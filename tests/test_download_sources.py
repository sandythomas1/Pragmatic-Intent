"""Unit tests for ``src.data.download_sources``.

Standard-library ``unittest`` only, and no network access: downloads go through an
injected in-memory opener. Run from the repository root with either::

    python -m unittest discover -s tests -t .
    python -m pytest tests
"""

from __future__ import annotations

import hashlib
import io
import stat
import tarfile
import tempfile
import unittest
import urllib.request
import zipfile
from pathlib import Path

from src.data import download_sources as ds

HOST = "example.org"
PAYLOAD = b"hello, pragmatic world\n"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_entry(data: bytes = PAYLOAD, path: str = "data.txt", url: str = f"https://{HOST}/data.txt") -> dict:
    return {"url": url, "path": path, "sha256": sha(data), "size": len(data)}


def source_entry(files: list[dict] | None = None, name: str = "demo") -> dict:
    return {
        "name": name,
        "title": "Demo dataset",
        "homepage": f"https://{HOST}/demo",
        "license": "CC-BY-4.0",
        "license_url": f"https://{HOST}/license",
        "citation_key": "demo-2026",
        "version": "v1",
        "files": files if files is not None else [file_entry()],
    }


def manifest_dict(sources: list[dict] | None = None) -> dict:
    return {"schema_version": 1, "allowed_hosts": [HOST], "sources": sources or [source_entry()]}


class FakeOpener:
    """Serves in-memory bytes by URL and records each request."""

    def __init__(self, responses: dict[str, bytes]) -> None:
        self.responses = responses
        self.requested: list[str] = []

    def __call__(self, url: str) -> io.BytesIO:
        self.requested.append(url)
        return io.BytesIO(self.responses[url])


def refuse_network(url: str) -> io.BytesIO:
    raise AssertionError(f"unexpected network access: {url}")


