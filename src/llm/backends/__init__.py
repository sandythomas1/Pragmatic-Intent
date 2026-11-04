"""Backend registry (spec 009 T6, FR7). The recipe's ``backend`` picks one; imports are lazy, so the
stdlib core never imports vLLM or a provider SDK unless that backend is actually constructed."""

from __future__ import annotations

import importlib

from src.llm.backends.base import Backend

_REGISTRY = {
    "fake": ("src.llm.backends.fake", "FakeBackend"),
    "vllm": ("src.llm.backends.vllm_backend", "VllmBackend"),
    "anthropic": ("src.llm.backends.anthropic_backend", "AnthropicBackend"),
    "openai": ("src.llm.backends.openai_backend", "OpenAIBackend"),
}
NAMES = tuple(_REGISTRY)
PAID = frozenset({"anthropic", "openai"})


def backend_class(name: str) -> type[Backend]:
    """Import and return the named backend class; refuses unknown names."""
    if name not in _REGISTRY:
        raise ValueError(f"unknown backend; expected one of {list(NAMES)}")
    module_name, class_name = _REGISTRY[name]
    cls = getattr(importlib.import_module(module_name), class_name)
    if not (isinstance(cls, type) and issubclass(cls, Backend)) or cls.name != name:
        raise TypeError("registry entry does not name a matching Backend subclass")
    return cls
