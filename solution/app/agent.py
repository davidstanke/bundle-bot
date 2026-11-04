"""BundleBot — ADK 2.0 Diamond Graph Workflow for B2B Tech Kit & Margin Optimization."""

from __future__ import annotations

import os
from typing import Any

import google.auth
from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.events.event import Event
from google.adk.workflow import JoinNode, Workflow, node
from google.genai import types

from app.catalog_tools import (
    KitRequirements,
    SelectedKit,
    check_warehouse_stock as run_warehouse_stock_check,
    get_catalog_summary,
    optimize_margins as run_margin_optimization,
    select_default_kit_skus,
    validate_compatibility as run_compatibility_check,
)

# Use Google Cloud Application Default Credentials (ADC) via Vertex AI
# rather than a Gemini API key.
try:
  _, _default_project = google.auth.default()
  if _default_project:
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", _default_project)
except Exception:
  pass
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")

MODEL_ID = "gemini-2.5-flash"

parse_requirements = LlmAgent(
    name="parse_requirements",
    model=MODEL_ID,
    description="Parses B2B reseller kit requirements from natural language.",
    instruction=(
        "Extract the structured B2B kit requirements from the user's request.\n"
        "- Set `quantity` to the number of kits/new hires requested (default 24 if unspecified).\n"
        "- Set `tier` to 'value', 'standard', or 'performance' (default 'standard').\n"
        "- Set `destination` to the shipping city or region (default 'Austin').\n"
        "- Set `budget_usd` to the numeric total budget if mentioned (e.g. 45000.0 for '$45k' or '$45,000'), else null.\n"
        "- Set `include_headset` to true only if a headset, ANC audio, or webcam is explicitly requested."
    ),
    output_schema=KitRequirements,
    output_key="requirements",
)

build_kit = LlmAgent(
    name="build_kit",
    model=MODEL_ID,
    description="Selects compatible hardware and software SKUs from data/catalog.json.",
    instruction=(
        "You are configuring a B2B hardware + software kit from `data/catalog.json`.\n"
        "Parsed requirements: {requirements}\n\n"
        "Call `select_default_kit_skus` (and optionally `get_catalog_summary`) to pick "
        "a complete, power-compatible set of SKUs matching the requested tier.\n"
        "Always include laptop, dock, monitor, peripherals (`IM-PER-COMBO`), endpoint "
        "security (`IM-SW-SEC365`), and 3-year NBD warranty (`IM-WAR-NBD3Y`).\n"
        "Return the structured `SelectedKit` matching the parsed `quantity`, `tier`, "
        "`destination`, and `budget_usd`."
    ),
    tools=[select_default_kit_skus, get_catalog_summary],
    output_schema=SelectedKit,
    output_key="selected_kit",
)


@node(name="validate_compatibility")
def validate_compatibility(node_input: dict[str, Any] | SelectedKit) -> Event:
  """Parallel branch 1: Verify USB-C dock wattage, display ports, and software seat bounds."""
  report = run_compatibility_check(node_input)
  payload = report.model_dump()
  return Event(
      content=types.Content(
          role="model",
          parts=[types.Part.from_text(text=f"[Compatibility] {report.summary}")],
      ),
      output=payload,
      state={"compatibility_report": payload},
  )


@node(name="check_warehouse_stock")
def check_warehouse_stock(node_input: dict[str, Any] | SelectedKit) -> Event:
  """Parallel branch 2: Check regional warehouse stock for all selected SKUs."""
  report = run_warehouse_stock_check(node_input)
  payload = report.model_dump()
  return Event(
      content=types.Content(
          role="model",
          parts=[types.Part.from_text(text=f"[Warehouse Stock] {report.summary}")],
      ),
      output=payload,
      state={"stock_report": payload},
  )


@node(name="optimize_margins")
def optimize_margins(node_input: dict[str, Any] | SelectedKit) -> Event:
  """Parallel branch 3: Compute reseller margin and check next volume-tier upsell math."""
  report = run_margin_optimization(node_input)
  payload = report.model_dump()
  return Event(
      content=types.Content(
          role="model",
          parts=[types.Part.from_text(text=f"[Margin Optimizer] {report.summary}")],
      ),
      output=payload,
      state={"margin_report": payload},
  )


join_checks = JoinNode(name="join_checks")

format_quote = LlmAgent(
    name="format_quote",
    model=MODEL_ID,
    description="Synthesizes the parallel validation, stock, and margin checks into a B2B partner quote.",
    instruction=(
        "You are BundleBot, a B2B channel distribution advisor. Present a clear, "
        "executive-ready partner quote using the verified results from the parallel workflow:\n"
        "- Selected Kit: {selected_kit}\n"
        "- Technical & Power Compatibility: {compatibility_report}\n"
        "- Regional Warehouse Inventory: {stock_report}\n"
        "- Pricing, Reseller Margin & Volume-Tier Upsell: {margin_report}\n\n"
        "Include:\n"
        "1. **Selected SKU Bill of Materials** (SKU codes, tier, and quantity).\n"
        "2. **Technical & Power Compatibility Verdict** (dock PD watts vs. laptop watts, display ports, license seats).\n"
        "3. **Regional Warehouse Fulfillment Status** (warehouse name and stock confirmation).\n"
        "4. **Pricing & Partner Margin Summary** (unit MSRP, applied volume discount tier, customer total vs. budget, and reseller margin dollars/percentage).\n"
        "5. **Volume-Tier Upsell Recommendation** (if `upsell_recommended` is true, highlight how bumping to the next tier threshold—e.g. 25 units for Gold Partner 12% off—lowers the customer's total price while increasing reseller margin dollars)."
    ),
)

root_agent = Workflow(
    name="bundle_bot_workflow",
    description=(
        "B2B IT Kit Builder & Margin Optimizer with sequential SKU selection "
        "and 3-way parallel compatibility, warehouse stock, and margin checks."
    ),
    edges=[
        ("START", parse_requirements),
        (parse_requirements, build_kit),
        (
            build_kit,
            (validate_compatibility, check_warehouse_stock, optimize_margins),
        ),
        (
            (validate_compatibility, check_warehouse_stock, optimize_margins),
            join_checks,
        ),
        (join_checks, format_quote),
    ],
)

app = App(
    name="bundle_bot",
    root_agent=root_agent,
)
