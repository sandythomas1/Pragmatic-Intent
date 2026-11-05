"""Length preflight and ``max_model_len`` sizing (spec 009 T4, FR5a).

Inputs are never truncated and an over-length input is never an ``invalid`` row: a long input is
almost always ``full``/``one``/mismatched context, so a length failure would land on one arm of
the H2 contrast. Instead, every rendered prompt is token-counted before the first call, and the
run is refused if any prompt plus the output-token limit exceeds the model's window.

The token counter is injected: a whitespace counter in tests, the pinned Qwen tokenizer's chat
template in the lab (T12). Reports and errors hold counts only, never IDs or text.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

Messages = Sequence[dict[str, str]]
TokenCounter = Callable[[Messages], int]
ROUND_TO = 512


class PreflightError(ValueError):
    """At least one prompt would not fit; the message holds counts only."""


@dataclass(frozen=True)
class LengthReport:
    """Counts only: safe to log for any split."""

    prompts: int
    max_prompt_tokens: int
    over_limit: int
    max_tokens: int
    max_model_len: int

    def as_dict(self) -> dict[str, int]:
        return {"prompts": self.prompts, "max_prompt_tokens": self.max_prompt_tokens,
                "over_limit": self.over_limit, "max_tokens": self.max_tokens, "max_model_len": self.max_model_len}


def measure(prompts: Iterable[Messages], count: TokenCounter, *, max_tokens: int, max_model_len: int) -> LengthReport:
    """Count every prompt; ``over_limit`` is how many need more than ``max_model_len - max_tokens``."""
    if max_tokens < 1 or max_model_len <= max_tokens:
        raise ValueError("need 1 <= max_tokens < max_model_len")
    room = max_model_len - max_tokens
    total = longest = over = 0
    for messages in prompts:
        tokens = count(messages)
        if type(tokens) is not int or tokens < 1:
            raise ValueError("token counter must return a positive integer")
        total += 1
        longest = max(longest, tokens)
        over += tokens > room
    if not total:
        raise ValueError("no prompts to check")
    return LengthReport(total, longest, over, max_tokens, max_model_len)


def require_fit(prompts: Iterable[Messages], count: TokenCounter, *, max_tokens: int,
                max_model_len: int) -> LengthReport:
    """FR5a: refuse the run before any call if any prompt cannot fit with its output budget."""
    report = measure(prompts, count, max_tokens=max_tokens, max_model_len=max_model_len)
    if report.over_limit:
        raise PreflightError(f"{report.over_limit} of {report.prompts} prompt(s) exceed max_model_len "
                             f"{report.max_model_len} minus max_tokens {report.max_tokens} "
                             f"(longest prompt {report.max_prompt_tokens} tokens); raise max_model_len "
                             "in the recipe, never truncate inputs")
    return report


def required_model_len(max_prompt_tokens: int, max_tokens: int, *, step: int = ROUND_TO) -> int:
    """Worst-case window: longest prompt plus the output limit, rounded up to the next multiple of
    ``step`` strictly above the sum, so there is always at least one token of margin (plan: Key
    details, ``max_model_len``)."""
    if max_prompt_tokens < 1 or max_tokens < 1 or step < 1:
        raise ValueError("token counts and step must be positive")
    return ((max_prompt_tokens + max_tokens) // step + 1) * step


def size_model_len(prompts: Iterable[Messages], count: TokenCounter, *, max_tokens: int,
                   step: int = ROUND_TO) -> int:
    """Sizing helper: the ``max_model_len`` to record in the recipe for these prompts. Feed it the
    longest prompt variant (P2) over the train and dev inputs; the test split is then covered by
    the renderer's 350-word bound and checked again by ``require_fit`` before its run."""
    longest = 0
    for messages in prompts:
        tokens = count(messages)
        if type(tokens) is not int or tokens < 1:
            raise ValueError("token counter must return a positive integer")
        longest = max(longest, tokens)
    if not longest:
        raise ValueError("no prompts to size")
    return required_model_len(longest, max_tokens, step=step)
