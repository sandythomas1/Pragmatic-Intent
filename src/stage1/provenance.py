"""Run provenance: code version, environment, GPU, and input hashes for every result.

Committed result records carry a user-chosen ``machine`` label rather than the
hostname, so a public repository does not expose lab host names. The hostname
is kept in the run's local (git-ignored) metrics file.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import socket
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

PACKAGES = ("torch", "transformers", "tokenizers", "scikit-learn", "numpy", "scipy")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False, cwd=cwd)


def git_state(ignore: Sequence[Path] = (), cwd: Path | None = None) -> dict[str, Any]:
    """Commit and dirty flag for the working tree containing ``cwd`` (default: the process's).

    ``ignore`` lists the run's own outputs (the results log it appends to, its output
    directory). They never mark the tree dirty; otherwise every run after the first in a
    checkout would report dirty code. Paths outside the worktree need no exclusion and
    are dropped, since git rejects an out-of-repository pathspec. Without a git binary on
    PATH both fields are unknown, as they are outside a repository.
    """
    unknown = {"git_commit": None, "git_dirty": None}
    try:
        commit = _git("rev-parse", "HEAD", cwd=cwd)
        top = _git("rev-parse", "--show-toplevel", cwd=cwd)
        if commit.returncode != 0 or top.returncode != 0:
            return unknown
        root = Path(top.stdout.strip()).resolve()
        excluded = [f":(exclude){path.as_posix()}" for path in (p.resolve() for p in ignore)
                    if path.is_relative_to(root)]
        status = _git("status", "--porcelain", "--", ":/", *excluded, cwd=cwd)
    except OSError:
        return unknown
    return {"git_commit": commit.stdout.strip(),
            "git_dirty": bool(status.stdout.strip()) if status.returncode == 0 else None}


def is_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text(encoding="utf-8").lower()
    except OSError:
        return False


def environment() -> dict[str, Any]:
    versions = {}
    for package in PACKAGES:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            continue
    return {"python": sys.version.split()[0], "platform": platform.platform(), "wsl": is_wsl(),
            "packages": versions}


def gpu_info() -> dict[str, Any] | None:
    """Device facts from torch; ``None`` when torch is absent or no GPU is visible."""
    try:
        import torch
    except ImportError:
        return None
    if not torch.cuda.is_available():
        return None
    major, minor = torch.cuda.get_device_capability(0)
    return {"name": torch.cuda.get_device_name(0), "capability": f"sm_{major}{minor}",
            "cuda_runtime": torch.version.cuda, "bf16": torch.cuda.is_bf16_supported(),
            "memory_gib": round(torch.cuda.get_device_properties(0).total_memory / 2**30, 1)}


def local_details() -> dict[str, Any]:
    """Details kept only in git-ignored run outputs."""
    return {"hostname": socket.gethostname()}


def append_result(path: Path, record: dict[str, Any]) -> None:
    """Append one JSON line; the file is the committed, append-only results log."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
