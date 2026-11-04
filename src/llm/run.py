"""LLM runner CLI (spec 009 T8, FR4, FR6, FR8).

    python -E -s -m src.llm.run run --recipe configs/llm/<recipe>.toml --split dev --task main
    python -E -s -m src.llm.run run --recipe ... --split dev --task main --variant p2 --conditions none full
    python -E -s -m src.llm.run size --recipe ... --split dev    # tokenizer only: the max_model_len needed

One run, in order:
1. Load the recipe.
2. Verify the inputs (schema, recomputed hashes, oracle ⊂ routed).
3. Collapse them to distinct input hashes: one call per distinct input (FR2).
4. Serve cached keys.
5. Construct the backend only if there are misses; run the FR5a length preflight over every
   prompt, then send the misses in batches, appending each batch to the cache before the next.
6. Parse every answer strictly (no repair) and write the streams atomically. For the main task
   that is routed, oracle and interpretation; the last is the composer's input, see
   ``src.llm.streams``.
7. Write provenance last (FR8). A provenance file therefore means a complete run, and it holds
   the hash of every stream it describes.

Where streams go:
- the recipe's selected variant over all conditions writes the scored streams to
  ``outputs/stage2/<system>/<split>/``;
- any other variant, or a condition subset (prompt selection, FR9), writes to
  ``outputs/llm/selection/<system>/<variant>/<split>/``, so a partial stream can't be mistaken for
  a scored one.

The test split is refused unconditionally until the freeze gate lands (T10). Paid backends are
refused until the spend ledger lands (T7). Logs and errors carry counts, hashes and field names
only, never an example ID or corpus text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
import sys
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.data.direct_dataset import CONDITIONS
from src.data.freeze import text_sha256
from src.evaluation.interpretation import validate_predictions
from src.llm import backends, prompt, schema, streams
from src.llm.backends.base import Backend, CallStats, ErrorLog, Request, RunStopped, generate_with_retry
from src.llm.cache import CacheError, KeyParts, ResponseCache, exclusive_lock, new_entry
from src.llm.inputs import InputError, InputStream, check_oracle_subset, distinct_inputs, load_stream
from src.llm.paths import REPO_ROOT, under_outputs
from src.llm.preflight import (LengthReport, PreflightError, TokenCounter, measure, require_fit,
                                required_model_len)
from src.llm.recipe import SPLITS, Recipe, RecipeError, load_recipe
from src.stage1.provenance import git_state, source_sha256

PROVENANCE_VERSION = "llm-run-v1"
TASKS = ("main", "transfer")
STREAMS = {"main": ("routed", "oracle", "interpretation"), "transfer": ("transfer",)}
SOURCE_RECORDS = {"routed": "routed", "oracle": "oracle", "interpretation": "routed", "transfer": "transfer"}
PROGRESS_EVERY = 1000
TEST_REFUSED = "--split test is refused until the freeze gate is in place (spec 009 T10)"
BackendFactory = Callable[[Recipe], Backend]
CounterFactory = Callable[[Recipe], TokenCounter | None]
log = logging.getLogger(__name__)


class RunRefused(ValueError):
    """The request is not allowed (split, variant, conditions or backend); nothing was called."""


@dataclass(frozen=True)
class Call:
    """One distinct input's call: its cache key and everything needed to make and parse it."""

    key: str
    record: Mapping[str, Any]
    messages: tuple[Mapping[str, str], ...]
    schema: Mapping[str, Any]
    schema_sha256: str


def default_backend_factory(recipe: Recipe) -> Backend:
    return backends.backend_class(recipe.backend).from_recipe(recipe)


