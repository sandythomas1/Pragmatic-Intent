"""Strict TOML run configs: one resolved config fully determines one run.

Unknown keys are errors, so a typo cannot silently fall back to a default.
Command-line overrides are applied before validation, and the resolved config is
written next to every run's outputs and hashed into its result record.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

from src.data.direct_dataset import CONDITIONS
from src.stage1.data import POLICIES

SPLITS = ("train", "dev", "test")
KINDS = ("tfidf", "encoder")


@dataclass(frozen=True)
class DataConfig:
    train_condition: str
    items: str = "data/interim/direct/items.jsonl"
    dialogues: str = "data/interim/direct/dialogues.jsonl"
    policy: str = "direct_variants_v1"
    train_split: str = "train"
    eval_split: str = "dev"
    eval_conditions: tuple[str, ...] = CONDITIONS
    levels: tuple[str, ...] = ()  # human level CSVs, joined as an evaluation slice only


@dataclass(frozen=True)
class TfidfConfig:
    use_context: bool
    ngram_max: int = 2
    min_df: int = 2
    c: float = 1.0
    max_iter: int = 2000


@dataclass(frozen=True)
class EncoderConfig:
    pretrained: str
    revision: str = "main"  # pin a Hugging Face commit for the final runs
    max_length: int = 512
    batch_size: int = 32  # effective batch; fixed across machines
    micro_batch_size: int = 16  # per step; lower it on small GPUs, accumulation compensates
    eval_batch_size: int = 64
    learning_rate: float = 2e-5
    epochs: int = 2
    warmup_ratio: float = 0.06
    weight_decay: float = 0.01
    max_grad_norm: float = 1.0
    bf16: bool = True
    gradient_checkpointing: bool = False

    @property
    def grad_accum_steps(self) -> int:
        return self.batch_size // self.micro_batch_size


@dataclass(frozen=True)
class RunConfig:
    name: str
    kind: str
    data: DataConfig
    tfidf: TfidfConfig | None = None
    encoder: EncoderConfig | None = None
    bootstrap_samples: int = 1000
    bootstrap_seed: int = 20261006

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def sha256(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True).encode()).hexdigest()


def _section(cls: type, table: dict[str, Any], name: str) -> Any:
    known = {f.name for f in fields(cls)}
    unknown = set(table) - known
    if unknown:
        raise ValueError(f"unknown keys in [{name}]: {sorted(unknown)}")
    values = {key: tuple(value) if isinstance(value, list) else value for key, value in table.items()}
    try:
        return cls(**values)
    except TypeError as exc:
        raise ValueError(f"[{name}]: {exc}") from None


def validate(config: RunConfig, allow_test: bool = False) -> None:
    data = config.data
    if config.kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if data.policy not in POLICIES:
        raise ValueError(f"policy must be one of {POLICIES}")
    if data.train_split not in SPLITS or data.eval_split not in SPLITS:
        raise ValueError(f"splits must be among {SPLITS}")
    if data.train_split == data.eval_split:
        raise ValueError("train and eval splits must differ (splits are grouped by dialogue)")
    if data.eval_split == "test" and not allow_test:
        raise ValueError("evaluating on test needs --allow-test; reserve it for the frozen test run")
    conditions = (data.train_condition, *data.eval_conditions)
    if not data.eval_conditions or any(c not in CONDITIONS for c in conditions):
        raise ValueError(f"conditions must be among {CONDITIONS}")
    if len(set(data.eval_conditions)) != len(data.eval_conditions):
        raise ValueError("duplicate eval condition")
    if config.bootstrap_samples < 1:
        raise ValueError("bootstrap_samples must be positive")
    section = config.tfidf if config.kind == "tfidf" else config.encoder
    if section is None:
        raise ValueError(f"kind = {config.kind!r} needs a [{config.kind}] table")
    if config.tfidf is not None and config.tfidf.use_context and data.train_condition == "none":
        raise ValueError("tfidf use_context needs a train condition that has context")
    if config.encoder is not None:
        encoder = config.encoder
        if min(encoder.batch_size, encoder.micro_batch_size, encoder.eval_batch_size, encoder.epochs) < 1:
            raise ValueError("batch sizes and epochs must be positive")
        if encoder.batch_size % encoder.micro_batch_size:
            raise ValueError("batch_size must be a multiple of micro_batch_size")


def load_config(path: Path, overrides: dict[str, dict[str, Any]] | None = None,
                allow_test: bool = False) -> RunConfig:
    """Parse ``path``; ``overrides`` maps a table name to replacement values."""
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    for table, values in (overrides or {}).items():
        raw.setdefault(table, {}).update({k: v for k, v in values.items() if v is not None})
    run = raw.pop("run", {})
    unknown = set(raw) - {"data", "tfidf", "encoder"}
    if unknown:
        raise ValueError(f"unknown tables: {sorted(unknown)}")
    if "name" not in run or "kind" not in run:
        raise ValueError("[run] needs name and kind")
    unknown_run = set(run) - {"name", "kind", "bootstrap_samples", "bootstrap_seed"}
    if unknown_run:
        raise ValueError(f"unknown keys in [run]: {sorted(unknown_run)}")
    config = RunConfig(
        data=_section(DataConfig, raw.get("data", {}), "data"),
        tfidf=_section(TfidfConfig, raw["tfidf"], "tfidf") if "tfidf" in raw else None,
        encoder=_section(EncoderConfig, raw["encoder"], "encoder") if "encoder" in raw else None,
        **run,
    )
    validate(config, allow_test)
    return config