def build_tar(path: Path, files: dict[str, bytes], links: dict[str, tuple[bytes, str]] | None = None) -> Path:
    """Write a .tar.gz with regular ``files`` plus optional ``links`` (name -> (tar type, target))."""
    with tarfile.open(path, "w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        for name, (link_type, target) in (links or {}).items():
            info = tarfile.TarInfo(name)
            info.type = link_type
            info.linkname = target
            tar.addfile(info)
    return path


def build_zip(path: Path, files: dict[str, bytes], symlinks: dict[str, str] | None = None) -> Path:
    with zipfile.ZipFile(path, "w") as zip_file:
        for name, data in files.items():
            zip_file.writestr(zipfile.ZipInfo(name), data)
        for name, target in (symlinks or {}).items():
            info = zipfile.ZipInfo(name)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zip_file.writestr(info, target)
    return path


class TempDirTestCase(unittest.TestCase):
    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.root = Path(temp_dir.name)


# --------------------------------------------------------------------------- manifest


class ManifestValidationTests(unittest.TestCase):
    def test_valid_manifest_parses(self) -> None:
        manifest = ds.parse_manifest(manifest_dict())
        self.assertEqual(manifest.allowed_hosts, frozenset({HOST}))
        (source,) = manifest.sources
        self.assertEqual(source.name, "demo")
        self.assertEqual(source.files[0].sha256, sha(PAYLOAD))

    def test_repository_manifest_is_valid(self) -> None:
        manifest = ds.load_manifest(ds.DEFAULT_MANIFEST)
        names = {source.name for source in manifest.sources}
        self.assertEqual(
            names,
            {
                "direct",
                "indirect_requests",
                "circa",
                "clinc150",
                "massive",
                "conv_implicatures",
                "multiwoz",
                "aesop_jones1912",
                "kjv_pg10",
            },
        )

    def test_literary_editions_are_pinned_single_files_on_gutenberg(self) -> None:
        manifest = ds.load_manifest(ds.DEFAULT_MANIFEST)
        literary = {source.name: source for source in manifest.sources if "literary-transfer" in source.intended_use}
        self.assertEqual(set(literary), {"aesop_jones1912", "kjv_pg10"})
        for source in literary.values():
            (spec,) = source.files
            self.assertTrue(spec.url.startswith("https://www.gutenberg.org/cache/epub/"), spec.url)
            self.assertFalse(spec.extract)

    def test_missing_source_field_rejected(self) -> None:
        data = manifest_dict()
        del data["sources"][0]["license"]
        with self.assertRaisesRegex(ds.ManifestError, "missing required field.*license"):
            ds.parse_manifest(data)

    def test_missing_file_checksum_rejected(self) -> None:
        data = manifest_dict()
        del data["sources"][0]["files"][0]["sha256"]
        with self.assertRaisesRegex(ds.ManifestError, "missing required field.*sha256"):
            ds.parse_manifest(data)

    def test_misspelled_field_rejected(self) -> None:
        data = manifest_dict()
        data["sources"][0]["files"][0]["sha265"] = "typo"
        with self.assertRaisesRegex(ds.ManifestError, "unknown field.*sha265"):
            ds.parse_manifest(data)

    def test_non_https_urls_rejected(self) -> None:
        for url in (f"http://{HOST}/data.txt", f"ftp://{HOST}/data.txt", "file:///etc/passwd"):
            with self.subTest(url=url):
                with self.assertRaisesRegex(ds.ManifestError, "https"):
                    ds.parse_manifest(manifest_dict([source_entry([file_entry(url=url)])]))

    def test_unlisted_hosts_rejected(self) -> None:
        for url in ("https://evil.example.com/data.txt", f"https://{HOST}.evil.com/data.txt"):
            with self.subTest(url=url):
                with self.assertRaisesRegex(ds.ManifestError, "not in allowed_hosts"):
                    ds.parse_manifest(manifest_dict([source_entry([file_entry(url=url)])]))

    def test_credentials_and_odd_ports_rejected(self) -> None:
        for url in (f"https://user:secret@{HOST}/data.txt", f"https://{HOST}:8443/data.txt"):
            with self.subTest(url=url):
                with self.assertRaises(ds.ManifestError):
                    ds.parse_manifest(manifest_dict([source_entry([file_entry(url=url)])]))

    def test_unsafe_target_paths_rejected(self) -> None:
        for path in ("../escape.txt", "/abs.txt", "a/../../b.txt", "C:/x.txt", "a\\b.txt", "", "a//b.txt", "./a.txt"):
            with self.subTest(path=path):
                with self.assertRaisesRegex(ds.ManifestError, "unsafe path"):
                    ds.parse_manifest(manifest_dict([source_entry([file_entry(path=path)])]))

    def test_malformed_checksum_rejected(self) -> None:
        data = manifest_dict()
        data["sources"][0]["files"][0]["sha256"] = "ABC123"
        with self.assertRaisesRegex(ds.ManifestError, "sha256"):
            ds.parse_manifest(data)

    def test_boolean_size_rejected(self) -> None:
        data = manifest_dict()
        data["sources"][0]["files"][0]["size"] = True
        with self.assertRaisesRegex(ds.ManifestError, "size"):
            ds.parse_manifest(data)

    def test_duplicate_source_names_rejected(self) -> None:
        with self.assertRaisesRegex(ds.ManifestError, "duplicate source name"):
            ds.parse_manifest(manifest_dict([source_entry(), source_entry()]))

    def test_extract_requires_archive_path(self) -> None:
        entry = file_entry()
        entry["extract"] = [{"member": "x.txt", "sha256": sha(b"x"), "size": 1}]
        with self.assertRaisesRegex(ds.ManifestError, "extract"):
            ds.parse_manifest(manifest_dict([source_entry([entry])]))

    def test_unknown_source_selection_rejected(self) -> None:
        manifest = ds.parse_manifest(manifest_dict())
        with self.assertRaisesRegex(ds.ManifestError, "unknown source"):
            ds.select_sources(manifest, ["nope"])


# --------------------------------------------------------------------------- network policy


class RedirectPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.handler = ds._AllowlistRedirectHandler(frozenset({HOST}))
        self.request = urllib.request.Request(f"https://{HOST}/start")

    def redirect(self, new_url: str) -> urllib.request.Request:
        return self.handler.redirect_request(self.request, io.BytesIO(), 302, "Found", {}, new_url)

    def test_redirect_to_allowed_host_is_followed(self) -> None:
        self.assertEqual(self.redirect(f"https://{HOST}/cache/file").full_url, f"https://{HOST}/cache/file")

    def test_redirect_to_unlisted_host_rejected(self) -> None:
        with self.assertRaises(ds.UnsafeUrlError):
            self.redirect("https://evil.example.com/file")

    def test_redirect_downgrade_to_http_rejected(self) -> None:
        with self.assertRaises(ds.UnsafeUrlError):
            self.redirect(f"http://{HOST}/file")

    def test_opener_rejects_unsafe_url_before_any_request(self) -> None:
        open_url = ds.make_url_opener(frozenset({HOST}))
        with self.assertRaises(ds.UnsafeUrlError):
            open_url(f"http://{HOST}/data.txt")


# --------------------------------------------------------------------------- checksums


class ChecksumTests(TempDirTestCase):
    url = f"https://{HOST}/data.txt"

    def download(self, served: bytes, expected: bytes = PAYLOAD) -> Path:
        dest = self.root / "out" / "data.txt"
        ds.download_file(self.url, dest, sha(expected), len(expected), FakeOpener({self.url: served}))
        return dest

    def assert_nothing_written(self) -> None:
        out_dir = self.root / "out"
        leftovers = list(out_dir.iterdir()) if out_dir.exists() else []
        self.assertEqual(leftovers, [], "failed download left files behind")

    def test_matching_checksum_keeps_file(self) -> None:
        dest = self.download(PAYLOAD)
        self.assertEqual(dest.read_bytes(), PAYLOAD)
        self.assertEqual(ds.sha256_file(dest), sha(PAYLOAD))

    def test_checksum_mismatch_fails_and_leaves_nothing(self) -> None:
        tampered = PAYLOAD.replace(b"hello", b"HELLO")  # same length, different bytes
        with self.assertRaisesRegex(ds.IntegrityError, "SHA-256 mismatch"):
            self.download(tampered)
        self.assert_nothing_written()

    def test_oversized_stream_fails(self) -> None:
        with self.assertRaisesRegex(ds.IntegrityError, "larger than"):
            self.download(PAYLOAD + b"extra")
        self.assert_nothing_written()

    def test_truncated_stream_fails(self) -> None:
        with self.assertRaisesRegex(ds.IntegrityError, "expected .* bytes"):
            self.download(PAYLOAD[:-3])
        self.assert_nothing_written()


# --------------------------------------------------------------------------- idempotency


class IdempotencyTests(TempDirTestCase):
    def source(self, files: list[dict] | None = None) -> ds.Source:
        return ds.parse_manifest(manifest_dict([source_entry(files)])).sources[0]

    def test_intact_file_is_skipped_without_network(self) -> None:
        target = self.root / "demo" / "data.txt"
        target.parent.mkdir(parents=True)
        target.write_bytes(PAYLOAD)
        self.assertEqual(ds.fetch_source(self.source(), self.root, refuse_network), ["up-to-date"])

    def test_corrupted_file_is_downloaded_again(self) -> None:
        target = self.root / "demo" / "data.txt"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"corrupted")
        opener = FakeOpener({f"https://{HOST}/data.txt": PAYLOAD})
        with self.assertLogs(ds.logger, "WARNING") as logs:
            self.assertEqual(ds.fetch_source(self.source(), self.root, opener), ["downloaded"])
        self.assertIn("fails its checksum", logs.output[0])
        self.assertEqual(target.read_bytes(), PAYLOAD)

    def test_second_run_is_a_no_op(self) -> None:
        opener = FakeOpener({f"https://{HOST}/data.txt": PAYLOAD})
        ds.fetch_source(self.source(), self.root, opener)
        self.assertEqual(ds.fetch_source(self.source(), self.root, refuse_network), ["up-to-date"])
        self.assertEqual(len(opener.requested), 1)

    def test_verify_only_reports_missing_file(self) -> None:
        with self.assertRaisesRegex(ds.IntegrityError, "missing or modified"):
            ds.fetch_source(self.source(), self.root, None, verify_only=True)

    def test_archive_is_extracted_then_removed_and_later_skipped(self) -> None:
        member = b'{"utt": "it is freezing in here"}\n'
        archive_bytes = build_tar(self.root / "src.tar.gz", {"pkg/data.jsonl": member}).read_bytes()
        entry = file_entry(archive_bytes, path="bundle.tar.gz", url=f"https://{HOST}/bundle.tar.gz")
        entry["keep_archive"] = False
        entry["extract"] = [{"member": "pkg/data.jsonl", "sha256": sha(member), "size": len(member)}]
        source = self.source([entry])

        opener = FakeOpener({entry["url"]: archive_bytes})
        self.assertEqual(ds.fetch_source(source, self.root, opener), ["extracted"])
        self.assertEqual((self.root / "demo" / "pkg" / "data.jsonl").read_bytes(), member)
        self.assertFalse((self.root / "demo" / "bundle.tar.gz").exists(), "archive should be deleted")

        self.assertEqual(ds.fetch_source(source, self.root, refuse_network), ["up-to-date"])