def run(recipe: Recipe, *, split: str, task: str, variant: str | None = None,
        conditions: Sequence[str] | None = None, root: Path = REPO_ROOT,
        backend_factory: BackendFactory = default_backend_factory, sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None, progress_every: int = PROGRESS_EVERY) -> dict[str, Any]:
    """Run one task on one split end to end; returns the provenance record it wrote."""
    started = _now()
    variant, conditions = _check_request(recipe, split, task, variant, conditions)
    inputs = _load_inputs(recipe, split, task, conditions)
    prompt_path = recipe.prompt_path(variant) if task == "main" else recipe.transfer_prompt
    slot_keys = schema.load_slot_keys(recipe.slot_keys) if task == "main" else ()
    instructions = (prompt.main_instructions(prompt_path, slot_keys) if task == "main"
                    else prompt.transfer_instructions(prompt_path))
    calls = plan_calls(recipe, task, instructions, slot_keys, inputs.values())
    out_dir = output_dir(recipe, split, task, variant, conditions, root)
    cache_path = under_outputs(Path("outputs/llm/cache") / recipe.system / f"{task}.jsonl", root)
    error_log = ErrorLog(Path("outputs/llm/errors") / recipe.system / f"{task}.jsonl", root)
    stats, new_usage, report = CallStats(), Counter[str](), None

    with exclusive_lock(cache_path):
        cache = ResponseCache(cache_path, root).load()
        misses = [call for call in calls if call.key not in cache]
        log.info("%s/%s: %d distinct inputs, %d cached, %d to call", task, split, len(calls),
                 len(calls) - len(misses), len(misses))
        if misses:
            backend = backend_factory(recipe)
            if backend.name != recipe.backend or backend.model_id != recipe.model_ref:
                raise RunRefused("the constructed backend does not match the recipe's backend and model")
            report = _preflight(recipe, backend, calls)
            _call_misses(backend, misses, cache, recipe.batch_size, error_log=error_log, stats=stats,
                         sleep=sleep, rng=rng or random.Random(), usage=new_usage, progress_every=progress_every)
        outcomes, invalid_calls, all_usage = _parse(task, calls, cache, slot_keys)
        cache_entries = len(cache)

    written: dict[str, str] = {}
    rows_by_kind: dict[str, int] = {}
    invalid_rows: dict[str, dict[str, int]] = {}
    for kind in STREAMS[task]:
        source = inputs[SOURCE_RECORDS[kind]]
        rows, invalid = streams.build_rows(kind, source.records, outcomes)
        if task == "main":
            _validate_main(rows, source)
        data = streams.jsonl_bytes(rows)
        streams.write_atomic(out_dir / f"{kind}.jsonl", data, root)
        written[f"{kind}.jsonl"] = hashlib.sha256(data).hexdigest()
        rows_by_kind[kind], invalid_rows[kind] = len(rows), dict(sorted(invalid.items()))

    provenance = {
        "version": PROVENANCE_VERSION, "spec": "009", "task": task, "split": split, "system": recipe.system,
        "variant": variant if task == "main" else None,
        "selected_variant": task == "transfer" or variant == recipe.main_prompt,
        "conditions": list(conditions) if conditions else None, "sample": "all",
        "recipe": {"path": _relative(recipe.path, root), "text_sha256": recipe.text_sha256},
        "backend": recipe.backend, "model": recipe.model_ref, "backend_options": dict(recipe.options),
        "decoding": dict(recipe.decoding),
        "prompt": {"path": _relative(prompt_path, root), "template_sha256": text_sha256(prompt_path),
                   "rendered_sha256": instructions.sha256, "framing_version": prompt.FRAMING_VERSION},
        "slot_keys_sha256": text_sha256(recipe.slot_keys) if task == "main" else None,
        **_schema_provenance(task, calls),
        "inputs": {kind: {"path": _relative(recipe.input_path(split, kind), root),
                          "file_sha256": stream.file_sha256, "records": len(stream.records)}
                   for kind, stream in inputs.items()},
        "code": {"source_sha256": source_sha256(), **git_state(cwd=REPO_ROOT)},
        "started": started, "finished": _now(),
        "counts": {"distinct_inputs": len(calls), "cache_hits": len(calls) - len(misses),
                   "calls": stats.calls, "batches": stats.batches, "retries": stats.retries,
                   "rate_limited": stats.rate_limited, "transport_errors": stats.transport_errors,
                   "invalid_calls_by_reason": dict(sorted(invalid_calls.items())),
                   "invalid_rows_by_reason": invalid_rows, "rows": rows_by_kind},
        "usage": {"all_answers": dict(sorted(all_usage.items())), "new_calls": dict(sorted(new_usage.items()))},
        "preflight": report.as_dict() if report else None,
        "spend": {"estimated_usd": None, "reserved_usd": None, "actual_usd": None,
                  "note": "local backend: no spend ledger"},
        "cache": {"path": _relative(cache_path, root), "entries": cache_entries},
        "outputs": written,
    }
    streams.write_atomic(out_dir / f"provenance.{task}.json", streams.json_bytes(provenance), root)
    log.info("%s/%s done: %d rows written, %d calls, %d retries, %d invalid calls", task, split,
             sum(rows_by_kind.values()), stats.calls, stats.retries, sum(invalid_calls.values()))
    return provenance


