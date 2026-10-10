"""Segment pinned literary editions into located units (spec 002, FR2).

Each supported source is a single Project Gutenberg plain-text file pinned in ``data/sources.toml``.
``load_edition`` verifies the file's SHA-256 against that pin, decodes it as UTF-8 **without
newline translation**, and parses it into ``Unit`` records. Every unit's ``start``/``end`` are
code-point offsets into that decoded text, so ``edition.text[unit.start:unit.end]`` is the unit's
exact source text (surrounding whitespace trimmed) and re-encodes to the original bytes.

Formats (see docs/data_sources.md, "Literary editions"):

* ``aesop_jones1912``: fables. Kinds are ``title``, ``narrative`` and ``moral`` (an indented
  paragraph). Episode = fable, ``aesop:<title-slug>``.
* ``kjv_pg10``: verses. Kind is ``verse``, and the verse-number marker is excluded from the span.
  Episode = chapter, ``kjv:<book>:<chapter>``.

The parsers are deliberately strict: an unexpected structure raises ``ParseError`` instead of
producing slightly different units, because committed locators depend on them.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from src.data import download_sources

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "raw"

UNIT_KINDS = ("title", "narrative", "moral", "verse")
NON_SPEECH_KINDS = frozenset({"title", "moral"})

_START_MARKER = "*** START OF"
_END_MARKER = "*** END OF"


class LiteraryError(Exception):
    """A literary source is missing, does not match its pin, or cannot be used as requested."""


class ParseError(LiteraryError):
    """A pinned file does not have the structure its parser expects."""


class AmbiguousSpanError(LiteraryError):
    """A target text occurs more than once in the region searched."""


@dataclass(frozen=True)
class Unit:
    """One located span of a pinned edition: a fable paragraph/title or a Bible verse."""

    source: str
    unit_id: str
    episode_id: str
    kind: str
    locator: str
    start: int
    end: int


@dataclass(frozen=True)
class Edition:
    """A pinned, hash-verified, segmented source file."""

    source: str
    sha256: str
    text: str
    units: tuple[Unit, ...]
    _episodes: dict[str, tuple[Unit, ...]] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        episodes: dict[str, list[Unit]] = {}
        for unit in self.units:
            episodes.setdefault(unit.episode_id, []).append(unit)
        object.__setattr__(self, "_episodes", {key: tuple(value) for key, value in episodes.items()})

    def unit_text(self, unit: Unit) -> str:
        return self.text[unit.start : unit.end]

    @property
    def episode_ids(self) -> tuple[str, ...]:
        """Episode IDs in source order."""
        return tuple(self._episodes)

    def episode_units(self, episode_id: str) -> tuple[Unit, ...]:
        try:
            return self._episodes[episode_id]
        except KeyError:
            raise LiteraryError(f"{self.source}: unknown episode {episode_id!r}") from None

    def episode_bounds(self, episode_id: str) -> tuple[int, int]:
        units = self.episode_units(episode_id)
        return units[0].start, units[-1].end

    def units_overlapping(self, episode_id: str, start: int, end: int) -> list[Unit]:
        return [unit for unit in self.episode_units(episode_id) if unit.start < end and start < unit.end]


# --------------------------------------------------------------------------- loading


def load_edition(
    source: str,
    raw_dir: Path = DEFAULT_RAW_DIR,
    manifest_path: Path = download_sources.DEFAULT_MANIFEST,
) -> Edition:
    """Read ``source``'s pinned file, verify its SHA-256 against the manifest, and segment it."""
    parser = PARSERS.get(source)
    if parser is None:
        raise LiteraryError(f"no literary parser for source {source!r}; known: {', '.join(sorted(PARSERS))}")
    spec = _pinned_file(source, manifest_path)
    path = download_sources.resolve_inside(raw_dir / source, spec.path)
    if not path.is_file():
        raise LiteraryError(f"{path} is missing; run: python -m src.data.download_sources --only {source}")
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != spec.sha256:
        raise LiteraryError(f"{path}: SHA-256 {digest} does not match the pinned {spec.sha256}; refusing to parse")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ParseError(f"{path}: not valid UTF-8 ({error})") from None
    return Edition(source=source, sha256=digest, text=text, units=tuple(parser(source, text)))


