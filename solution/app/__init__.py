"""BundleBot ADK 2.0 package."""

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
  if name == "agent":
    from . import agent as _agent

    return _agent
  if name == "app":
    from .agent import app as _app

    return _app
  raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["agent", "app"]
