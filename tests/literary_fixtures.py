"""Tiny invented Gutenberg-format editions for the literary tests (spec 002).

The wording is invented, apart from Gutenberg's own marker and heading conventions. The files use
CRLF line endings like the real pinned files.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

AESOP_LINES = [
    "The Project Gutenberg eBook of Invented Fables",
    "",
    "*** START OF THE PROJECT GUTENBERG EBOOK INVENTED FABLES ***",
    "",
    "ÆSOP'S FABLES",
    "",
    "CONTENTS",
    "",
    "THE OWL AND THE KETTLE",
    "",
    "THE HEN AND THE LADDER",
    "",
    "",
    "",
    "",
    "ÆSOP'S FABLES",
    "",
    "",
    "",
    "",
    "THE OWL AND THE KETTLE",
    "",
    "",
    'An Owl sat by a cold Kettle and said to the Badger, "The night is long,',
    'and my feathers are thin." The Badger answered, "Then fetch some sticks."',
    "",
    "    Cold owls hint; warm badgers act.",
    "",
    "",
    "",
    "",
    "THE HEN AND THE LADDER",
    "",
    "",
    'A Hen looked up at the loft. "Oh, dear," said the Hen to the Goat, "what',
    'a fine loft that is." "It is," said the Goat. "Ladders are heavy,"',
    'said the Hen to herself, "and so is my',
    "",
    "",
    "",
    "",
    "ILLUSTRATIONS",
    "",
    "[Illustration: THE OWL AND THE KETTLE]",
    "",
    "*** END OF THE PROJECT GUTENBERG EBOOK INVENTED FABLES ***",
    "",
]

KJV_BOOKS = (("first", "First"), ("second", "Second"), ("third", "Third"))

KJV_LINES = [
    "The Project Gutenberg eBook of an Invented Scripture",
    "",
    "*** START OF THE PROJECT GUTENBERG EBOOK INVENTED SCRIPTURE ***",
    "",
    "The Old Testament of the King James Version of the Bible",
    "",
    "The First Book",
    "",
    "The Second Book",
    "",
    "The New Testament of the King James Bible",
    "",
    "The Third Book",
    "",
    "",
    "The Old Testament of the King James Version of the Bible",
    "",
    "",
    "The First Book",
    "",
    "Otherwise Called:",
    "",
    "The Third Book",
    "",
    "1:1 In the first place a gardener came to the gate. 1:2 And the gardener",
    "saith unto the keeper, The gate is shut.",
    "",
    "1:3 And the keeper opened it. 2:1 Then the keeper",
    "said unto him, What seekest thou?",
    "",
    "The Second Book",
    "",
    "1:1 A potter dwelt by the river.",
    "",
    "***",
    "",
    "The New Testament of the King James Bible",
    "",
    "",
    "The Third Book",
    "",
    "1:1 The weaver asked the merchant for thread.",
    "",
    "*** END OF THE PROJECT GUTENBERG EBOOK INVENTED SCRIPTURE ***",
    "",
]


def crlf(lines: list[str]) -> str:
    return "\r\n".join(lines)


AESOP_TEXT = crlf(AESOP_LINES)
KJV_TEXT = crlf(KJV_LINES)


def write_edition(raw_dir: Path, source: str, filename: str, text: str) -> str:
    """Write a fixture file under ``raw_dir/source`` and return its SHA-256."""
    data = text.encode("utf-8")
    (raw_dir / source).mkdir(parents=True, exist_ok=True)
    (raw_dir / source / filename).write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def manifest_toml(entries: list[tuple[str, str, str, int]]) -> str:
    """A minimal valid manifest for (source, filename, sha256, size) entries."""
    parts = ['schema_version = 1\nallowed_hosts = ["www.gutenberg.org"]\n']
    for source, filename, digest, size in entries:
        parts.append(
            f'[[sources]]\nname = "{source}"\ntitle = "t"\nhomepage = "https://www.gutenberg.org/"\n'
            f'license = "pd"\nlicense_url = "https://www.gutenberg.org/"\ncitation_key = "k"\nversion = "v"\n'
            f'intended_use = ["literary-transfer"]\n'
            f'[[sources.files]]\nurl = "https://www.gutenberg.org/cache/epub/1/{filename}"\npath = "{filename}"\n'
            f'size = {size}\nsha256 = "{digest}"\n'
        )
    return "\n".join(parts)


def install_fixture_editions(root: Path) -> tuple[Path, Path]:
    """Write both fixture editions and a manifest under ``root``; return (raw_dir, manifest_path)."""
    raw_dir = root / "raw"
    entries = []
    for source, filename, text in (("aesop_jones1912", "pg11339.txt", AESOP_TEXT), ("kjv_pg10", "pg10.txt", KJV_TEXT)):
        digest = write_edition(raw_dir, source, filename, text)
        entries.append((source, filename, digest, len(text.encode("utf-8"))))
    manifest_path = root / "sources.toml"
    manifest_path.write_text(manifest_toml(entries), encoding="utf-8")
    return raw_dir, manifest_path