def _pinned_file(source: str, manifest_path: Path) -> download_sources.FileSpec:
    manifest = download_sources.load_manifest(manifest_path)
    for entry in manifest.sources:
        if entry.name == source:
            if len(entry.files) != 1 or entry.files[0].extract:
                raise LiteraryError(f"{source}: a literary source must pin exactly one plain file")
            return entry.files[0]
    raise LiteraryError(f"{source} is not in {manifest_path}")


# --------------------------------------------------------------------------- text helpers


@dataclass(frozen=True)
class _Line:
    start: int
    content: str  # without the line terminator

    @property
    def blank(self) -> bool:
        return not self.content.strip()


def _lines(text: str, start: int, end: int) -> list[_Line]:
    lines = []
    position = start
    while position < end:
        newline = text.find("\n", position, end)
        stop = end if newline == -1 else newline
        content_end = stop - 1 if stop > position and text[stop - 1] == "\r" else stop
        lines.append(_Line(position, text[position:content_end]))
        position = end if newline == -1 else newline + 1
    return lines


def _body_bounds(text: str) -> tuple[int, int]:
    """Offsets of the text between the Gutenberg START and END marker lines."""
    start_marker = text.find(_START_MARKER)
    end_marker = text.find(_END_MARKER)
    if start_marker == -1 or end_marker == -1 or end_marker < start_marker:
        raise ParseError("Project Gutenberg START/END markers not found")
    body_start = text.find("\n", start_marker)
    if body_start == -1 or body_start > end_marker:
        raise ParseError("Project Gutenberg START marker line is not terminated")
    return body_start + 1, end_marker


