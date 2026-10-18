"""What an annotator sees around a target: ``seg-v1`` prior segments and the continuation (spec 003 FR4).

Prior segments are the one shared, numbered view of prior context. Context-pass evidence cites
their indices, so the segmenter is versioned (``context_schema.SEGMENTER_VERSION``) and every
context row records the version it was cited against.

* **Dialogue:** segment ``i`` is turn ``i`` for ``0 <= i < t``: the same window as the ``full``
  condition in ``direct_dataset.build_context``. The continuation is turns ``t+1`` to the end.
* **Literary:** the episode's ``narrative``/``verse`` units, in order, clipped at the target's
  start. Each unit is split into sentences after ``.``, ``!`` or ``?`` plus any closing quotes,
  where whitespace follows. Segments never cross a unit, empty ones are dropped, and ``title`` and
  ``moral`` units are never segments. The continuation runs from the target's end to the end of
  the episode, moral included, and is shown in the reveal pass only.

Everything here is pure: callers pass in text they have already verified against the registry.
These views are for annotators. Model input rendering belongs to spec 004.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from src.data.direct_dataset import Turn
from src.literary import sources as ls

PRIOR_UNIT_KINDS = frozenset({"narrative", "verse"})
# A sentence ends at . ! or ? plus any closing quotes, when whitespace follows.
_SENTENCE_END = re.compile(r"[.!?][\"'”’]*(?=\s)")


@dataclass(frozen=True)
class Segment:
    """One numbered piece of context. ``speaker`` is the dialogue speaker, or ``moral``, or ``""``."""

    index: int
    speaker: str
    text: str


def collapse(text: str) -> str:
    """One line with single spaces: pinned editions wrap lines mid-sentence."""
    return " ".join(text.split())


# --------------------------------------------------------------------------- dialogue


def dialogue_prior(turns: Sequence[Turn], turn_index: int) -> list[Segment]:
    """Turns ``0..t-1``, text unchanged: exactly the ``full`` context condition."""
    _check_turn(turns, turn_index)
    return [Segment(i, turn.speaker, turn.text) for i, turn in enumerate(turns[:turn_index])]


def dialogue_continuation(turns: Sequence[Turn], turn_index: int) -> list[Segment]:
    """Turns ``t+1`` to the end, numbered by their turn index."""
    _check_turn(turns, turn_index)
    return [Segment(i, turns[i].speaker, turns[i].text) for i in range(turn_index + 1, len(turns))]


def _check_turn(turns: Sequence[Turn], turn_index: int) -> None:
    if not 0 <= turn_index < len(turns):
        raise ValueError(f"turn {turn_index} is outside a dialogue of {len(turns)} turns")


# --------------------------------------------------------------------------- literary


def sentences(text: str) -> list[str]:
    """Split one unit's text into whitespace-collapsed sentences; empty pieces are dropped."""
    pieces, start = [], 0
    for match in _SENTENCE_END.finditer(text):
        pieces.append(text[start : match.end()])
        start = match.end()
    pieces.append(text[start:])
    return [piece for piece in (collapse(piece) for piece in pieces) if piece]


def literary_prior(edition: ls.Edition, episode_id: str, target_start: int) -> list[Segment]:
    """Sentences of the episode's narrative/verse units before ``target_start``, numbered from 0.

    A unit containing the target contributes only its text before the target, so a mid-paragraph
    target gets the paragraph's earlier sentences as separate segments.
    """
    _check_offset(edition, episode_id, target_start)
    texts: list[str] = []
    for unit in edition.episode_units(episode_id):
        if unit.kind not in PRIOR_UNIT_KINDS or unit.start >= target_start:
            continue
        texts += sentences(edition.text[unit.start : min(unit.end, target_start)])
    return [Segment(i, "", text) for i, text in enumerate(texts)]


def literary_continuation(edition: ls.Edition, episode_id: str, target_end: int) -> list[Segment]:
    """Everything in the episode after the target, one segment per unit (or unit remainder).

    Morals are included and marked ``speaker="moral"``; titles are not story text and are skipped.
    """
    _check_offset(edition, episode_id, target_end)
    segments: list[Segment] = []
    for unit in edition.episode_units(episode_id):
        if unit.kind == "title" or unit.end <= target_end:
            continue
        text = collapse(edition.text[max(unit.start, target_end) : unit.end])
        if text:
            segments.append(Segment(len(segments), "moral" if unit.kind == "moral" else "", text))
    return segments


def _check_offset(edition: ls.Edition, episode_id: str, offset: int) -> None:
    start, end = edition.episode_bounds(episode_id)
    if not start <= offset <= end:
        raise ValueError(f"offset {offset} is outside episode {episode_id} ({start}-{end})")


# --------------------------------------------------------------------------- rendering


def render(segments: Sequence[Segment]) -> str:
    """One line per segment, ``[i] SPEAKER: text``, for a sheet cell (Excel wraps on newlines)."""
    return "\n".join(f"[{s.index}] {s.speaker.upper() + ': ' if s.speaker else ''}{collapse(s.text)}" for s in segments)
