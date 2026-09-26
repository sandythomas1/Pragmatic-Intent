"""Download the third-party source datasets listed in ``data/sources.toml``.

Run from the repository root with Python 3.11+ (standard library only)::

    python -m src.data.download_sources                   # fetch every source
    python -m src.data.download_sources --only circa massive
    python -m src.data.download_sources --verify-only     # check local files, no network
    python -m src.data.download_sources --list            # show what the manifest pins

Files land in ``data/raw/<source name>/`` (git-ignored). Re-running is cheap: a
file that already exists with the expected SHA-256 is skipped.

Security properties:

* Every URL, including each redirect target, must be ``https://`` on a host in the
  manifest's ``allowed_hosts``. The opener has no plain-HTTP, FTP, or file handlers.
* A downloaded or extracted file is kept only if its size and SHA-256 match the
  manifest. A mismatch is fatal and the partial file is deleted.
* Only archive members named in the manifest are extracted. Each must be a regular
  file whose path stays inside the source directory; tar extraction also uses
  ``filter="data"``.
* Nothing downloaded is imported or executed.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import ssl
import stat
import sys
import tarfile
import tempfile
import tomllib
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPO_ROOT / "data" / "sources.toml"
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "raw"

SUPPORTED_SCHEMA_VERSION = 1
CHUNK_SIZE = 1024 * 1024
TIMEOUT_SECONDS = 60
USER_AGENT = "pragmatic-intent-downloader/1.0 (+https://github.com/sandythomas1/Pragmatic-Intent)"

_NAME_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]*")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_TAR_SUFFIXES = (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz")
# tarfile.FilterError only exists on Python 3.11.4+; an empty tuple matches nothing.
_TAR_FILTER_ERROR = getattr(tarfile, "FilterError", ())

# Field name -> expected TOML type, per table. Unknown fields are rejected so a typo
# such as "sha265" fails loudly instead of silently disabling a check.
_MANIFEST_FIELDS = {"schema_version": int, "allowed_hosts": list, "sources": list}
_SOURCE_REQUIRED = {
    "name": str,
    "title": str,
    "homepage": str,
    "license": str,
    "license_url": str,
    "citation_key": str,
    "version": str,
    "files": list,
}
_SOURCE_OPTIONAL = {"intended_use": list, "notes": str}
_FILE_REQUIRED = {"url": str, "path": str, "sha256": str, "size": int}
_FILE_OPTIONAL = {"extract": list, "keep_archive": bool}
_EXTRACT_REQUIRED = {"member": str, "sha256": str, "size": int}

OpenUrl = Callable[[str], BinaryIO]
"""Opens a URL and returns a readable binary stream (injectable for tests)."""

logger = logging.getLogger(__name__)


class DownloadSourcesError(Exception):
    """Base class for every error this module raises deliberately."""


class ManifestError(DownloadSourcesError):
    """The manifest is malformed or breaks a safety rule."""


class UnsafeUrlError(DownloadSourcesError):
    """A URL is not HTTPS or its host is not allow-listed."""


class UnsafePathError(DownloadSourcesError):
    """A path (e.g. an archive member) would escape its target directory."""


class IntegrityError(DownloadSourcesError):
    """A file is missing, or its size or SHA-256 does not match the manifest."""


@dataclass(frozen=True)
class ExtractSpec:
    """One archive member to extract, with its expected size and checksum."""

    member: str
    sha256: str
    size: int


@dataclass(frozen=True)
class FileSpec:
    """One file to download, optionally an archive with members to extract."""

    url: str
    path: str
    sha256: str
    size: int
    extract: tuple[ExtractSpec, ...] = ()
    keep_archive: bool = True


@dataclass(frozen=True)
class Source:
    """A dataset and the provenance metadata recorded for it."""

    name: str
    title: str
    homepage: str
    license: str
    license_url: str
    citation_key: str
    version: str
    files: tuple[FileSpec, ...]
    intended_use: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class Manifest:
    allowed_hosts: frozenset[str]
    sources: tuple[Source, ...]


# --------------------------------------------------------------------------- manifest


def load_manifest(path: Path) -> Manifest:
    """Read and validate a TOML manifest."""
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ManifestError(f"manifest not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ManifestError(f"{path}: invalid TOML: {exc}") from exc
    return parse_manifest(data)


def parse_manifest(data: dict[str, Any]) -> Manifest:
    """Validate an already-parsed manifest and convert it into dataclasses."""
    _check_fields(data, _MANIFEST_FIELDS, {}, "manifest")
    if data["schema_version"] != SUPPORTED_SCHEMA_VERSION:
        raise ManifestError(
            f"manifest: unsupported schema_version {data['schema_version']} "
            f"(expected {SUPPORTED_SCHEMA_VERSION})"
        )
    allowed_hosts = _parse_allowed_hosts(data["allowed_hosts"])
    sources = tuple(
        _parse_source(raw, allowed_hosts, f"sources[{index}]")
        for index, raw in enumerate(data["sources"])
    )
    if not sources:
        raise ManifestError("manifest: 'sources' must not be empty")
    _reject_duplicates([source.name for source in sources], "manifest: duplicate source name")
    return Manifest(allowed_hosts=allowed_hosts, sources=sources)


def _parse_allowed_hosts(hosts: list[Any]) -> frozenset[str]:
    if not hosts:
        raise ManifestError("manifest: 'allowed_hosts' must not be empty")
    for host in hosts:
        if not isinstance(host, str) or not host or host != host.lower() or "/" in host:
            raise ManifestError(f"manifest: invalid allowed host {host!r} (use a lowercase hostname)")
    return frozenset(hosts)


def _parse_source(raw: Any, allowed_hosts: frozenset[str], context: str) -> Source:
    _check_fields(raw, _SOURCE_REQUIRED, _SOURCE_OPTIONAL, context)
    name = raw["name"]
    if not _NAME_PATTERN.fullmatch(name):
        raise ManifestError(f"{context}: invalid name {name!r} (use lowercase letters, digits, '_' or '-')")
    context = f"source {name!r}"
    if not raw["files"]:
        raise ManifestError(f"{context}: 'files' must not be empty")
    files = tuple(
        _parse_file(entry, allowed_hosts, f"{context} files[{index}]")
        for index, entry in enumerate(raw["files"])
    )
    outputs = [spec.path for spec in files] + [m.member for spec in files for m in spec.extract]
    _reject_duplicates(outputs, f"{context}: duplicate output path")
    intended_use = raw.get("intended_use", [])
    if not all(isinstance(item, str) for item in intended_use):
        raise ManifestError(f"{context}: 'intended_use' must be a list of strings")
    return Source(
        name=name,
        title=raw["title"],
        homepage=raw["homepage"],
        license=raw["license"],
        license_url=raw["license_url"],
        citation_key=raw["citation_key"],
        version=raw["version"],
        files=files,
        intended_use=tuple(intended_use),
        notes=raw.get("notes", ""),
    )


def _parse_file(raw: Any, allowed_hosts: frozenset[str], context: str) -> FileSpec:
    _check_fields(raw, _FILE_REQUIRED, _FILE_OPTIONAL, context)
    try:
        validate_url(raw["url"], allowed_hosts)
    except UnsafeUrlError as exc:
        raise ManifestError(f"{context}: {exc}") from exc
    path = _checked_relative_path(raw["path"], f"{context} path")
    extract = tuple(
        _parse_extract(entry, f"{context} extract[{index}]")
        for index, entry in enumerate(raw.get("extract", []))
    )
    if extract and archive_kind(path) is None:
        raise ManifestError(f"{context}: 'extract' needs a .zip or .tar[.gz|.bz2|.xz] path, got {path!r}")
    if "keep_archive" in raw and not extract:
        raise ManifestError(f"{context}: 'keep_archive' only applies together with 'extract'")
    return FileSpec(
        url=raw["url"],
        path=path,
        sha256=_checked_sha256(raw["sha256"], context),
        size=_checked_size(raw["size"], context),
        extract=extract,
        keep_archive=raw.get("keep_archive", True),
    )


def _parse_extract(raw: Any, context: str) -> ExtractSpec:
    _check_fields(raw, _EXTRACT_REQUIRED, {}, context)
    return ExtractSpec(
        member=_checked_relative_path(raw["member"], f"{context} member"),
        sha256=_checked_sha256(raw["sha256"], context),
        size=_checked_size(raw["size"], context),
    )


def _check_fields(table: Any, required: dict[str, type], optional: dict[str, type], context: str) -> None:
    if not isinstance(table, dict):
        raise ManifestError(f"{context}: expected a table")
    missing = sorted(required.keys() - table.keys())
    if missing:
        raise ManifestError(f"{context}: missing required field(s): {', '.join(missing)}")
    unknown = sorted(table.keys() - required.keys() - optional.keys())
    if unknown:
        raise ManifestError(f"{context}: unknown field(s): {', '.join(unknown)}")
    for key, expected_type in (required | optional).items():
        value = table.get(key)
        # bool is a subclass of int in Python; don't let `size = true` pass as a number.
        wrong_bool = expected_type is int and isinstance(value, bool)
        if key in table and (wrong_bool or not isinstance(value, expected_type)):
            raise ManifestError(f"{context}: field {key!r} must be of type {expected_type.__name__}")


def _checked_relative_path(value: str, context: str) -> str:
    if not is_safe_relative_path(value):
        raise ManifestError(f"{context}: unsafe path {value!r} (must be relative, '/'-separated, no '..')")
    return value


def _checked_sha256(value: str, context: str) -> str:
    if not _SHA256_PATTERN.fullmatch(value):
        raise ManifestError(f"{context}: sha256 must be 64 lowercase hex characters")
    return value


def _checked_size(value: int, context: str) -> int:
    if value <= 0:
        raise ManifestError(f"{context}: size must be a positive number of bytes")
    return value


def _reject_duplicates(values: Sequence[str], message: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ManifestError(f"{message}: {value!r}")
        seen.add(value)


def select_sources(manifest: Manifest, names: Sequence[str] | None) -> tuple[Source, ...]:
    """Return the requested sources in manifest order (all of them if ``names`` is empty)."""
    if not names:
        return manifest.sources
    requested = set(names)
    known = {source.name for source in manifest.sources}
    unknown = sorted(requested - known)
    if unknown:
        raise ManifestError(f"unknown source(s): {', '.join(unknown)}; known: {', '.join(sorted(known))}")
    return tuple(source for source in manifest.sources if source.name in requested)


# --------------------------------------------------------------------------- safety checks


def validate_url(url: str, allowed_hosts: frozenset[str]) -> None:
    """Raise ``UnsafeUrlError`` unless ``url`` is plain HTTPS on an allow-listed host."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https":
        raise UnsafeUrlError(f"only https:// URLs are allowed, got {url!r}")
    if parts.username is not None or parts.password is not None:
        raise UnsafeUrlError(f"credentials are not allowed in URLs: {parts.hostname!r}")
    try:
        port = parts.port
    except ValueError as exc:
        raise UnsafeUrlError(f"invalid port in URL {url!r}") from exc
    if port not in (None, 443):
        raise UnsafeUrlError(f"non-standard port {port} is not allowed: {url!r}")
    host = (parts.hostname or "").lower()
    if host not in allowed_hosts:
        raise UnsafeUrlError(f"host {host!r} is not in allowed_hosts")


