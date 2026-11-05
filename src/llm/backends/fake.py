"""A scripted backend for tests (spec 009 T6). It never touches a model or the network."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING

from src.llm.backends.base import Backend, Request, Response, TransportError
from src.llm.preflight import TokenCounter

if TYPE_CHECKING:
    from src.llm.recipe import Recipe

Answer = tuple[str, str, dict[str, int]]
Failure = BaseException | Callable[[Sequence[Request]], BaseException] | None

DEFAULT_ANSWER = json.dumps({"route": "direct", "category": "booking", "slots": [], "requested_slots": []})


def default_respond(request: Request) -> Answer:
    return DEFAULT_ANSWER, "stop", {"input_tokens": 10, "output_tokens": 5}


def word_count(messages: Sequence[Mapping[str, str]]) -> int:
    """A stand-in tokenizer: whitespace-separated words across all messages."""
    return sum(len(message["content"].split()) for message in messages)


class FakeBackend(Backend):
    """Answers via ``respond``; before each batch, pops the next scripted ``failures`` entry.

    A failure may be an exception, a factory that builds one from the batch (so it can echo the
    request, as some provider errors do) or ``None`` for a normal call.
    """

    name = "fake"

    def __init__(self, model_id: str = "fake-model", respond: Callable[[Request], Answer] = default_respond,
                 failures: Sequence[Failure] = ()) -> None:
        self.model_id = model_id
        self.respond = respond
        self.failures = list(failures)
        self.batches: list[list[str]] = []

    @classmethod
    def from_recipe(cls, recipe: Recipe) -> FakeBackend:
        return cls(model_id=recipe.model_ref)

    def token_counter(self) -> TokenCounter:
        return word_count

    @property
    def calls(self) -> int:
        return sum(len(batch) for batch in self.batches)

    def generate(self, batch: Sequence[Request]) -> list[Response]:
        failure = self.failures.pop(0) if self.failures else None
        if failure is not None:
            raise failure(batch) if callable(failure) and not isinstance(failure, BaseException) else failure
        self.batches.append([request.key for request in batch])
        return [Response(request.key, *self.respond(request)) for request in batch]


def echoing_error(status: int = 503, secret: str = "") -> Callable[[Sequence[Request]], TransportError]:
    """A transport error whose message echoes the whole request (and an optional secret)."""
    def build(batch: Sequence[Request]) -> TransportError:
        echoed = " ".join(message["content"] for request in batch for message in request.messages)
        return TransportError(f"upstream said: {echoed} {secret}", status=status, request_id="req_fake01")
    return build
