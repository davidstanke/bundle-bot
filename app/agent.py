"""BundleBot ADK 2.0 Diamond Graph Workflow Agent."""

from __future__ import annotations

import os

# Default to Google Cloud Application Default Credentials (ADC) via Vertex AI
if (
    "GOOGLE_GENAI_USE_VERTEXAI" not in os.environ
    and "GOOGLE_GENAI_USE_ENTERPRISE" not in os.environ
):
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"

from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.workflow import JoinNode, START, Workflow

from app.catalog_tools import (
    KitRequirements,
    SelectedKit,
    check_warehouse_stock,
    get_catalog_summary,
    optimize_margins,
    select_default_kit_skus,
    validate_compatibility,
)

MODEL_ID = "gemini-2.5-flash"

# Stage 1: Parse natural-language reseller request into structured KitRequirements
parse_requirements = LlmAgent(
    name="parse_requirements",
    model=MODEL_ID,
    description=(
        "Extracts kit quantity, hardware tier, shipping destination, customer "
        "budget, and headset preference from the reseller's prompt."
    ),
    instruction=(
        "You are the BundleBot Intake Specialist for a B2B technology distributor.\n"
        "Analyze the channel reseller's prompt and extract structured `KitRequirements`:\n"
        "- `quantity`: Number of kits requested (integer, default 1).\n"
        "- `tier`: Hardware tier — choose 'value' (budget/entry), 'standard' "
        "(general business/hybrid developer), or 'performance' (creator/engineering/4K/16-inch workstation).\n"
        "- `destination`: Shipping city, state, or regional warehouse (e.g., 'Austin, TX', "
        "'Harrisburg, PA', 'Mira Loma, CA').\n"
        "- `budget_usd`: Customer budget in USD (either per-kit or total order budget) if mentioned, else None.\n"
        "- `include_headset`: True if wireless ANC headsets or audio/video headsets (IM-PER-ANC) are requested.\n"
        "- `use_case`: Short summary of the customer workload or rollout scenario.\n"
        "- `notes`: Any additional requirements or explicit SKU requests."
    ),
    output_schema=KitRequirements,
    output_key="requirements",
)

# Stage 2: Build complete hardware + software kit BOM from data/catalog.json
build_kit = LlmAgent(
    name="build_kit",
    model=MODEL_ID,
    description=(
        "Selects a complete hardware and software bill of materials from "
        "data/catalog.json based on extracted requirements."
    ),
    instruction=(
        "You are the BundleBot Solutions Architect.\n"
        "Review the extracted partner requirements:\n"
        "{requirements?}\n\n"
        "Use `select_default_kit_skus` and `get_catalog_summary` to select a complete "
        "hardware + software bill of materials from `data/catalog.json`:\n"
        "- Value tier default SKUs: IM-LPT-VAL14, IM-DCK-65W, IM-MON-24FHD, IM-PER-COMBO, IM-SW-SEC365, IM-WAR-NBD3Y\n"
        "- Standard tier default SKUs: IM-LPT-PRO14, IM-DCK-100W, IM-MON-27QHD, IM-PER-COMBO, IM-SW-SEC365, IM-WAR-NBD3Y\n"
        "- Performance tier default SKUs: IM-LPT-ULT16, IM-DCK-100W, IM-MON-32UHD, IM-PER-COMBO, IM-SW-SEC365, IM-WAR-NBD3Y\n"
        "- Include IM-PER-ANC when `include_headset` is True.\n"
        "- Carry forward `quantity`, `destination`, `budget_usd`, and `include_headset` into the `SelectedKit` output."
    ),
    tools=[select_default_kit_skus, get_catalog_summary],
    output_schema=SelectedKit,
    output_key="selected_kit",
)

# Stage 3b: Fan-in synchronization barrier for the 3 parallel deterministic FunctionNodes
join_checks = JoinNode(
    name="join_checks",
    description=(
        "Synchronizes parallel compatibility, warehouse stock, and margin "
        "optimization FunctionNode outputs into a single dictionary."
    ),
)

# Stage 4: Render executive Markdown B2B partner quote
format_quote = LlmAgent(
    name="format_quote",
    model=MODEL_ID,
    description=(
        "Synthesizes the joined compatibility, warehouse stock, and margin "
        "optimization reports with the selected kit into a Markdown B2B quote."
    ),
    instruction=(
        "You are the BundleBot Partner Quote Advisor.\n"
        "Generate an executive-ready Markdown B2B reseller quote using:\n"
        "- Partner Requirements: {requirements?}\n"
        "- Selected Kit BOM: {selected_kit?}\n"
        "- The incoming message from `join_checks`, which contains the merged JSON dictionary "
        "keyed by `validate_compatibility`, `check_warehouse_stock`, and `optimize_margins`.\n\n"
        "Include the following sections clearly in your Markdown response:\n"
        "1. **Executive Summary & Kit Overview** (kit name, tier, quantity, destination warehouse).\n"
        "2. **Bill of Materials (BOM) & Line-Item Pricing** (SKU IDs, product names, unit MSRP, "
        "discounted unit price, and reseller cost).\n"
        "3. **Technical & Power Compatibility Report** (USB-C PD wattage check, display interface "
        "intersection check, software license seat bounds & OS compatibility, and any recommendations).\n"
        "4. **Regional Warehouse Inventory & Fulfillment** (resolved warehouse, per-SKU stock "
        "availability, shortfalls, and alternate warehouse or split-shipment suggestions).\n"
        "5. **Partner Margin & Volume Tier Optimization** (applied discount tier, total MSRP, "
        "total discounted customer price, total reseller cost, partner margin $ and %, budget "
        "compliance, and any proactive next-tier volume upsell recommendation when ordering more "
        "units lowers total customer spend)."
    ),
    output_key="final_quote",
)

# Root ADK 2.0 Diamond Graph Workflow
root_agent = Workflow(
    name="bundle_bot_workflow",
    description=(
        "ADK 2.0 diamond graph workflow for B2B kit configuration, parallel "
        "compatibility/stock/margin checks, JoinNode synchronization, and quote generation."
    ),
    edges=[
        (START, parse_requirements),
        (parse_requirements, build_kit),
        (build_kit, (validate_compatibility, check_warehouse_stock, optimize_margins)),
        ((validate_compatibility, check_warehouse_stock, optimize_margins), join_checks),
        (join_checks, format_quote),
    ],
)

app = App(
    name="bundle_bot",
    root_agent=root_agent,
)