def is_safe_relative_path(value: str) -> bool:
    """True for a relative, '/'-separated path with no empty, '.' or '..' segments.

    Backslashes, drive letters, and colons are rejected outright so a path means
    the same thing on Windows and POSIX.
    """
    if not value or value.startswith("/") or any(char in value for char in "\\:\x00"):
        return False
    return all(segment not in ("", ".", "..") for segment in value.split("/"))


def resolve_inside(base: Path, relative: str) -> Path:
    """Join ``relative`` onto ``base``, refusing anything that lands outside ``base``."""
    if not is_safe_relative_path(relative):
        raise UnsafePathError(f"refusing unsafe path {relative!r}")
    target = base.joinpath(*relative.split("/"))
    # resolve() also follows symlinks already on disk, which a string check would miss.
    if not target.resolve().is_relative_to(base.resolve()):
        raise UnsafePathError(f"refusing path {relative!r}: it resolves outside {base}")
    return target


def archive_kind(path: str) -> str | None:
    """Return ``"zip"``, ``"tar"``, or ``None`` based on the file name."""
    lowered = path.lower()
    if lowered.endswith(".zip"):
        return "zip"
    if lowered.endswith(_TAR_SUFFIXES):
        return "tar"
    return None


# --------------------------------------------------------------------------- network