def default_counter_factory(recipe: Recipe) -> TokenCounter | None:
    return backends.backend_class(recipe.backend).counter_from_recipe(recipe)


def size(recipe: Recipe, *, split: str, root: Path = REPO_ROOT,
         counter_factory: CounterFactory = default_counter_factory) -> dict[str, Any]:
    """Count every prompt each variant (and the transfer prompt) would send on ``split``, with the
    backend's own tokenizer, and report the ``max_model_len`` the recipe needs (FR5a sizing).

    It makes no calls and touches no cache. The report holds counts only, so it is safe to print.
    """
    _check_request(recipe, split, "main", None, None)
    counter = counter_factory(recipe)
    if counter is None:
        raise RunRefused("this backend has no local context window to size")
    max_model_len = recipe.options.get("max_model_len")
    if type(max_model_len) is not int:
        raise RunRefused("backend_options.max_model_len is required for sizing")
    slot_keys = schema.load_slot_keys(recipe.slot_keys)
    main_inputs = _load_inputs(recipe, split, "main", None).values()
    prompts: dict[str, list[Call]] = {
        variant: plan_calls(recipe, "main", prompt.main_instructions(recipe.prompt_path(variant), slot_keys),
                            slot_keys, main_inputs)
        for variant in recipe.variants}
    if "transfer" in recipe.inputs.get(split, {}):
        transfer = _load_inputs(recipe, split, "transfer", None).values()
        prompts["transfer"] = plan_calls(recipe, "transfer", prompt.transfer_instructions(recipe.transfer_prompt),
                                         (), transfer)
    variants = {}
    for name, calls in prompts.items():
        report = measure([call.messages for call in calls], counter, max_tokens=recipe.max_tokens,
                         max_model_len=max_model_len)
        variants[name] = {**report.as_dict(),
                          "required_max_model_len": required_model_len(report.max_prompt_tokens, recipe.max_tokens)}
    required = max(entry["required_max_model_len"] for entry in variants.values())
    return {"split": split, "system": recipe.system, "model": recipe.model_ref, "max_tokens": recipe.max_tokens,
            "recipe_max_model_len": max_model_len, "required_max_model_len": required,
            "fits": all(entry["over_limit"] == 0 for entry in variants.values()), "prompts": variants}


def plan_calls(recipe: Recipe, task: str, instructions: prompt.Instructions, slot_keys: Sequence[str],
               inputs: Sequence[InputStream] | Any) -> list[Call]:
    """One call per distinct input hash, sorted by hash; each with its cache key (FR2, FR6)."""
    shared = schema.main_schema(slot_keys) if task == "main" else None
    shared_sha = schema.schema_sha256(shared) if shared is not None else None
    calls = []
    for input_sha, record in distinct_inputs(inputs).items():
        if task == "main":
            messages, call_schema, schema_sha = prompt.render_main(instructions, record), shared, shared_sha
        else:
            call_schema = schema.transfer_schema(record["candidates"])
            messages, schema_sha = prompt.render_transfer(instructions, record), schema.schema_sha256(call_schema)
        key = KeyParts(task, recipe.backend, recipe.model_ref, instructions.sha256, recipe.decoding,
                       schema_sha, input_sha).key
        calls.append(Call(key, record, tuple(messages), call_schema, schema_sha))
    return calls


