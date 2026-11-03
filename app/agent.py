"""Starter stub for BundleBot (ADK 2.0 Workflow).

On the `main` branch, this stub awaits `/grill-me` and `/teamwork-preview`
to implement the full B2B kit-builder workflow over `data/catalog.json`.
Switch to the `solution` branch (`git checkout solution`) for the complete build.
"""

from __future__ import annotations

from google.adk.apps import App
from google.adk.workflow import Workflow


def greet_partner(node_input: str) -> str:
  """Starter placeholder node."""
  return (
      "BundleBot starter stub ready. Run `/grill-me` and `/teamwork-preview` "
      "or `git checkout solution` for the full ADK 2.0 B2B Kit Workflow."
  )


root_agent = Workflow(
    name="bundle_bot_workflow",
    edges=[("START", greet_partner)],
)

app = App(
    name="bundle_bot",
    root_agent=root_agent,
)
