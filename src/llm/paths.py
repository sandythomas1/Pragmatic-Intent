"""Where LLM artifacts may be written: only under the git-ignored ``outputs/`` tree (spec 009 FR18).

Cache entries, raw error bodies, rendered prompts and prediction files can all echo corpus text,
so every writer in ``src.llm`` resolves its target through ``under_outputs`` first.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def under_outputs(path: Path, root: Path = REPO_ROOT) -> Path:
    """The resolved target if it lies inside ``root/outputs/``; refuses anything else (incl. ``..``)."""
    target = (path if path.is_absolute() else root / path).resolve()
    if not target.is_relative_to((root / "outputs").resolve()):
        raise ValueError("LLM artifacts may echo corpus text and must be written under git-ignored outputs/")
    return target
