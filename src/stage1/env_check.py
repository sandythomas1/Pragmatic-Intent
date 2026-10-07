"""Check that this machine can run the Stage 1 experiments. Run it first on each machine.

    python -m src.stage1.env_check                     # environment, GPU, data files
    python -m src.stage1.env_check --tokenizer microsoft/deberta-v3-base   # also load a tokenizer

Exits 1 if anything blocking fails. Checks the points from the research plan's
Compute section: the torch build must include kernels for this GPU (RTX 50-series
is sm_120 and needs a CUDA 12.8+ build), bf16 must work, and on WSL the repo
should live on the Linux filesystem rather than ``/mnt/c``.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from src.stage1 import provenance

DATA_FILES = ("data/interim/direct/items.jsonl", "data/interim/direct/dialogues.jsonl")


def has_kernels(capability: tuple[int, int], arch_list: Sequence[str]) -> bool:
    """True if a compiled ``sm_XY`` binary runs here: same major, minor no higher.

    PyTorch wheels often ship sm_86 but not sm_89; an RTX 4090 runs the sm_86 code.
    PTX-only (``compute_XY``) entries do not count: they are what fails on sm_120
    with pre-12.8 builds.
    """
    major, minor = capability
    for arch in arch_list:
        if arch.startswith("sm_"):
            digits = arch[3:].rstrip("af")  # e.g. sm_90a
            if digits.isdigit() and int(digits[:-1]) == major and int(digits[-1]) <= minor:
                return True
    return False


def check(argv: Sequence[str] | None = None) -> list[str]:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tokenizer", help="Hugging Face tokenizer to load (needs network on first use)")
    args = parser.parse_args(argv)
    problems: list[str] = []
    env = provenance.environment()
    print(f"python {env['python']} on {env['platform']} (WSL: {env['wsl']})")
    for package, version in env["packages"].items():
        print(f"  {package} {version}")
    if sys.version_info < (3, 12):
        problems.append("Python 3.12+ is required by the pinned environment")
    if env["wsl"] and Path.cwd().resolve().as_posix().startswith("/mnt/"):
        print("WARNING: repo is on a Windows drive; move it under ~/ for much faster I/O")
    for path in DATA_FILES:
        if not Path(path).is_file():
            problems.append(f"missing {path}: run python -m src.data.download_sources, then "
                            "python -m src.data.build_direct_dataset")

    try:
        import torch
    except ImportError:
        problems.append("torch is not installed: uv sync --group gpu")
        return problems
    print(f"torch {torch.__version__}, built for CUDA {torch.version.cuda}")
    if not torch.cuda.is_available():
        problems.append("no CUDA device visible (on WSL: install only the Windows NVIDIA driver, then "
                        "check nvidia-smi inside WSL)")
    else:
        gpu = provenance.gpu_info()
        assert gpu is not None
        print(f"GPU {gpu['name']} {gpu['capability']}, {gpu['memory_gib']} GiB, bf16={gpu['bf16']}")
        built = torch.cuda.get_arch_list()
        if not has_kernels(torch.cuda.get_device_capability(0), built):
            problems.append(f"this torch build has kernels for {built}, none usable on {gpu['capability']}; "
                            "install the cu128 (or newer) build from the pinned environment")
        if not gpu["bf16"]:
            problems.append("bf16 unsupported: the encoder configs assume bf16 autocast")
        else:
            try:
                a = torch.randn(256, 256, device="cuda", dtype=torch.bfloat16)
                torch.cuda.synchronize()
                print(f"bf16 matmul OK (checksum {float((a @ a).float().abs().mean()):.3f})")
            except RuntimeError as exc:
                problems.append(f"bf16 matmul failed: {exc}")

    try:
        import transformers
        print(f"transformers {transformers.__version__}")
        if args.tokenizer:
            tokenizer = transformers.AutoTokenizer.from_pretrained(args.tokenizer)
            print(f"tokenizer {args.tokenizer}: fast={tokenizer.is_fast}")
            if not tokenizer.is_fast:
                problems.append("slow tokenizer loaded; install sentencepiece and protobuf (uv sync --group gpu)")
    except ImportError:
        problems.append("transformers is not installed: uv sync --group gpu")
    except OSError as exc:
        problems.append(f"could not load tokenizer: {exc}")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    problems = check(argv)
    for problem in problems:
        print(f"FAIL: {problem}")
    print("OK: ready to run Stage 1 experiments" if not problems else f"{len(problems)} problem(s) found")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
