"""LLM run recipes (spec 009 T8, FR7, FR8): one TOML file fixes everything a run depends on.

A recipe names the system (the output directory), the backend and exact model, the decoding
parameters, the prompt variants and which one is selected, the slot-key vocabulary, the input files
per split and backend-only options. The backend is chosen here, never by data (FR7).

Everything is checked on load:
- unknown keys are refused;
- every path is repository-relative and stays inside the repository;
- decoding is greedy (temperature 0) with a bounded ``max_tokens``;
- option names that look like credentials are refused. Keys come only from the environment
  (spec 009 Security), and a recipe is committed and copied into provenance.

The recipe file's LF-normalized SHA-256 (the freeze's ``text_sha256``) goes into provenance.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.data.freeze import text_sha256
from src.llm import backends
from src.llm.paths import REPO_ROOT

RECIPE_VERSION = "llm-recipe-v1"
SPLITS = ("dev", "test")
INPUT_KINDS = ("routed", "oracle", "transfer")
MAX_RECIPE_BYTES = 64_000
MAX_TOKENS_LIMIT = 4096
MAX_BATCH = 4096
_TOP = frozenset({"version", "system", "backend", "model_id", "batch_size", "slot_keys", "decoding",
                  "prompts", "inputs", "backend_options"})
_PROMPTS = frozenset({"main", "transfer", "variants"})
_SYSTEM = re.compile(r"[a-z0-9][a-z0-9.\-]{0,63}\Z")
_VARIANT = re.compile(r"[a-z][a-z0-9_]{0,15}\Z")
_OPTION = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_MODEL = re.compile(r"[A-Za-z0-9._/\-]{1,160}\Z")
_REVISION = re.compile(r"[A-Za-z0-9._\-]{1,64}\Z")
_CREDENTIAL = re.compile(r"key|token|secret|password|credential|auth", re.IGNORECASE)
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_VLLM_REQUIRED = frozenset({"revision", "max_model_len", "gpu_memory_utilization"})
_VLLM_OPTIONAL = frozenset({"max_num_seqs"})
MAX_MODEL_LEN_LIMIT = 131_072
MAX_GPU_SHARE = 0.95
Scalar = str | int | float | bool


class RecipeError(ValueError):
    """The recipe is malformed; messages name fields, never file content."""


@dataclass(frozen=True)
class Recipe:
    path: Path
    text_sha256: str
    system: str
    backend: str
    model_id: str
    batch_size: int
    slot_keys: Path
    decoding: Mapping[str, Scalar]
    main_prompt: str
    variants: Mapping[str, Path]
    transfer_prompt: Path
    inputs: Mapping[str, Mapping[str, Path]]
    options: Mapping[str, Scalar]

    @property
    def model_ref(self) -> str:
        """The model identity in the cache key and provenance: the ID plus any pinned revision, so
        an answer is never reused across model revisions."""
        revision = self.options.get("revision")
        return f"{self.model_id}@{revision}" if revision else self.model_id

    @property
    def max_tokens(self) -> int:
        return int(self.decoding["max_tokens"])

    @property
    def paid(self) -> bool:
        return self.backend in backends.PAID

    def input_path(self, split: str, kind: str) -> Path:
        try:
            return self.inputs[split][kind]
        except KeyError:
            raise RecipeError(f"the recipe declares no {kind} inputs for split {split}") from None

    def prompt_path(self, variant: str) -> Path:
        if variant not in self.variants:
            raise RecipeError(f"unknown prompt variant; the recipe declares {sorted(self.variants)}")
        return self.variants[variant]


def load_recipe(path: Path, root: Path = REPO_ROOT) -> Recipe:
    """Read and validate a recipe; every path in it resolves against ``root``."""
    file = _inside(path, root, "recipe")
    try:
        with file.open("rb") as handle:
            data = handle.read(MAX_RECIPE_BYTES + 1)
        if len(data) > MAX_RECIPE_BYTES:
            raise RecipeError("recipe file is too large")
        document = tomllib.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        raise RecipeError("recipe is not valid UTF-8 TOML") from None
    _exact(document, _TOP, "recipe")
    if document["version"] != RECIPE_VERSION:
        raise RecipeError(f"recipe version must be {RECIPE_VERSION}")
    system, backend, model_id = document["system"], document["backend"], document["model_id"]
    if not isinstance(system, str) or not _SYSTEM.fullmatch(system) or system == "hybrid":
        raise RecipeError("system must be a short lowercase name (not 'hybrid', the composer's)")
    if backend not in backends.NAMES:
        raise RecipeError(f"backend must be one of {list(backends.NAMES)}")
    if not isinstance(model_id, str) or not _MODEL.fullmatch(model_id) or model_id.lower().endswith("latest"):
        raise RecipeError("model_id must be an exact model name, not a floating alias")
    batch_size = document["batch_size"]
    if type(batch_size) is not int or not 1 <= batch_size <= MAX_BATCH:
        raise RecipeError(f"batch_size must be an integer in 1..{MAX_BATCH}")
    prompts = document["prompts"]
    _exact(prompts, _PROMPTS, "prompts")
    variants = prompts["variants"]
    if not isinstance(variants, dict) or not variants or not all(_VARIANT.fullmatch(name) for name in variants):
        raise RecipeError("prompts.variants must name at least one variant (short lowercase names)")
    if prompts["main"] not in variants:
        raise RecipeError("prompts.main must name one of prompts.variants")
    decoding, options = _decoding(document["decoding"]), _options(document["backend_options"])
    if backend == "vllm":
        _check_vllm_options(options, int(decoding["max_tokens"]))
    return Recipe(
        path=file, text_sha256=text_sha256(file), system=system, backend=backend, model_id=model_id,
        batch_size=batch_size, slot_keys=_inside(document["slot_keys"], root, "slot_keys"),
        decoding=decoding, main_prompt=prompts["main"],
        variants={name: _inside(value, root, f"prompts.variants.{name}") for name, value in sorted(variants.items())},
        transfer_prompt=_inside(prompts["transfer"], root, "prompts.transfer"),
        inputs=_inputs(document["inputs"], root), options=options)


def _decoding(decoding: Any) -> dict[str, Scalar]:
    values = _scalars(decoding, "decoding")
    if values.get("temperature") != 0:
        raise RecipeError("decoding.temperature must be 0 (FR7: greedy or temperature-0 decoding)")
    max_tokens = values.get("max_tokens")
    if type(max_tokens) is not int or not 1 <= max_tokens <= MAX_TOKENS_LIMIT:
        raise RecipeError(f"decoding.max_tokens must be an integer in 1..{MAX_TOKENS_LIMIT}")
    return values


def _options(options: Any) -> dict[str, Scalar]:
    values = _scalars(options, "backend_options")
    if any(_CREDENTIAL.search(name) for name in values):
        raise RecipeError("backend_options must not carry credentials; keys come from the environment only")
    revision = values.get("revision")
    if revision is not None and (not isinstance(revision, str) or not _REVISION.fullmatch(revision)):
        raise RecipeError("backend_options.revision must be a short commit or tag name")
    return values


def _check_vllm_options(options: Mapping[str, Scalar], max_tokens: int) -> None:
    """Local weights are pinned to an exact commit, never a branch or tag, which can move (FR7, T12).
    The context window and memory share are bounded here; whether every prompt fits is the
    preflight's job, before any call."""
    names = set(options)
    if not _VLLM_REQUIRED <= names or names - _VLLM_REQUIRED - _VLLM_OPTIONAL:
        raise RecipeError(f"vllm backend_options must be {sorted(_VLLM_REQUIRED)} "
                          f"plus optionally {sorted(_VLLM_OPTIONAL)}")
    if not isinstance(options["revision"], str) or not _COMMIT.fullmatch(options["revision"]):
        raise RecipeError("vllm backend_options.revision must be a full 40-character commit hash")
    max_model_len = options["max_model_len"]
    if type(max_model_len) is not int or not max_tokens < max_model_len <= MAX_MODEL_LEN_LIMIT:
        raise RecipeError(f"vllm backend_options.max_model_len must be an integer above max_tokens "
                          f"and at most {MAX_MODEL_LEN_LIMIT}")
    share = options["gpu_memory_utilization"]
    if type(share) is not float or not 0 < share <= MAX_GPU_SHARE:
        raise RecipeError(f"vllm backend_options.gpu_memory_utilization must be a float in (0, {MAX_GPU_SHARE}]")
    seqs = options.get("max_num_seqs")
    if seqs is not None and (type(seqs) is not int or not 1 <= seqs <= 1024):
        raise RecipeError("vllm backend_options.max_num_seqs must be an integer in 1..1024")


