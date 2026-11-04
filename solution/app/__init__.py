"""BundleBot ADK 2.0 package."""

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
  if name == "agent":
    from . import agent as _agent

    return _agent
  raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["agent"]
