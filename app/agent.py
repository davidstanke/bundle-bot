"""Starter stub for BundleBot.

On the `main` branch, this stub awaits `/plan`, `/grill-me`, and `/teamwork-preview`
to implement the full B2B kit-builder pipeline over `data/catalog.json`.
Switch to the `solution` branch (`git checkout solution`) for the complete build.
"""

from __future__ import annotations

from google.adk.agents import Agent
from google.adk.apps import App


def greet_partner() -> str:
  """Starter placeholder tool."""
  return (
      "BundleBot starter stub ready. Run `/plan`, `/grill-me`, and "
      "`/teamwork-preview` or `git checkout solution` for the full "
      "B2B Kit Builder."
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