def output_dir(recipe: Recipe, split: str, task: str, variant: str, conditions: Sequence[str] | None,
               root: Path = REPO_ROOT) -> Path:
    if task == "transfer" or (variant == recipe.main_prompt and not conditions):
        return under_outputs(Path("outputs/stage2") / recipe.system / split, root)
    return under_outputs(Path("outputs/llm/selection") / recipe.system / variant / split, root)


def _check_request(recipe: Recipe, split: str, task: str, variant: str | None,
                   conditions: Sequence[str] | None) -> tuple[str, tuple[str, ...] | None]:
    if split not in SPLITS:
        raise RunRefused(f"split must be one of {list(SPLITS)}")
    if split == "test":
        raise RunRefused(TEST_REFUSED)
    if task not in TASKS:
        raise RunRefused(f"task must be one of {list(TASKS)}")
    if recipe.paid:
        raise RunRefused("paid backends need the spend ledger (spec 009 T7), which is not built yet")
    if task == "transfer" and (variant is not None or conditions):
        raise RunRefused("the transfer task has one fixed prompt and one condition; drop --variant/--conditions")
    variant = variant or recipe.main_prompt
    recipe.prompt_path(variant)
    if conditions is None or len(conditions) == 0:
        return variant, None
    if len(set(conditions)) != len(conditions) or set(conditions) - set(CONDITIONS):
        raise RunRefused(f"conditions must be distinct values from {list(CONDITIONS)}")
    return variant, tuple(c for c in CONDITIONS if c in conditions)


def _load_inputs(recipe: Recipe, split: str, task: str, conditions: Sequence[str] | None) -> dict[str, InputStream]:
    if task == "transfer":
        return {"transfer": load_stream(recipe.input_path(split, "transfer"), "transfer")}
    routed = load_stream(recipe.input_path(split, "routed"), "routed")
    oracle = load_stream(recipe.input_path(split, "oracle"), "oracle")
    check_oracle_subset(routed, oracle)
    if conditions:
        routed, oracle = (InputStream(s.kind, tuple(r for r in s.records if r["condition"] in conditions), s.file_sha256)
                          for s in (routed, oracle))
        if not routed.records:
            raise RunRefused("no input records under the requested conditions")
    return {"routed": routed, "oracle": oracle}


def _preflight(recipe: Recipe, backend: Backend, calls: Sequence[Call]) -> LengthReport | None:
    """FR5a over every prompt of the run (not just the misses): the worst case, before any call."""
    counter = backend.token_counter()
    if counter is None:
        return None
    max_model_len = recipe.options.get("max_model_len")
    if type(max_model_len) is not int:
        raise RunRefused("backend_options.max_model_len is required for a backend with a local context window")
    return require_fit([call.messages for call in calls], counter, max_tokens=recipe.max_tokens,
                       max_model_len=max_model_len)


