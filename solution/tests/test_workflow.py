"""Unit tests for BundleBot catalog tools and ADK 2.0 diamond Workflow."""

from __future__ import annotations

from google.adk.workflow import Workflow

from app.agent import app, root_agent
from app.catalog_tools import (
    SelectedKit,
    check_warehouse_stock,
    load_catalog,
    optimize_margins,
    select_default_kit_skus,
    validate_compatibility,
)


def test_catalog_has_12_skus_and_volume_tiers() -> None:
  catalog = load_catalog()
  assert len(catalog["skus"]) == 12
  tiers = catalog["metadata"]["volume_tiers"]
  assert [t["min_qty"] for t in tiers] == [1, 10, 25, 50]


def test_compatibility_passes_for_standard_kit() -> None:
  skus = select_default_kit_skus("standard")
  kit = SelectedKit(
      quantity=24,
      tier="standard",
      destination="Austin",
      budget_usd=45000.0,
      skus=skus,
  )
  report = validate_compatibility(kit)
  assert report.compatible is True
  assert report.power_check_passed is True
  assert report.dock_power_delivery_watts >= report.laptop_power_required_watts


def test_compatibility_fails_for_underpowered_dock() -> None:
  # IM-LPT-ULT16 requires 100W, IM-DCK-65W only delivers 65W
  kit = SelectedKit(
      quantity=10,
      tier="performance",
      destination="Austin",
      skus=[
          "IM-LPT-ULT16",
          "IM-DCK-65W",
          "IM-MON-32UHD",
          "IM-PER-COMBO",
          "IM-SW-SEC365",
          "IM-WAR-NBD3Y",
      ],
  )
  report = validate_compatibility(kit)
  assert report.compatible is False
  assert report.power_check_passed is False
  assert any("Power mismatch" in issue for issue in report.issues)


def test_warehouse_stock_austin_and_shortfall() -> None:
  skus = select_default_kit_skus("standard")
  kit_ok = SelectedKit(
      quantity=24,
      tier="standard",
      destination="Austin",
      skus=skus,
  )
  stock_ok = check_warehouse_stock(kit_ok)
  assert stock_ok.warehouse == "US-Central (Austin, TX)"
  assert stock_ok.all_in_stock is True

  # IM-LPT-ULT16 only has 45 units in Austin
  kit_short = SelectedKit(
      quantity=50,
      tier="performance",
      destination="Austin",
      skus=select_default_kit_skus("performance"),
  )
  stock_short = check_warehouse_stock(kit_short)
  assert stock_short.all_in_stock is False
  assert any("IM-LPT-ULT16" in s for s in stock_short.shortfalls)


def test_margin_optimizer_flags_24_to_25_gold_tier_upsell() -> None:
  skus = select_default_kit_skus("standard")
  kit = SelectedKit(
      quantity=24,
      tier="standard",
      destination="Austin",
      budget_usd=45000.0,
      skus=skus,
  )
  margin = optimize_margins(kit)
  assert margin.within_budget is True
  assert margin.applied_tier == "Silver Partner (10+)"
  assert margin.discount_pct == 5.0
  assert margin.upsell_recommended is True
  assert margin.upsell_quantity == 25
  assert margin.upsell_tier == "Gold Partner (25+)"
  assert margin.upsell_discount_pct == 12.0
  assert margin.upsell_customer_total_price is not None
  assert margin.upsell_customer_total_price < margin.customer_total_price
  assert margin.upsell_reseller_margin_dollars is not None
  assert margin.upsell_reseller_margin_dollars > margin.reseller_margin_dollars


def test_workflow_diamond_topology() -> None:
  assert isinstance(root_agent, Workflow)
  assert app.name == "bundle_bot"
  assert root_agent.name == "bundle_bot_workflow"
