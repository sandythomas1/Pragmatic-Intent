"""Mechanical, exhaustive screening proposals within an episode (spec 002, FR4).

A proposal is a span that *might* be addressed speech. It is never a judgment: a human screener
decides speaker, addressee and eligibility. Proposals are made for every speech-like span in an
episode, so selection never depends on a model or on what the researcher happened to notice.

* Aesop: every double-quoted span in a narrative paragraph. Interrupted speech
  (``"Oh, dear," said the Hen, "what a loft."``) becomes one proposal. An unclosed quote runs to
  the end of its paragraph and is flagged.
* KJV: every verse with a speech verb. The KJV has no quotation marks, so the whole verse is
  proposed and flagged for the screener to trim.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from src.literary.sources import Edition, Unit

QUOTE = '"'
MAX_SPEECH_TAG_CHARS = 80
_SENTENCE_END = re.compile(r"[.!?]")
KJV_SPEECH_VERBS = re.compile(
    r"\b(saith|said|say|saying|spake|spoken|answered|asked|cried|besought|commanded|told|prayed)\b",
    re.IGNORECASE,
)

FLAG_MERGED = "merged"
FLAG_UNCLOSED = "unclosed_quote"
FLAG_NEEDS_TRIM = "needs_trim"


@dataclass(frozen=True)
class Proposal:
    candidate_id: str
    source: str
    family_id: str
    episode_id: str
    unit_id: str
    locator: str
    start: int
    end: int
    flags: tuple[str, ...] = ()


def candidate_id(source: str, start: int, end: int) -> str:
    """Stable ID for a span: identical spans always get the same ID, across runs and machines."""
    return "lit-" + hashlib.sha256(f"{source}:{start}:{end}".encode()).hexdigest()[:10]


Span = tuple[int, int, tuple[str, ...]]  # start, end, flags


def propose_episode(edition: Edition, episode_id: str, family_id: str) -> list[Proposal]:
    proposer = PROPOSERS.get(edition.source)
    if proposer is None:
        raise ValueError(f"no proposal rule for source {edition.source!r}")
    return [
        Proposal(candidate_id(edition.source, start, end), edition.source, family_id, episode_id, unit.unit_id,
                 unit.locator, start, end, flags)
        for unit, (start, end, flags) in proposer(edition, edition.episode_units(episode_id))
    ]  # fmt: skip


def _aesop_spans(edition: Edition, units: tuple[Unit, ...]) -> list[tuple[Unit, Span]]:
    return [(unit, span) for unit in units if unit.kind == "narrative" for span in quoted_spans(edition.text, unit)]


def _kjv_spans(edition: Edition, units: tuple[Unit, ...]) -> list[tuple[Unit, Span]]:
    return [
        (unit, (unit.start, unit.end, (FLAG_NEEDS_TRIM,)))
        for unit in units
        if unit.kind == "verse" and KJV_SPEECH_VERBS.search(edition.unit_text(unit))
    ]


def quoted_spans(text: str, unit: Unit) -> list[Span]:
    """(start, end, flags) of each quoted span in ``unit``, with quote marks included."""
    quotes = [position for position in range(unit.start, unit.end) if text[position] == QUOTE]
    spans: list[Span] = []
    for index in range(0, len(quotes), 2):
        if index + 1 < len(quotes):
            spans.append((quotes[index], quotes[index + 1] + 1, ()))
        else:
            spans.append((quotes[index], unit.end, (FLAG_UNCLOSED,)))
    return _merge_interrupted(text, spans)


def _merge_interrupted(text: str, spans: list[Span]) -> list[Span]:
    merged: list[Span] = []
    for span in spans:
        if merged and _continues(text, merged[-1], span):
            start, _, flags = merged[-1]
            combined = tuple(dict.fromkeys((*flags, FLAG_MERGED, *span[2])))
            merged[-1] = (start, span[1], combined)
        else:
            merged.append(span)
    return merged


def _continues(text: str, previous: Span, current: Span) -> bool:
    """Interrupted speech: the earlier quote ends with a comma and a short tag joins them."""
    previous_start, previous_end, previous_flags = previous
    if FLAG_UNCLOSED in previous_flags or previous_end - previous_start < 3:
        return False
    ends_with_comma = text[previous_end - 2] == ","
    gap = text[previous_end : current[0]]
    return ends_with_comma and len(gap) <= MAX_SPEECH_TAG_CHARS and not _SENTENCE_END.search(gap)


PROPOSERS = {"aesop_jones1912": _aesop_spans, "kjv_pg10": _kjv_spans}
