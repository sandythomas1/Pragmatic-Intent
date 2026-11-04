"""Local open-weights backend on vLLM's offline engine (spec 009 T12, FR7).

Pinned and greedy:
- the weights and tokenizer load at the recipe's exact commit (``revision``), with
  ``trust_remote_code=False``, so no code from the model repository ever runs;
- bf16, temperature 0, a fixed seed and the recipe's ``max_tokens``;
- every request is constrained to its JSON schema through vLLM structured outputs (vLLM >= 0.12:
  ``SamplingParams(structured_outputs=StructuredOutputsParams(json=...))``). Transfer requests each
  carry their own candidate-enum schema;
- automatic prefix caching reuses the shared instructions across a batch.

vLLM's finish reasons map onto the parser's: ``stop`` -> ``stop``, ``length`` -> ``length`` (the
parser then marks the answer ``truncated``). An aborted request or any engine exception is not a
content outcome. It propagates as an unmapped failure and stops the run, resumably. An in-process
engine that died cannot be fixed by retrying in the same process, so no vLLM error maps to
``TransportError``.

``vllm`` and ``transformers`` are imported only when this backend is built (the ``llm`` uv group,
Linux only), so the stdlib core and its tests never need them.

Fallback (FR7, R13): if vLLM can't run on the lab machine, a plain ``transformers`` backend would
implement the same ``Backend`` interface. Without vLLM's grammar-constrained decoding its JSON
would be unconstrained, so its invalid rate is not comparable and must be disclosed. It is not
built until it is needed.
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from src.llm.backends.base import Backend, Request, Response
from src.llm.preflight import TokenCounter

if TYPE_CHECKING:
    from src.llm.recipe import Recipe

DTYPE = "bfloat16"
SEED = 0
FINISH_REASONS = {"stop": "stop", "length": "length"}


class VllmBackend(Backend):
    name = "vllm"

    def __init__(self, engine: Any, *, model_ref: str, max_tokens: int, sampling_params: Any,
                 structured_outputs: Any, tokenizer: Any = None) -> None:
        self.engine = engine
        self.model_id = model_ref
        self.max_tokens = max_tokens
        self._sampling_params = sampling_params
        self._structured_outputs = structured_outputs
        self._tokenizer = tokenizer

    @classmethod
    def from_recipe(cls, recipe: Recipe) -> VllmBackend:
        vllm = importlib.import_module("vllm")
        sampling = importlib.import_module("vllm.sampling_params")
        options = recipe.options
        engine = vllm.LLM(**engine_arguments(recipe.model_id, options))
        return cls(engine, model_ref=recipe.model_ref, max_tokens=recipe.max_tokens,
                   sampling_params=vllm.SamplingParams, structured_outputs=sampling.StructuredOutputsParams)

    @classmethod
    def counter_from_recipe(cls, recipe: Recipe) -> TokenCounter:
        """Only the pinned tokenizer (no GPU, no engine), for ``size`` on any machine with the group."""
        transformers = importlib.import_module("transformers")
        revision = recipe.options["revision"]
        tokenizer = transformers.AutoTokenizer.from_pretrained(recipe.model_id, revision=revision,
                                                               trust_remote_code=False)
        return chat_token_counter(tokenizer)

    def token_counter(self) -> TokenCounter:
        return chat_token_counter(self._tokenizer or self.engine.get_tokenizer())

    def generate(self, batch: Sequence[Request]) -> list[Response]:
        params = [self._params(request) for request in batch]
        conversations = [[dict(message) for message in request.messages] for request in batch]
        outputs = self.engine.chat(conversations, sampling_params=params, use_tqdm=False, add_generation_prompt=True)
        if len(outputs) != len(batch):
            raise RuntimeError("vLLM returned a different number of outputs than requests")
        return [_response(request, output) for request, output in zip(batch, outputs)]

    def _params(self, request: Request) -> Any:
        constraint = self._structured_outputs(json=_plain(request.schema))
        return self._sampling_params(temperature=0.0, max_tokens=self.max_tokens, seed=SEED,
                                     structured_outputs=constraint)


def engine_arguments(model_id: str, options: Mapping[str, Any]) -> dict[str, Any]:
    """The ``vllm.LLM`` arguments: weights and tokenizer pinned to one commit, no remote code."""
    arguments = {
        "model": model_id, "revision": options["revision"], "tokenizer_revision": options["revision"],
        "trust_remote_code": False, "dtype": DTYPE, "seed": SEED, "enable_prefix_caching": True,
        "max_model_len": options["max_model_len"], "gpu_memory_utilization": options["gpu_memory_utilization"],
    }
    if "max_num_seqs" in options:
        arguments["max_num_seqs"] = options["max_num_seqs"]
    return arguments


def chat_token_counter(tokenizer: Any) -> TokenCounter:
    """Prompt length as vLLM sees it: the chat template rendered with the generation prompt, then
    encoded without extra special tokens (the template already includes them)."""
    def count(messages: Sequence[Mapping[str, str]]) -> int:
        text = tokenizer.apply_chat_template([dict(m) for m in messages], tokenize=False, add_generation_prompt=True)
        return len(tokenizer(text, add_special_tokens=False)["input_ids"])
    return count


def _response(request: Request, output: Any) -> Response:
    completion = output.outputs[0]
    reason = FINISH_REASONS.get(completion.finish_reason)
    if reason is None:
        raise RuntimeError("vLLM ended a request without a stop or length finish (aborted?)")
    usage = {"input_tokens": len(output.prompt_token_ids or ()), "output_tokens": len(completion.token_ids or ())}
    return Response(request.key, completion.text, reason, usage)


def _plain(value: Any) -> Any:
    """Schemas arrive as read-only mappings; vLLM expects plain dicts and lists."""
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value