class _AllowlistRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only if the new URL passes the same allow-list check."""

    max_redirections = 5

    def __init__(self, allowed_hosts: frozenset[str]) -> None:
        super().__init__()
        self._allowed_hosts = allowed_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # urllib has already resolved `newurl` against the request URL at this point.
        validate_url(newurl, self._allowed_hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def make_url_opener(allowed_hosts: frozenset[str]) -> OpenUrl:
    """Build an HTTPS-only opener with certificate verification and safe redirects."""
    opener = urllib.request.OpenerDirector()
    for handler in (
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        _AllowlistRedirectHandler(allowed_hosts),
        urllib.request.HTTPDefaultErrorHandler(),
        urllib.request.HTTPErrorProcessor(),
    ):
        opener.add_handler(handler)

    def open_url(url: str) -> BinaryIO:
        validate_url(url, allowed_hosts)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        return opener.open(request, timeout=TIMEOUT_SECONDS)

    return open_url


def download_file(url: str, dest: Path, expected_sha256: str, expected_size: int, open_url: OpenUrl) -> None:
    """Stream ``url`` into ``dest``. The file is kept only if size and SHA-256 match."""
    with open_url(url) as response:
        _write_verified(response, dest, expected_sha256, expected_size, label=url)


# --------------------------------------------------------------------------- files


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _is_intact(path: Path, expected_sha256: str) -> bool:
    return path.is_file() and sha256_file(path) == expected_sha256


def _write_verified(source: BinaryIO, dest: Path, expected_sha256: str, expected_size: int, label: str) -> None:
    """Copy ``source`` into ``dest`` via a temp file, then move it into place only if it verifies.

    Reading stops as soon as the stream exceeds ``expected_size``, so a hostile or
    broken server (or a decompression bomb) can't fill the disk.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=dest.parent, prefix=f".{dest.name}.", suffix=".part")
    temp_path = Path(temp_name)
    try:
        digest = hashlib.sha256()
        received = 0
        with os.fdopen(handle, "wb") as out:
            while chunk := source.read(CHUNK_SIZE):
                received += len(chunk)
                if received > expected_size:
                    raise IntegrityError(f"{label}: stream is larger than the expected {expected_size} bytes")
                digest.update(chunk)
                out.write(chunk)
        if received != expected_size:
            raise IntegrityError(f"{label}: expected {expected_size} bytes, got {received}")
        actual = digest.hexdigest()
        if actual != expected_sha256:
            raise IntegrityError(
                f"{label}: SHA-256 mismatch\n  expected {expected_sha256}\n  actual   {actual}"
            )
        os.replace(temp_path, dest)
    finally:
        temp_path.unlink(missing_ok=True)