# --------------------------------------------------------------------------- archive safety


class ArchiveSafetyTests(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.dest = self.root / "dest"
        self.dest.mkdir()

    def spec(self, member: str, data: bytes = PAYLOAD) -> ds.ExtractSpec:
        return ds.ExtractSpec(member=member, sha256=sha(data), size=len(data))

    def assert_no_escape(self) -> None:
        self.assertFalse((self.root / "evil.txt").exists(), "a file escaped the destination directory")

    def test_tar_traversal_members_rejected(self) -> None:
        for name in ("../evil.txt", "pkg/../../evil.txt", "/evil.txt"):
            with self.subTest(member=name):
                archive = build_tar(self.root / "bad.tar.gz", {name: PAYLOAD})
                with self.assertRaises(ds.UnsafePathError):
                    ds.extract_members(archive, self.dest, [self.spec(name)])
                self.assert_no_escape()

    def test_tar_link_members_rejected(self) -> None:
        for link_type in (tarfile.SYMTYPE, tarfile.LNKTYPE):
            with self.subTest(link_type=link_type):
                archive = build_tar(self.root / "links.tar.gz", {}, links={"data.txt": (link_type, "../../evil.txt")})
                with self.assertRaisesRegex(ds.UnsafePathError, "not a regular file"):
                    ds.extract_members(archive, self.dest, [self.spec("data.txt")])

    def test_zip_traversal_members_rejected(self) -> None:
        for name in ("../evil.txt", "pkg/../../evil.txt", "/evil.txt", "..\\evil.txt"):
            with self.subTest(member=name):
                archive = build_zip(self.root / "bad.zip", {name: PAYLOAD})
                with self.assertRaises(ds.UnsafePathError):
                    ds.extract_members(archive, self.dest, [self.spec(name)])
                self.assert_no_escape()

    def test_zip_symlink_member_rejected(self) -> None:
        archive = build_zip(self.root / "links.zip", {}, symlinks={"data.txt": "../../evil.txt"})
        with self.assertRaisesRegex(ds.UnsafePathError, "not a regular file"):
            ds.extract_members(archive, self.dest, [self.spec("data.txt", b"../../evil.txt")])

    def test_unrequested_traversal_member_is_never_written(self) -> None:
        archive = build_tar(self.root / "mixed.tar.gz", {"../evil.txt": b"pwned", "pkg/ok.txt": PAYLOAD})
        ds.extract_members(archive, self.dest, [self.spec("pkg/ok.txt")])
        self.assertEqual((self.dest / "pkg" / "ok.txt").read_bytes(), PAYLOAD)
        self.assert_no_escape()

    def test_safe_members_extract_from_tar_and_zip(self) -> None:
        for archive in (
            build_tar(self.root / "ok.tar.gz", {"pkg/data.txt": PAYLOAD}),
            build_zip(self.root / "ok.zip", {"pkg/data.txt": PAYLOAD}),
        ):
            with self.subTest(archive=archive.name):
                ds.extract_members(archive, self.dest, [self.spec("pkg/data.txt")])
                self.assertEqual((self.dest / "pkg" / "data.txt").read_bytes(), PAYLOAD)

    def test_extracted_checksum_mismatch_rejected_and_removed(self) -> None:
        archive = build_tar(self.root / "ok.tar.gz", {"pkg/data.txt": PAYLOAD})
        wrong = ds.ExtractSpec(member="pkg/data.txt", sha256=sha(b"something else"), size=len(PAYLOAD))
        with self.assertRaises(ds.IntegrityError):
            ds.extract_members(archive, self.dest, [wrong])
        self.assertFalse((self.dest / "pkg" / "data.txt").exists())

    def test_declared_size_mismatch_rejected(self) -> None:
        archive = build_zip(self.root / "ok.zip", {"pkg/data.txt": PAYLOAD})
        wrong_size = ds.ExtractSpec(member="pkg/data.txt", sha256=sha(PAYLOAD), size=len(PAYLOAD) + 1)
        with self.assertRaisesRegex(ds.IntegrityError, "declared size"):
            ds.extract_members(archive, self.dest, [wrong_size])


if __name__ == "__main__":
    unittest.main()
