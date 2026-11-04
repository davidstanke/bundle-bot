"""Deterministic B2B catalog, compatibility, inventory, and margin tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "catalog.json"


class KitRequirements(BaseModel):
  """Parsed B2B customer requirements from natural language."""

  quantity: int = Field(
      description="Number of kits/hires requested (e.g. 24)."
  )
  tier: str = Field(
      default="standard",
      description="Requested kit tier: 'value', 'standard', or 'performance'.",
  )
  destination: str = Field(
      default="Austin",
      description="Shipping destination city or region (e.g. 'Austin', 'Harrisburg', 'Mira Loma').",
  )
  budget_usd: float | None = Field(
      default=None,
      description="Maximum customer budget in USD if specified (e.g. 45000.0).",
  )
  include_headset: bool = Field(
      default=False,
      description="Whether an ANC headset/webcam SKU was explicitly requested.",
  )


class SelectedKit(BaseModel):
  """Candidate kit SKU selection emitted by build_kit."""

  quantity: int = Field(description="Number of kits to build.")
  tier: str = Field(description="Kit tier ('value', 'standard', or 'performance').")
  destination: str = Field(description="Shipping destination city or warehouse.")
  budget_usd: float | None = Field(
      default=None, description="Maximum customer budget in USD if specified."
  )
  skus: list[str] = Field(
      description="List of selected SKU IDs from data/catalog.json."
  )
  selection_rationale: str = Field(
      default="",
      description="Brief explanation of why these SKUs were selected.",
  )


class CompatibilityReport(BaseModel):
  """Result of deterministic technical and power compatibility checks."""

  compatible: bool
  laptop_sku: str | None = None
  dock_sku: str | None = None
  laptop_power_required_watts: int = 0
  dock_power_delivery_watts: int = 0
  power_check_passed: bool = True
  display_check_passed: bool = True
  software_seat_check_passed: bool = True
  issues: list[str] = Field(default_factory=list)
  summary: str


class WarehouseStockReport(BaseModel):
  """Result of deterministic regional warehouse inventory verification."""

  warehouse: str
  quantity_requested: int
  all_in_stock: bool
  sku_availability: dict[str, int] = Field(default_factory=dict)
  shortfalls: list[str] = Field(default_factory=list)
  summary: str


class MarginOptimizationReport(BaseModel):
  """Result of deterministic volume-tier pricing and partner margin optimization."""

  quantity: int
  unit_msrp: float
  unit_reseller_cost: float
  applied_tier: str
  discount_pct: float
  customer_total_price: float
  reseller_total_cost: float
  reseller_margin_dollars: float
  reseller_margin_pct: float
  budget_usd: float | None = None
  within_budget: bool = True
  upsell_recommended: bool = False
  upsell_quantity: int | None = None
  upsell_tier: str | None = None
  upsell_discount_pct: float | None = None
  upsell_customer_total_price: float | None = None
  upsell_customer_savings: float | None = None
  upsell_reseller_margin_dollars: float | None = None
  upsell_margin_gain_dollars: float | None = None
  summary: str


def load_catalog() -> dict[str, Any]:
  """Load the self-contained B2B catalog from data/catalog.json."""
  with CATALOG_PATH.open("r", encoding="utf-8") as f:
    return json.load(f)


def get_sku_map() -> dict[str, dict[str, Any]]:
  """Return a dictionary mapping SKU code to SKU record."""
  catalog = load_catalog()
  return {item["sku"]: item for item in catalog["skus"]}


def get_catalog_summary() -> dict[str, Any]:
  """Return the full B2B catalog metadata and SKUs for kit building."""
  return load_catalog()


def select_default_kit_skus(
    tier: str = "standard", include_headset: bool = False
) -> list[str]:
  """Return a compatible set of SKU IDs for the requested tier ('value', 'standard', 'performance')."""
  normalized = tier.strip().lower()
  if normalized == "performance":
    skus = [
        "IM-LPT-ULT16",
        "IM-DCK-100W",
        "IM-MON-32UHD",
        "IM-PER-COMBO",
        "IM-SW-SEC365",
        "IM-WAR-NBD3Y",
    ]
  elif normalized == "value":
    skus = [
        "IM-LPT-VAL14",
        "IM-DCK-65W",
        "IM-MON-24FHD",
        "IM-PER-COMBO",
        "IM-SW-SEC365",
        "IM-WAR-NBD3Y",
    ]
  else:
    skus = [
        "IM-LPT-PRO14",
        "IM-DCK-100W",
        "IM-MON-27QHD",
        "IM-PER-COMBO",
        "IM-SW-SEC365",
        "IM-WAR-NBD3Y",
    ]
  if include_headset and "IM-PER-ANC" not in skus:
    skus.insert(4, "IM-PER-ANC")
  return skus


def resolve_warehouse(destination: str) -> str:
  """Resolve a destination city or region string to a canonical catalog warehouse."""
  dest_lower = destination.strip().lower()
  if any(k in dest_lower for k in ("harrisburg", "east", "pa", "new york", "boston")):
    return "US-East (Harrisburg, PA)"
  if any(k in dest_lower for k in ("mira loma", "west", "ca", "los angeles", "seattle")):
    return "US-West (Mira Loma, CA)"
  return "US-Central (Austin, TX)"


def _coerce_selected_kit(node_input: SelectedKit | dict[str, Any]) -> SelectedKit:
  if isinstance(node_input, SelectedKit):
    return node_input
  return SelectedKit.model_validate(node_input)


def validate_compatibility(
    node_input: SelectedKit | dict[str, Any],
) -> CompatibilityReport:
  """Validate USB-C dock power delivery vs. laptop draw, display ports, and software seat bounds."""
  kit = _coerce_selected_kit(node_input)
  sku_map = get_sku_map()
  issues: list[str] = []

  laptops = [
      sku_map[s] for s in kit.skus if s in sku_map and sku_map[s]["category"] == "laptop"
  ]
  docks = [
      sku_map[s] for s in kit.skus if s in sku_map and sku_map[s]["category"] == "dock"
  ]
  monitors = [
      sku_map[s] for s in kit.skus if s in sku_map and sku_map[s]["category"] == "monitor"
  ]
  software = [
      sku_map[s]
      for s in kit.skus
      if s in sku_map and sku_map[s]["category"] == "software_warranty"
  ]

  unknown_skus = [s for s in kit.skus if s not in sku_map]
  if unknown_skus:
    issues.append(f"Unknown SKU(s): {', '.join(unknown_skus)}")

  laptop = laptops[0] if laptops else None
  dock = docks[0] if docks else None

  laptop_watts = (
      int(laptop["specs"].get("usb_c_power_watts_required", 0)) if laptop else 0
  )
  dock_watts = (
      int(dock["specs"].get("usb_c_power_delivery_watts", 0)) if dock else 0
  )

  power_ok = True
  if laptop and dock:
    if dock_watts < laptop_watts:
      power_ok = False
      issues.append(
          f"Power mismatch: {dock['sku']} delivers {dock_watts}W PD, "
          f"but {laptop['sku']} requires {laptop_watts}W."
      )

  display_ok = True
  if dock and monitors:
    dock_ports = {p.split()[0] for p in dock["specs"].get("display_ports", [])}
    for mon in monitors:
      mon_inputs = {p.split()[0] for p in mon["specs"].get("inputs", [])}
      if not (dock_ports & mon_inputs):
        display_ok = False
        issues.append(
            f"Display port mismatch between {dock['sku']} and {mon['sku']}."
        )

  seat_ok = True
  for sw in software:
    specs = sw.get("specs", {})
    min_seats = specs.get("min_seats")
    max_seats = specs.get("max_seats")
    if min_seats is not None and kit.quantity < int(min_seats):
      seat_ok = False
      issues.append(
          f"{sw['sku']} requires at least {min_seats} seats (requested {kit.quantity})."
      )
    if max_seats is not None and kit.quantity > int(max_seats):
      seat_ok = False
      issues.append(
          f"{sw['sku']} supports at most {max_seats} seats (requested {kit.quantity})."
      )

  compatible = power_ok and display_ok and seat_ok and not issues
  if compatible:
    summary = (
        f"PASS: {dock['sku'] if dock else 'Dock'} ({dock_watts}W PD) >= "
        f"{laptop['sku'] if laptop else 'Laptop'} ({laptop_watts}W required); "
        f"display interfaces and software seat counts ({kit.quantity} seats) verified."
    )
  else:
    summary = "FAIL: " + "; ".join(issues)

  return CompatibilityReport(
      compatible=compatible,
      laptop_sku=laptop["sku"] if laptop else None,
      dock_sku=dock["sku"] if dock else None,
      laptop_power_required_watts=laptop_watts,
      dock_power_delivery_watts=dock_watts,
      power_check_passed=power_ok,
      display_check_passed=display_ok,
      software_seat_check_passed=seat_ok,
      issues=issues,
      summary=summary,
  )


def check_warehouse_stock(
    node_input: SelectedKit | dict[str, Any],
) -> WarehouseStockReport:
  """Verify regional warehouse inventory for all SKUs in the selected kit."""
  kit = _coerce_selected_kit(node_input)
  sku_map = get_sku_map()
  warehouse = resolve_warehouse(kit.destination)

  availability: dict[str, int] = {}
  shortfalls: list[str] = []

  for sku_id in kit.skus:
    sku = sku_map.get(sku_id)
    if not sku:
      availability[sku_id] = 0
      shortfalls.append(f"{sku_id}: unknown SKU")
      continue
    stock_qty = int(sku.get("stock", {}).get(warehouse, 0))
    availability[sku_id] = stock_qty
    if stock_qty < kit.quantity:
      shortfalls.append(
          f"{sku_id} has {stock_qty} units in {warehouse} (need {kit.quantity})"
      )

  all_in_stock = len(shortfalls) == 0
  if all_in_stock:
    min_stock = min(availability.values()) if availability else 0
    summary = (
        f"IN STOCK at {warehouse}: all {len(kit.skus)} SKUs available "
        f"for {kit.quantity} kits (lowest SKU stock: {min_stock} units)."
    )
  else:
    summary = f"STOCK SHORTFALL at {warehouse}: " + "; ".join(shortfalls)

  return WarehouseStockReport(
      warehouse=warehouse,
      quantity_requested=kit.quantity,
      all_in_stock=all_in_stock,
      sku_availability=availability,
      shortfalls=shortfalls,
      summary=summary,
  )


def _get_tier_for_qty(
    volume_tiers: list[dict[str, Any]], qty: int
) -> dict[str, Any]:
  matched = volume_tiers[0]
  for tier in sorted(volume_tiers, key=lambda t: int(t["min_qty"])):
    if qty >= int(tier["min_qty"]):
      matched = tier
  return matched


def _compute_pricing(
    unit_msrp: float,
    unit_cost: float,
    qty: int,
    discount_pct: float,
) -> tuple[float, float, float, float]:
  """Return (customer_total, reseller_total_cost, margin_dollars, margin_pct).

  Distributor volume discount applies to customer MSRP and is backed by a
  distributor cost rebate so partner unit margin scales cleanly with volume.
  """
  discount_fraction = discount_pct / 100.0
  customer_unit_price = unit_msrp * (1.0 - discount_fraction)
  # Distributor rebates the volume tier discount on partner cost
  effective_unit_cost = unit_cost - (unit_msrp * discount_fraction)
  customer_total = round(customer_unit_price * qty, 2)
  reseller_total_cost = round(effective_unit_cost * qty, 2)
  margin_dollars = round(customer_total - reseller_total_cost, 2)
  margin_pct = (
      round((margin_dollars / customer_total) * 100.0, 2)
      if customer_total > 0
      else 0.0
  )
  return customer_total, reseller_total_cost, margin_dollars, margin_pct


def optimize_margins(
    node_input: SelectedKit | dict[str, Any],
) -> MarginOptimizationReport:
  """Compute B2B kit pricing, partner margin, and volume-tier upsell opportunities."""
  kit = _coerce_selected_kit(node_input)
  catalog = load_catalog()
  sku_map = get_sku_map()
  volume_tiers = catalog["metadata"]["volume_tiers"]

  unit_msrp = round(
      sum(float(sku_map[s]["msrp"]) for s in kit.skus if s in sku_map), 2
  )
  unit_cost = round(
      sum(float(sku_map[s]["reseller_cost"]) for s in kit.skus if s in sku_map),
      2,
  )

  current_tier = _get_tier_for_qty(volume_tiers, kit.quantity)
  discount_pct = float(current_tier["discount_pct"])
  customer_total, reseller_cost, margin_dollars, margin_pct = _compute_pricing(
      unit_msrp, unit_cost, kit.quantity, discount_pct
  )

  within_budget = (
      True if kit.budget_usd is None else customer_total <= kit.budget_usd
  )

  # Check if the next volume tier is within 1-3 units or saves the customer money
  higher_tiers = [
      t
      for t in sorted(volume_tiers, key=lambda x: int(x["min_qty"]))
      if int(t["min_qty"]) > kit.quantity
  ]

  upsell_recommended = False
  upsell_qty: int | None = None
  upsell_tier_name: str | None = None
  upsell_disc: float | None = None
  upsell_cust_total: float | None = None
  upsell_savings: float | None = None
  upsell_margin_dollars: float | None = None
  upsell_margin_gain: float | None = None

  if higher_tiers:
    next_tier = higher_tiers[0]
    next_min_qty = int(next_tier["min_qty"])
    next_disc = float(next_tier["discount_pct"])
    next_cust_total, _, next_margin_dollars, _ = _compute_pricing(
        unit_msrp, unit_cost, next_min_qty, next_disc
    )
    delta_units = next_min_qty - kit.quantity
    if delta_units <= 3 or next_cust_total < customer_total:
      upsell_recommended = True
      upsell_qty = next_min_qty
      upsell_tier_name = str(next_tier["tier_name"])
      upsell_disc = next_disc
      upsell_cust_total = next_cust_total
      upsell_savings = round(customer_total - next_cust_total, 2)
      upsell_margin_dollars = next_margin_dollars
      upsell_margin_gain = round(next_margin_dollars - margin_dollars, 2)

  summary_parts = [
      f"{kit.quantity} kits @ ${unit_msrp:,.2f} MSRP/kit "
      f"({current_tier['tier_name']}, {discount_pct:.0f}% off) = "
      f"${customer_total:,.2f} customer total | "
      f"${margin_dollars:,.2f} reseller margin ({margin_pct:.1f}%)."
  ]
  if upsell_recommended and upsell_qty is not None:
    summary_parts.append(
        f"UPSELL OPPORTUNITY: Ordering {upsell_qty} kits unlocks "
        f"{upsell_tier_name} ({upsell_disc:.0f}% off), reducing customer total "
        f"to ${upsell_cust_total:,.2f} (saves ${upsell_savings:,.2f}) while "
        f"increasing reseller margin to ${upsell_margin_dollars:,.2f} "
        f"(+${upsell_margin_gain:,.2f})."
    )

  return MarginOptimizationReport(
      quantity=kit.quantity,
      unit_msrp=unit_msrp,
      unit_reseller_cost=unit_cost,
      applied_tier=str(current_tier["tier_name"]),
      discount_pct=discount_pct,
      customer_total_price=customer_total,
      reseller_total_cost=reseller_cost,
      reseller_margin_dollars=margin_dollars,
      reseller_margin_pct=margin_pct,
      budget_usd=kit.budget_usd,
      within_budget=within_budget,
      upsell_recommended=upsell_recommended,
      upsell_quantity=upsell_qty,
      upsell_tier=upsell_tier_name,
      upsell_discount_pct=upsell_disc,
      upsell_customer_total_price=upsell_cust_total,
      upsell_customer_savings=upsell_savings,
      upsell_reseller_margin_dollars=upsell_margin_dollars,
      upsell_margin_gain_dollars=upsell_margin_gain,
      summary=" ".join(summary_parts),
  )