def _trimmed(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def collapse_whitespace(value: str) -> str:
    """Single-space a span for display; the source text itself is never rewritten."""
    return " ".join(value.split())


def resolve_span(text: str, region_start: int, region_end: int, needle: str) -> tuple[int, int]:
    """Locate ``needle`` exactly once in ``text[region_start:region_end]``, ignoring whitespace differences.

    Matching is literal apart from whitespace runs, and respects word boundaries at both ends, so
    "he" does not match inside "the". Raises ``LiteraryError`` if there are zero or several matches.
    """
    tokens = needle.split()
    if not tokens:
        raise LiteraryError("target text is empty")
    pattern = r"\s+".join(re.escape(token) for token in tokens)
    if re.match(r"\w", tokens[0][0]):
        pattern = r"(?<!\w)" + pattern
    if re.match(r"\w", tokens[-1][-1]):
        pattern += r"(?!\w)"
    compiled = re.compile(pattern)
    matches: list[tuple[int, int]] = []
    position = region_start
    while len(matches) < 2:
        match = compiled.search(text, position, region_end)
        if match is None:
            break
        matches.append((match.start(), match.end()))
        position = match.start() + 1  # count overlapping occurrences too
    if not matches:
        raise LiteraryError("target text does not occur in its episode")
    if len(matches) > 1:
        raise AmbiguousSpanError("target text occurs more than once in its episode; add surrounding words")
    return matches[0]


def _slug(value: str) -> str:
    value = value.lower().replace("æ", "ae").replace("œ", "oe")
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")


# --------------------------------------------------------------------------- Aesop


_AESOP_HEADING = "ÆSOP'S FABLES"
_AESOP_REGION_END = "ILLUSTRATIONS"
_TITLE_MIN_BLANKS_BEFORE = 3


def _is_aesop_title(lines: Sequence[_Line], index: int) -> bool:
    content = lines[index].content
    if not content.strip() or content[0].isspace() or content != content.upper() or not re.search("[A-Z]", content):
        return False
    before = lines[max(0, index - _TITLE_MIN_BLANKS_BEFORE) : index]
    after_blank = index + 1 >= len(lines) or lines[index + 1].blank
    return len(before) == _TITLE_MIN_BLANKS_BEFORE and all(line.blank for line in before) and after_blank


def _paragraphs(lines: Sequence[_Line]) -> list[list[_Line]]:
    paragraphs: list[list[_Line]] = []
    current: list[_Line] = []
    for line in lines:
        if line.blank:
            if current:
                paragraphs.append(current)
                current = []
        else:
            current.append(line)
    if current:
        paragraphs.append(current)
    return paragraphs


def parse_aesop(source: str, text: str) -> list[Unit]:
    """Fables between the last standalone heading and the trailing ILLUSTRATIONS list."""
    body_start, body_end = _body_bounds(text)
    lines = _lines(text, body_start, body_end)
    headings = [i for i, line in enumerate(lines) if line.content.strip() == _AESOP_HEADING]
    if not headings:
        raise ParseError(f"{_AESOP_HEADING!r} heading not found")
    region_start = headings[-1] + 1
    region_end = next(
        (i for i in range(region_start, len(lines)) if lines[i].content.strip() == _AESOP_REGION_END), None
    )
    if region_end is None:
        raise ParseError(f"trailing {_AESOP_REGION_END!r} heading not found")
    region = lines[region_start:region_end]

    title_indexes = [i for i in range(len(region)) if _is_aesop_title(region, i)]
    if not title_indexes:
        raise ParseError("no fable titles found")
    if any(not line.blank for line in region[: title_indexes[0]]):
        raise ParseError("text before the first fable title")

    units: list[Unit] = []
    seen: set[str] = set()
    for position, title_index in enumerate(title_indexes):
        title_line = region[title_index]
        title = title_line.content.strip()
        episode_id = f"aesop:{_slug(title)}"
        if episode_id in seen:
            raise ParseError(f"duplicate fable title {title!r}")
        seen.add(episode_id)
        start, end = _trimmed(text, title_line.start, title_line.start + len(title_line.content))
        units.append(Unit(source, f"{episode_id}:title", episode_id, "title", title, start, end))

        next_title = title_indexes[position + 1] if position + 1 < len(title_indexes) else len(region)
        paragraphs = _paragraphs(region[title_index + 1 : next_title])
        if not any(not paragraph[0].content[0].isspace() for paragraph in paragraphs):
            raise ParseError(f"fable {title!r} has no narrative paragraph")
        for number, paragraph in enumerate(paragraphs, start=1):
            kind = "moral" if all(line.content[0].isspace() for line in paragraph) else "narrative"
            last = paragraph[-1]
            start, end = _trimmed(text, paragraph[0].start, last.start + len(last.content))
            units.append(Unit(source, f"{episode_id}:p{number}", episode_id, kind, f"{title}, para {number}", start, end))
    return units


# --------------------------------------------------------------------------- King James Bible


KJV_BOOKS: tuple[tuple[str, str], ...] = (
    ("genesis", "Genesis"), ("exodus", "Exodus"), ("leviticus", "Leviticus"), ("numbers", "Numbers"),
    ("deuteronomy", "Deuteronomy"), ("joshua", "Joshua"), ("judges", "Judges"), ("ruth", "Ruth"),
    ("1samuel", "1 Samuel"), ("2samuel", "2 Samuel"), ("1kings", "1 Kings"), ("2kings", "2 Kings"),
    ("1chronicles", "1 Chronicles"), ("2chronicles", "2 Chronicles"), ("ezra", "Ezra"),
    ("nehemiah", "Nehemiah"), ("esther", "Esther"), ("job", "Job"), ("psalms", "Psalms"),
    ("proverbs", "Proverbs"), ("ecclesiastes", "Ecclesiastes"), ("songofsolomon", "Song of Solomon"),
    ("isaiah", "Isaiah"), ("jeremiah", "Jeremiah"), ("lamentations", "Lamentations"),
    ("ezekiel", "Ezekiel"), ("daniel", "Daniel"), ("hosea", "Hosea"), ("joel", "Joel"), ("amos", "Amos"),
    ("obadiah", "Obadiah"), ("jonah", "Jonah"), ("micah", "Micah"), ("nahum", "Nahum"),
    ("habakkuk", "Habakkuk"), ("zephaniah", "Zephaniah"), ("haggai", "Haggai"),
    ("zechariah", "Zechariah"), ("malachi", "Malachi"),
    ("matthew", "Matthew"), ("mark", "Mark"), ("luke", "Luke"), ("john", "John"), ("acts", "Acts"),
    ("romans", "Romans"), ("1corinthians", "1 Corinthians"), ("2corinthians", "2 Corinthians"),
    ("galatians", "Galatians"), ("ephesians", "Ephesians"), ("philippians", "Philippians"),
    ("colossians", "Colossians"), ("1thessalonians", "1 Thessalonians"),
    ("2thessalonians", "2 Thessalonians"), ("1timothy", "1 Timothy"), ("2timothy", "2 Timothy"),
    ("titus", "Titus"), ("philemon", "Philemon"), ("hebrews", "Hebrews"), ("james", "James"),
    ("1peter", "1 Peter"), ("2peter", "2 Peter"), ("1john", "1 John"), ("2john", "2 John"),
    ("3john", "3 John"), ("jude", "Jude"), ("revelation", "Revelation"),
)  # fmt: skip

_OLD_TESTAMENT_PREFIX = "The Old Testament of the King James"
_NEW_TESTAMENT_PREFIX = "The New Testament of the King James"
# A marker may end its line ("... 3:5" then the verse text on the next line), hence "|$".
_VERSE_MARKER = re.compile(r"(?:(?<=\s)|^)(\d{1,3}):(\d{1,3})(?=\s|$)")


def _is_testament_heading(content: str) -> bool:
    return content.startswith(_OLD_TESTAMENT_PREFIX) or content.startswith(_NEW_TESTAMENT_PREFIX)


def _is_structural(content: str) -> bool:
    """Testament headings and decorative separators ("***") end the verse before them."""
    is_separator = bool(content.strip()) and not re.search(r"\w", content)
    return is_separator or _is_testament_heading(content)


def parse_kjv(source: str, text: str, books: Sequence[tuple[str, str]] = KJV_BOOKS) -> list[Unit]:
    """Verses, with book headings matched in table-of-contents order."""
    body_start, body_end = _body_bounds(text)
    lines = _lines(text, body_start, body_end)
    old_testament = [i for i, line in enumerate(lines) if line.content.startswith(_OLD_TESTAMENT_PREFIX)]
    if len(old_testament) != 2:
        raise ParseError("expected the Old Testament heading twice (contents, then body)")
    contents = [
        line.content.strip()
        for line in lines[old_testament[0] + 1 : old_testament[1]]
        if not line.blank and not _is_testament_heading(line.content)
    ]
    if len(contents) != len(books):
        raise ParseError(f"table of contents lists {len(contents)} books; expected {len(books)}")

    # Group body lines into books. A heading only counts when it is the *next* expected title, so
    # alias headings ("Otherwise Called: The First Book of the Kings") stay inside their book's
    # preamble, before verse 1:1, where they are ignored.
    book_lines: list[list[_Line]] = []
    expected = 0
    for line in lines[old_testament[1] + 1 :]:
        if expected < len(contents) and line.content.strip() == contents[expected]:
            book_lines.append([])
            expected += 1
        elif book_lines:
            book_lines[-1].append(line)
    if expected != len(contents):
        raise ParseError(f"book heading {contents[expected]!r} not found in the body")

    units: list[Unit] = []
    for (slug, name), lines_of_book in zip(books, book_lines, strict=True):
        units.extend(_book_verses(source, text, slug, name, lines_of_book))
    return units


def _book_verses(source: str, text: str, slug: str, name: str, lines: Sequence[_Line]) -> list[Unit]:
    # Each verse runs from its marker to the next marker or a structural heading line.
    markers: list[tuple[int, int, int, int]] = []  # chapter, verse, marker_start, text_start
    stops: list[int] = []
    for line in lines:
        if _is_structural(line.content):
            stops.append(line.start)
            continue
        for match in _VERSE_MARKER.finditer(line.content):
            markers.append((int(match[1]), int(match[2]), line.start + match.start(), line.start + match.end()))
    if not markers:
        raise ParseError(f"{name}: no verses found")
    book_end = lines[-1].start + len(lines[-1].content)

    units = []
    previous: tuple[int, int] | None = None
    for index, (chapter, verse, _, text_start) in enumerate(markers):
        allowed = {(1, 1)} if previous is None else {(previous[0], previous[1] + 1), (previous[0] + 1, 1)}
        if (chapter, verse) not in allowed:
            after = "the book heading" if previous is None else f"{previous[0]}:{previous[1]}"
            raise ParseError(f"{name}: verse {chapter}:{verse} follows {after}")
        previous = (chapter, verse)
        limit = markers[index + 1][2] if index + 1 < len(markers) else book_end
        limit = min([limit, *(stop for stop in stops if stop > text_start)])
        start, end = _trimmed(text, text_start, limit)
        if start == end:
            raise ParseError(f"{name} {chapter}:{verse} is empty")
        episode_id = f"kjv:{slug}:{chapter}"
        units.append(Unit(source, f"{episode_id}:{verse}", episode_id, "verse", f"{name} {chapter}:{verse}", start, end))
    return units


PARSERS: dict[str, Callable[[str, str], list[Unit]]] = {
    "aesop_jones1912": parse_aesop,
    "kjv_pg10": parse_kjv,
}