def _call_misses(backend: Backend, misses: Sequence[Call], cache: ResponseCache, batch_size: int, *,
                 error_log: ErrorLog, stats: CallStats, sleep: Callable[[float], None], rng: random.Random,
                 usage: Counter[str], progress_every: int) -> None:
    """Send misses in batches; each batch is in the cache (fsynced) before the next is sent."""
    began, done, next_report = time.monotonic(), 0, progress_every
    for start in range(0, len(misses), batch_size):
        batch = [Request(call.key, call.messages, call.schema) for call in misses[start:start + batch_size]]
        responses = generate_with_retry(backend, batch, error_log=error_log, stats=stats, sleep=sleep, rng=rng)
        cache.append([new_entry(r.key, r.raw, r.finish_reason, r.usage) for r in responses])
        for response in responses:
            usage.update(response.usage)
        done += len(batch)
        if done >= next_report or done == len(misses):
            rate = done / max(time.monotonic() - began, 1e-9)
            log.info("progress: %d/%d calls answered, %d retries, %d transport errors, %.1f calls/s",
                     done, len(misses), stats.retries, stats.transport_errors, rate)
            next_report = (done // progress_every + 1) * progress_every


def _parse(task: str, calls: Sequence[Call], cache: ResponseCache, slot_keys: Sequence[str]
           ) -> tuple[dict[str, streams.Outcome], Counter[str], Counter[str]]:
    """Strict parse of every answer (FR5): one outcome per input hash, invalid counts by reason."""
    allowed = frozenset(slot_keys)
    outcomes: dict[str, streams.Outcome] = {}
    invalid: Counter[str] = Counter()
    usage: Counter[str] = Counter()
    for call in calls:
        entry = cache.get(call.key)
        if entry is None:
            raise RunStopped("a planned call has no cached answer after the run; rerun to resume")
        if task == "main":
            outcome = schema.parse_main(entry.raw, entry.finish_reason, allowed)
        else:
            outcome = schema.parse_transfer(entry.raw, entry.finish_reason, call.record["candidates"])
        if isinstance(outcome, schema.Invalid):
            invalid[outcome.reason] += 1
        usage.update(entry.usage)
        outcomes[call.record["input_sha256"]] = outcome
    return outcomes, invalid, usage


def _validate_main(rows: Sequence[dict[str, Any]], stream: InputStream) -> None:
    """The spec 005 validator: exactly one typed row per (condition, example) before anything is written."""
    expected: dict[str, set[str]] = {}
    for record in stream.records:
        expected.setdefault(record["condition"], set()).add(record["example_id"])
    validate_predictions(rows, expected)


def _schema_provenance(task: str, calls: Sequence[Call]) -> dict[str, Any]:
    if task == "main":
        return {"schema_sha256": calls[0].schema_sha256, "schema_per_record": False}
    digests = "\n".join(sorted(call.schema_sha256 for call in calls))
    return {"schema_sha256": hashlib.sha256(digests.encode("ascii")).hexdigest(), "schema_per_record": True}


def _relative(path: Path, root: Path) -> str:
    resolved = path.resolve()
    return resolved.relative_to(root.resolve()).as_posix() if resolved.is_relative_to(root.resolve()) else path.name


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="run one task on one split")
    run_parser.add_argument("--recipe", type=Path, required=True)
    run_parser.add_argument("--split", choices=SPLITS, required=True)
    run_parser.add_argument("--task", choices=TASKS, required=True)
    run_parser.add_argument("--variant", help="main-task prompt variant (default: the recipe's selected one)")
    run_parser.add_argument("--conditions", nargs="+", choices=CONDITIONS, help="dev prompt selection only")
    run_parser.add_argument("--progress-every", type=int, default=PROGRESS_EVERY)
    size_parser = commands.add_parser("size", help="count prompt tokens and report the max_model_len needed")
    size_parser.add_argument("--recipe", type=Path, required=True)
    size_parser.add_argument("--split", choices=SPLITS, required=True)
    args = parser.parse_args(argv)
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                            format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        if args.split == "test":
            raise RunRefused(TEST_REFUSED)  # before the recipe or any input is even read
        if args.command == "size":
            print(json.dumps(size(load_recipe(args.recipe), split=args.split), indent=2, sort_keys=True))
            return 0
        if args.progress_every < 1:
            raise RunRefused("--progress-every must be positive")
        recipe = load_recipe(args.recipe)
        provenance = run(recipe, split=args.split, task=args.task, variant=args.variant,
                         conditions=args.conditions, progress_every=args.progress_every)
    except (RunStopped, RunRefused, RecipeError, InputError, PreflightError, CacheError) as error:
        print(f"LLM {args.command} stopped: {error}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as error:
        print(f"LLM {args.command} failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    counts = provenance["counts"]
    print(f"LLM {args.task} run on {args.split}: {counts['rows']} rows, {counts['calls']} calls, "
          f"{counts['cache_hits']} cache hits, {sum(counts['invalid_calls_by_reason'].values())} invalid calls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
