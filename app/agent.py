"""Starter stub for BundleBot.

This starter stub awaits `/plan`, `/grill-me`, and `/teamwork-preview`
to implement the full B2B kit-builder pipeline over `data/catalog.json`.
"""

from __future__ import annotations

import os
import google.auth

# Default to Google Cloud Application Default Credentials (ADC) via Vertex AI
if (
    "GOOGLE_GENAI_USE_VERTEXAI" not in os.environ
    and "GOOGLE_GENAI_USE_ENTERPRISE" not in os.environ
):
  os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"

os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")
if "GOOGLE_CLOUD_PROJECT" not in os.environ:
  try:
    _, _default_project = google.auth.default()
    if _default_project:
      os.environ.setdefault("GOOGLE_CLOUD_PROJECT", _default_project)
  except Exception:
    pass

from google.adk.agents import Agent
from google.adk.apps import App


def greet_partner() -> str:
  """Starter placeholder tool."""
  return (
      "BundleBot starter stub ready. Run `/plan`, `/grill-me`, and "
      "`/teamwork-preview` to build the full B2B Kit Builder."
  )


root_agent = Agent(
    name="bundle_bot",
    model="gemini-2.5-flash",
    description="Starter stub for BundleBot B2B IT Kit Builder.",
    instruction=(
        "You are BundleBot, a B2B IT kit advisor. Call `greet_partner` to "
        "confirm the starter stub is running."
    ),
    tools=[greet_partner],
)

app = App(
    name="bundle_bot",
    root_agent=root_agent,
)