# --------------------------------------------------------------------------- archives


def extract_members(archive: Path, dest_dir: Path, members: Sequence[ExtractSpec]) -> None:
    """Extract exactly ``members`` from a tar or zip archive into ``dest_dir``.

    Each member must be a regular file whose name is a safe relative path. Its
    extracted size and SHA-256 must match the manifest.
    """
    targets = [(spec, resolve_inside(dest_dir, spec.member)) for spec in members]
    kind = archive_kind(archive.name)
    try:
        if kind == "tar":
            _extract_tar(archive, dest_dir, targets)
        elif kind == "zip":
            _extract_zip(archive, targets)
        else:
            raise DownloadSourcesError(f"{archive.name}: unsupported archive type")
    except _TAR_FILTER_ERROR as exc:
        raise UnsafePathError(f"{archive.name}: {exc}") from exc
    except (tarfile.TarError, zipfile.BadZipFile) as exc:
        raise DownloadSourcesError(f"{archive.name}: cannot read archive: {exc}") from exc
    for spec, target in targets:
        if not _is_intact(target, spec.sha256):
            target.unlink(missing_ok=True)
            raise IntegrityError(f"{archive.name}:{spec.member}: extracted file failed its SHA-256 check")


def _extract_tar(archive: Path, dest_dir: Path, targets: list[tuple[ExtractSpec, Path]]) -> None:
    with tarfile.open(archive, mode="r:*") as tar:
        for spec, target in targets:
            try:
                info = tar.getmember(spec.member)
            except KeyError as exc:
                raise DownloadSourcesError(f"{archive.name}: member {spec.member!r} not found") from exc
            _check_member(archive, spec, is_regular_file=info.isfile(), declared_size=info.size)
            target.parent.mkdir(parents=True, exist_ok=True)
            if hasattr(tarfile, "data_filter"):
                tar.extract(info, path=dest_dir, filter="data")
            else:  # Python < 3.11.4 lacks extraction filters; copy the vetted regular file's bytes.
                with tar.extractfile(info) as member_stream:
                    _write_verified(member_stream, target, spec.sha256, spec.size, f"{archive.name}:{spec.member}")