def _scalars(table: Any, name: str) -> dict[str, Scalar]:
    if not isinstance(table, dict):
        raise RecipeError(f"{name} must be a table")
    for key, value in table.items():
        if not _OPTION.fullmatch(key):
            raise RecipeError(f"{name} keys must be short lowercase names")
        if not isinstance(value, (str, int, float, bool)) or (isinstance(value, str) and len(value) > 200):
            raise RecipeError(f"{name}.{key} must be a short scalar")
    return dict(sorted(table.items()))


def _inputs(inputs: Any, root: Path) -> dict[str, dict[str, Path]]:
    if not isinstance(inputs, dict) or not inputs or set(inputs) - set(SPLITS):
        raise RecipeError(f"inputs must be tables named from {list(SPLITS)}")
    out: dict[str, dict[str, Path]] = {}
    for split, files in sorted(inputs.items()):
        if not isinstance(files, dict) or not files or set(files) - set(INPUT_KINDS):
            raise RecipeError(f"inputs.{split} keys must come from {list(INPUT_KINDS)}")
        if ("routed" in files) != ("oracle" in files):
            raise RecipeError(f"inputs.{split} needs routed and oracle together")
        out[split] = {kind: _inside(value, root, f"inputs.{split}.{kind}") for kind, value in sorted(files.items())}
    return out


def _exact(table: Any, fields: frozenset[str], name: str) -> None:
    if not isinstance(table, dict) or set(table) != fields:
        raise RecipeError(f"{name}: unknown or missing fields (expected {sorted(fields)})")


def _inside(value: Any, root: Path, name: str) -> Path:
    """A path that resolves inside ``root``. Recipe values must be relative POSIX strings; a ``Path``
    comes from the command line and may be absolute."""
    if isinstance(value, Path):
        path = value
    elif isinstance(value, str) and value and "\\" not in value and len(value) <= 300 and not Path(value).is_absolute():
        path = Path(value)
    else:
        raise RecipeError(f"{name} must be a repository-relative POSIX path")
    target = (path if path.is_absolute() else root / path).resolve()
    if not target.is_relative_to(root.resolve()):
        raise RecipeError(f"{name} must stay inside the repository")
    return target