def _extract_zip(archive: Path, targets: list[tuple[ExtractSpec, Path]]) -> None:
    with zipfile.ZipFile(archive) as zip_file:
        for spec, target in targets:
            try:
                info = zip_file.getinfo(spec.member)
            except KeyError as exc:
                raise DownloadSourcesError(f"{archive.name}: member {spec.member!r} not found") from exc
            is_symlink = stat.S_ISLNK(info.external_attr >> 16)
            _check_member(archive, spec, is_regular_file=not (info.is_dir() or is_symlink), declared_size=info.file_size)
            with zip_file.open(info) as member_stream:
                _write_verified(member_stream, target, spec.sha256, spec.size, f"{archive.name}:{spec.member}")


def _check_member(archive: Path, spec: ExtractSpec, *, is_regular_file: bool, declared_size: int) -> None:
    if not is_regular_file:
        raise UnsafePathError(f"{archive.name}:{spec.member} is not a regular file (link, directory, or device)")
    if declared_size != spec.size:
        raise IntegrityError(f"{archive.name}:{spec.member}: declared size {declared_size}, expected {spec.size}")


# --------------------------------------------------------------------------- orchestration


def fetch_source(
    source: Source,
    raw_dir: Path,
    open_url: OpenUrl | None,
    *,
    verify_only: bool = False,
) -> list[str]:
    """Make ``raw_dir/<source.name>`` match the manifest. Returns one status per file entry."""
    source_dir = raw_dir / source.name
    return [_fetch_file(spec, source_dir, open_url, verify_only) for spec in source.files]


def _fetch_file(spec: FileSpec, source_dir: Path, open_url: OpenUrl | None, verify_only: bool) -> str:
    download_path = resolve_inside(source_dir, spec.path)
    if spec.extract:
        wanted = [(resolve_inside(source_dir, m.member), m.sha256) for m in spec.extract]
    else:
        wanted = [(download_path, spec.sha256)]

    if all(_is_intact(path, sha) for path, sha in wanted):
        logger.info("  up to date   %s", spec.path)
        return "up-to-date"
    if verify_only or open_url is None:
        broken = ", ".join(str(path) for path, sha in wanted if not _is_intact(path, sha))
        raise IntegrityError(f"missing or modified: {broken}")

    if not _is_intact(download_path, spec.sha256):
        if download_path.exists():
            logger.warning("  %s exists but fails its checksum; downloading it again", download_path)
        logger.info("  downloading  %s", spec.url)
        download_file(spec.url, download_path, spec.sha256, spec.size, open_url)
    if not spec.extract:
        return "downloaded"

    logger.info("  extracting   %d member(s) from %s", len(spec.extract), spec.path)
    extract_members(download_path, source_dir, spec.extract)
    if not spec.keep_archive:
        download_path.unlink()
    return "extracted"


# --------------------------------------------------------------------------- CLI


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m src.data.download_sources",
        description="Download and verify the raw source datasets pinned in data/sources.toml.",
    )
    parser.add_argument("--only", nargs="+", metavar="NAME", help="fetch only these sources")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="manifest path")
    parser.add_argument("--dest", type=Path, default=DEFAULT_RAW_DIR, help="root directory for raw data")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify-only", action="store_true", help="check local files; never download")
    mode.add_argument("--list", action="store_true", help="print the pinned sources and exit")
    return parser.parse_args(argv)


def _print_sources(sources: Sequence[Source], raw_dir: Path) -> None:
    for source in sources:
        print(f"{source.name}: {source.title}")
        print(f"  version: {source.version}")
        print(f"  license: {source.license}")
        print(f"  target:  {raw_dir / source.name}")
        for spec in source.files:
            outputs = [m.member for m in spec.extract] or [spec.path]
            print(f"    {spec.url}\n      -> {', '.join(outputs)}")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        manifest = load_manifest(args.manifest)
        sources = select_sources(manifest, args.only)
    except DownloadSourcesError as exc:
        logger.error("%s", exc)
        return 1

    if args.list:
        _print_sources(sources, args.dest)
        return 0

    open_url = None if args.verify_only else make_url_opener(manifest.allowed_hosts)
    failures: list[str] = []
    for source in sources:
        logger.info("%s (%s)", source.name, source.version)
        try:
            fetch_source(source, args.dest, open_url, verify_only=args.verify_only)
        except (DownloadSourcesError, OSError) as exc:  # urllib/ssl/socket errors are OSErrors
            logger.error("%s: %s", source.name, exc)
            failures.append(source.name)

    if failures:
        logger.error("FAILED: %s", ", ".join(failures))
        return 1
    logger.info("OK: %d source(s) verified in %s", len(sources), args.dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
