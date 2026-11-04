"""Self-contained B2B catalog lookup and deterministic ADK 2.0 FunctionNode tools."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "catalog.json"

DEFAULT_KIT_SKUS_BY_TIER: dict[str, list[str]] = {
    "value": [
        "IM-LPT-VAL14",
        "IM-DCK-65W",
        "IM-MON-24FHD",
        "IM-PER-COMBO",
        "IM-SW-SEC365",
        "IM-WAR-NBD3Y",
    ],
    "standard": [
        "IM-LPT-PRO14",
        "IM-DCK-100W",
        "IM-MON-27QHD",
        "IM-PER-COMBO",
        "IM-SW-SEC365",
        "IM-WAR-NBD3Y",
    ],
    "performance": [
        "IM-LPT-ULT16",
        "IM-DCK-100W",
        "IM-MON-32UHD",
        "IM-PER-COMBO",
        "IM-SW-SEC365",
        "IM-WAR-NBD3Y",
    ],
}


class _DictAccessibleModel(BaseModel):
    """BaseModel subclass that supports both attribute and dict-style access."""

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)

    def keys(self):
        return self.__class__.model_fields.keys()


# ---------------------------------------------------------------------------
# Pydantic Schemas for ADK 2.0 Graph Workflow State Transitions
# ---------------------------------------------------------------------------


class KitRequirements(_DictAccessibleModel):
    """Structured partner requirements extracted from a natural-language request."""

    quantity: int = Field(
        default=1,
        description="Number of complete hardware + software kits requested.",
    )
    tier: Literal["value", "standard", "performance"] = Field(
        default="standard",
        description="Hardware tier: 'value', 'standard', or 'performance'.",
    )
    destination: str = Field(
        default="US-Central (Austin, TX)",
        description="Shipping destination city, state, or regional warehouse.",
    )
    budget_usd: Optional[float] = Field(
        default=None,
        description="Customer budget in USD (per-kit or total order budget) if specified.",
    )
    include_headset: bool = Field(
        default=False,
        description="Whether to include the wireless ANC headset (IM-PER-ANC).",
    )
    use_case: str = Field(
        default="hybrid workstation",
        description="Primary workload or business use case.",
    )
    notes: str = Field(
        default="",
        description="Any additional partner notes or explicit SKU overrides.",
    )


class SelectedKit(_DictAccessibleModel):
    """Complete hardware + software bill of materials emitted by build_kit."""

    kit_name: str = Field(
        default="Standard Workstation Kit",
        description="Descriptive name of the configured B2B kit.",
    )
    tier: str = Field(
        default="standard",
        description="Configured kit tier ('value', 'standard', or 'performance').",
    )
    quantity: int = Field(
        default=1,
        description="Number of kits to build and ship.",
    )
    destination: str = Field(
        default="US-Central (Austin, TX)",
        description="Target shipping destination or regional warehouse.",
    )
    skus: list[str] = Field(
        default_factory=list,
        description="Ordered list of catalog SKU IDs included in each kit.",
    )
    budget_usd: Optional[float] = Field(
        default=None,
        description="Customer budget in USD (per-kit or total) if specified.",
    )
    include_headset: bool = Field(
        default=False,
        description="Whether the ANC wireless headset (IM-PER-ANC) is included.",
    )
    rationale: str = Field(
        default="",
        description="Brief explanation of why these SKUs were selected.",
    )


class CompatibilityReport(_DictAccessibleModel):
    """Deterministic technical, power, display, and software compatibility report."""

    compatible: bool = Field(
        description="True when all compatibility rules pass with zero issues."
    )
    usb_c_power_ok: bool = Field(
        description="True when dock USB-C PD watts >= laptop required watts."
    )
    display_interface_ok: bool = Field(
        description="True when dock display_ports and monitor inputs share a protocol family."
    )
    software_license_ok: bool = Field(
        description="True when kit quantity is within software min/max seats and laptop OS is supported."
    )
    power_check: str = Field(
        description="Summary of the USB-C power delivery check."
    )
    display_check: str = Field(
        description="Summary of the dock-to-monitor display interface check."
    )
    software_seat_check: str = Field(
        description="Summary of the software license seat bounds and OS check."
    )
    laptop_sku: Optional[str] = Field(default=None, description="Selected laptop SKU.")
    dock_sku: Optional[str] = Field(default=None, description="Selected dock SKU.")
    monitor_sku: Optional[str] = Field(default=None, description="Selected monitor SKU.")
    laptop_power_watts_required: Optional[int] = Field(
        default=None, description="USB-C power watts required by the laptop."
    )
    dock_power_delivery_watts: Optional[int] = Field(
        default=None, description="USB-C power delivery watts provided by the dock."
    )
    shared_display_protocols: list[str] = Field(
        default_factory=list,
        description="Common display protocol families between dock and monitor.",
    )
    issues: list[str] = Field(
        default_factory=list,
        description="List of compatibility violations detected.",
    )
    recommendations: list[str] = Field(
        default_factory=list,
        description="Actionable remediation steps for any compatibility issues.",
    )


class WarehouseStockReport(_DictAccessibleModel):
    """Deterministic regional warehouse inventory and shortfall report."""

    warehouse: str = Field(
        description="Resolved canonical regional warehouse name."
    )
    destination: str = Field(
        description="Original shipping destination requested."
    )
    quantity: int = Field(
        description="Number of kits requested."
    )
    all_in_stock: bool = Field(
        description="True if the resolved warehouse has sufficient stock for all SKUs."
    )
    sku_stock: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Per-SKU stock availability details in the target warehouse.",
    )
    shortfalls: list[str] = Field(
        default_factory=list,
        description="Descriptions of any SKU inventory shortfalls in the target warehouse.",
    )
    alternate_warehouse_suggestions: list[str] = Field(
        default_factory=list,
        description="Alternate warehouse or split-shipment fulfillment recommendations.",
    )


class MarginOptimizationReport(_DictAccessibleModel):
    """Deterministic volume tier discount, partner margin, and upsell report."""

    quantity: int = Field(description="Number of kits quoted.")
    applied_tier: str = Field(description="Active volume discount tier name.")
    discount_pct: float = Field(description="Active volume discount percentage.")
    unit_msrp: float = Field(description="Single-kit total MSRP before volume discount.")
    unit_reseller_cost: float = Field(
        description="Single-kit base reseller cost before volume discount."
    )
    unit_discounted_price: float = Field(
        description="Single-kit customer price after applying discount_pct."
    )
    discounted_unit_reseller_cost: float = Field(
        description="Single-kit reseller cost after applying discount_pct."
    )
    total_msrp: float = Field(
        description="Extended MSRP for all kits before volume discount."
    )
    current_total_customer_price: float = Field(
        description="Total customer price for all kits after applying discount_pct."
    )
    total_discounted_price: float = Field(
        description="Alias for current_total_customer_price."
    )
    total_reseller_cost: float = Field(
        description="Total partner reseller cost for all kits after applying discount_pct."
    )
    total_reseller_margin_dollars: float = Field(
        description="Total reseller profit in USD (current_total_customer_price - total_reseller_cost)."
    )
    reseller_margin_pct: float = Field(
        description="Reseller margin percentage."
    )
    budget_usd: Optional[float] = Field(
        default=None, description="Customer budget in USD if provided."
    )
    within_budget: Optional[bool] = Field(
        default=None, description="Whether the quote is within the customer's budget."
    )
    budget_delta_usd: Optional[float] = Field(
        default=None,
        description="Remaining budget headroom (positive) or overrun (negative) in USD.",
    )
    recommend_upsell: bool = Field(
        default=False,
        description="True strictly when next_tier_total_customer_price < current_total_customer_price.",
    )
    next_tier_upsell: Optional[dict[str, Any]] = Field(
        default=None,
        description="Details of the proactive next-tier volume upsell when recommend_upsell is True.",
    )
    line_items: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Per-SKU pricing and margin breakdown.",
    )


# ---------------------------------------------------------------------------
# Self-Contained Catalog Lookup Helpers
# ---------------------------------------------------------------------------


def load_catalog() -> dict[str, Any]:
    """Load and return the self-contained B2B distribution catalog from data/catalog.json."""
    with CATALOG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_sku_map() -> dict[str, dict[str, Any]]:
    """Return a dictionary mapping each SKU ID to its catalog entry."""
    catalog = load_catalog()
    return {item["sku"]: item for item in catalog.get("skus", [])}


def get_catalog_summary() -> dict[str, Any]:
    """Return a concise summary of all catalog SKUs, warehouses, and volume discount tiers."""
    catalog = load_catalog()
    metadata = catalog.get("metadata", {})
    return {
        "distributor": metadata.get("distributor", ""),
        "currency": metadata.get("currency", "USD"),
        "warehouses": metadata.get("warehouses", []),
        "volume_tiers": metadata.get("volume_tiers", []),
        "skus": [
            {
                "sku": item["sku"],
                "name": item["name"],
                "category": item["category"],
                "tier": item["tier"],
                "msrp": item["msrp"],
                "reseller_cost": item["reseller_cost"],
                "specs": item.get("specs", {}),
                "stock": item.get("stock", {}),
            }
            for item in catalog.get("skus", [])
        ],
    }


def select_default_kit_skus(
    tier: str = "standard", include_headset: bool = False
) -> list[str]:
    """Select the default compatible hardware + software SKU list for a given kit tier."""
    normalized_tier = (tier or "standard").strip().lower()
    if normalized_tier not in DEFAULT_KIT_SKUS_BY_TIER:
        normalized_tier = "standard"

    base_skus = list(DEFAULT_KIT_SKUS_BY_TIER[normalized_tier])
    if include_headset and "IM-PER-ANC" not in base_skus:
        # Insert headset alongside peripherals before software/warranty SKUs
        insert_idx = (
            base_skus.index("IM-PER-COMBO") + 1
            if "IM-PER-COMBO" in base_skus
            else len(base_skus)
        )
        base_skus.insert(insert_idx, "IM-PER-ANC")
    return base_skus


def resolve_warehouse(destination: str) -> str:
    """Resolve a shipping destination string to one of the 3 canonical regional warehouses."""
    if not destination or not destination.strip():
        return "US-Central (Austin, TX)"

    text = destination.strip().lower()
    tokens = set(re.findall(r"[a-z0-9]+", text))

    # Check explicit canonical names or US-East / US-West / US-Central prefixes first
    if "us-east" in text or "harrisburg" in text:
        return "US-East (Harrisburg, PA)"
    if "us-west" in text or "mira loma" in text or "miraloma" in text:
        return "US-West (Mira Loma, CA)"
    if "us-central" in text or "austin" in text:
        return "US-Central (Austin, TX)"

    east_phrases = (
        "pennsylvania",
        "northeast",
        "new york",
        "boston",
        "philadelphia",
        "atlanta",
        "miami",
        "washington dc",
        "east coast",
    )
    east_tokens = {"east", "pa", "ny", "nyc", "nj", "ma", "va", "nc", "ga", "fl", "md"}
    if any(p in text for p in east_phrases) or (tokens & east_tokens):
        return "US-East (Harrisburg, PA)"

    west_phrases = (
        "california",
        "pacific",
        "los angeles",
        "san francisco",
        "san diego",
        "san jose",
        "seattle",
        "portland",
        "oregon",
        "washington",
        "las vegas",
        "phoenix",
        "west coast",
    )
    west_tokens = {"west", "ca", "wa", "or", "nv", "az", "la", "sf"}
    if any(p in text for p in west_phrases) or (tokens & west_tokens):
        return "US-West (Mira Loma, CA)"

    return "US-Central (Austin, TX)"


def _extract_display_protocol_family(port_label: str) -> str:
    """Normalize a versioned display port string (e.g. 'HDMI 2.1', 'DisplayPort 1.4') to its protocol family."""
    lower = port_label.strip().lower()
    if "hdmi" in lower:
        return "HDMI"
    if "displayport" in lower or re.search(r"\bdp\b", lower):
        return "DisplayPort"
    if "usb-c" in lower or "thunderbolt" in lower:
        return "USB-C"
    return port_label.strip()


# ---------------------------------------------------------------------------
# Deterministic ADK 2.0 FunctionNode Callables
# ---------------------------------------------------------------------------


def validate_compatibility(node_input: SelectedKit) -> CompatibilityReport:
    """Validate USB-C power delivery, display interfaces, and software seat/OS bounds for a SelectedKit."""
    kit = (
        SelectedKit.model_validate(node_input)
        if isinstance(node_input, dict)
        else node_input
    )
    sku_map = get_sku_map()

    issues: list[str] = []
    recommendations: list[str] = []

    unknown_skus = [sku for sku in kit.skus if sku not in sku_map]
    for sku in unknown_skus:
        issues.append(f"Unknown catalog SKU: {sku}")

    known_items = [sku_map[sku] for sku in kit.skus if sku in sku_map]
    laptops = [item for item in known_items if item.get("category") == "laptop"]
    docks = [item for item in known_items if item.get("category") == "dock"]
    monitors = [item for item in known_items if item.get("category") == "monitor"]
    software_items = [
        item for item in known_items if item.get("category") == "software_warranty"
    ]

    laptop = laptops[0] if laptops else None
    dock = docks[0] if docks else None
    monitor = monitors[0] if monitors else None

    # 1. USB-C Power Delivery Check
    laptop_watts: Optional[int] = None
    dock_watts: Optional[int] = None
    if laptop and dock:
        laptop_watts = int(laptop.get("specs", {}).get("usb_c_power_watts_required", 0))
        dock_watts = int(dock.get("specs", {}).get("usb_c_power_delivery_watts", 0))
        if dock_watts >= laptop_watts:
            usb_c_power_ok = True
            power_check = (
                f"PASS: Dock {dock['sku']} provides {dock_watts}W USB-C PD, "
                f"meeting {laptop['sku']} requirement of {laptop_watts}W."
            )
        else:
            usb_c_power_ok = False
            msg = (
                f"USB-C power delivery shortfall: Dock {dock['sku']} delivers "
                f"{dock_watts}W, which is below {laptop['sku']} requirement of {laptop_watts}W."
            )
            power_check = f"FAIL: {msg}"
            issues.append(msg)
            recommendations.append(
                "Upgrade dock from IM-DCK-65W to IM-DCK-100W (100W Power Delivery)."
            )
    else:
        usb_c_power_ok = False
        msg = "Kit must include both a laptop SKU and a dock SKU to verify USB-C power delivery."
        power_check = f"FAIL: {msg}"
        issues.append(msg)

    # 2. Display Interface Intersection Check
    shared_protocols: list[str] = []
    if dock and monitor:
        dock_ports = dock.get("specs", {}).get("display_ports", [])
        monitor_inputs = monitor.get("specs", {}).get("inputs", [])
        dock_families = {_extract_display_protocol_family(p) for p in dock_ports}
        monitor_families = {_extract_display_protocol_family(p) for p in monitor_inputs}
        shared_protocols = sorted(dock_families & monitor_families)
        if shared_protocols:
            display_interface_ok = True
            display_check = (
                f"PASS: Dock {dock['sku']} ({', '.join(dock_ports)}) and Monitor "
                f"{monitor['sku']} ({', '.join(monitor_inputs)}) share display "
                f"protocol family: {', '.join(shared_protocols)}."
            )
        else:
            display_interface_ok = False
            msg = (
                f"Display interface mismatch: Dock {dock['sku']} outputs {dock_ports} "
                f"share no common protocol family with Monitor {monitor['sku']} inputs {monitor_inputs}."
            )
            display_check = f"FAIL: {msg}"
            issues.append(msg)
            recommendations.append(
                "Choose a monitor and dock that share HDMI, DisplayPort, or USB-C video interfaces."
            )
    else:
        display_interface_ok = False
        msg = "Kit must include both a dock SKU and a monitor SKU to verify display compatibility."
        display_check = f"FAIL: {msg}"
        issues.append(msg)

    # 3. Software License Seat & OS Bounds Check
    software_license_ok = True
    seat_messages: list[str] = []
    laptop_os = laptop.get("specs", {}).get("os") if laptop else None

    for sw in software_items:
        specs = sw.get("specs", {})
        min_seats = specs.get("min_seats")
        max_seats = specs.get("max_seats")
        supported_os = specs.get("supported_os")

        if min_seats is not None and max_seats is not None:
            if kit.quantity < int(min_seats):
                software_license_ok = False
                msg = (
                    f"Software seat count below minimum for {sw['sku']}: requested "
                    f"{kit.quantity} seats, but minimum is {min_seats} seats."
                )
                issues.append(msg)
                seat_messages.append(f"FAIL: {msg}")
                recommendations.append(
                    f"Increase order quantity to at least {min_seats} seats for {sw['sku']}."
                )
            elif kit.quantity > int(max_seats):
                software_license_ok = False
                msg = (
                    f"Software seat count exceeds maximum for {sw['sku']}: requested "
                    f"{kit.quantity} seats, but maximum is {max_seats} seats."
                )
                issues.append(msg)
                seat_messages.append(f"FAIL: {msg}")
                recommendations.append(
                    f"Split the order or use an enterprise agreement for quantities over {max_seats} seats."
                )
            else:
                seat_messages.append(
                    f"PASS: {sw['sku']} seat count {kit.quantity} is within bounds [{min_seats}, {max_seats}]."
                )

        if supported_os is not None:
            if not laptop_os or laptop_os not in supported_os:
                software_license_ok = False
                msg = (
                    f"OS incompatibility for {sw['sku']}: laptop OS '{laptop_os}' "
                    f"is not in supported_os {supported_os}."
                )
                issues.append(msg)
                seat_messages.append(f"FAIL: {msg}")
                recommendations.append(
                    f"Select a laptop running a supported OS ({', '.join(supported_os)})."
                )
            else:
                seat_messages.append(
                    f"PASS: Laptop OS '{laptop_os}' is supported by {sw['sku']}."
                )

    software_seat_check = (
        " ".join(seat_messages)
        if seat_messages
        else "PASS: No seat-bounded software SKUs in kit."
    )

    compatible = (
        usb_c_power_ok
        and display_interface_ok
        and software_license_ok
        and len(issues) == 0
    )

    return CompatibilityReport(
        compatible=compatible,
        usb_c_power_ok=usb_c_power_ok,
        display_interface_ok=display_interface_ok,
        software_license_ok=software_license_ok,
        power_check=power_check,
        display_check=display_check,
        software_seat_check=software_seat_check,
        laptop_sku=laptop["sku"] if laptop else None,
        dock_sku=dock["sku"] if dock else None,
        monitor_sku=monitor["sku"] if monitor else None,
        laptop_power_watts_required=laptop_watts,
        dock_power_delivery_watts=dock_watts,
        shared_display_protocols=shared_protocols,
        issues=issues,
        recommendations=recommendations,
    )


def check_warehouse_stock(node_input: SelectedKit) -> WarehouseStockReport:
    """Resolve destination warehouse and verify regional stock and shortfalls for every SKU in SelectedKit."""
    kit = (
        SelectedKit.model_validate(node_input)
        if isinstance(node_input, dict)
        else node_input
    )
    catalog = load_catalog()
    sku_map = get_sku_map()
    all_warehouses: list[str] = catalog.get("metadata", {}).get(
        "warehouses",
        [
            "US-Central (Austin, TX)",
            "US-East (Harrisburg, PA)",
            "US-West (Mira Loma, CA)",
        ],
    )
    warehouse = resolve_warehouse(kit.destination)
    other_warehouses = [wh for wh in all_warehouses if wh != warehouse]

    sku_stock: list[dict[str, Any]] = []
    shortfalls: list[str] = []
    alternate_suggestions: list[str] = []

    for sku in kit.skus:
        if sku not in sku_map:
            shortfalls.append(f"{sku}: unknown SKU (0 available).")
            sku_stock.append(
                {
                    "sku": sku,
                    "name": "Unknown SKU",
                    "requested": kit.quantity,
                    "available": 0,
                    "in_stock": False,
                    "shortfall": kit.quantity,
                    "stock_by_warehouse": {},
                }
            )
            continue

        item = sku_map[sku]
        stock_by_wh: dict[str, int] = item.get("stock", {})
        available = int(stock_by_wh.get(warehouse, 0))
        in_stock = available >= kit.quantity
        shortfall = max(0, kit.quantity - available)

        sku_stock.append(
            {
                "sku": sku,
                "name": item["name"],
                "requested": kit.quantity,
                "available": available,
                "in_stock": in_stock,
                "shortfall": shortfall,
                "stock_by_warehouse": stock_by_wh,
            }
        )

        if not in_stock:
            shortfalls.append(
                f"{sku} ({item['name']}): requested {kit.quantity}, available {available} "
                f"in {warehouse} (shortfall: {shortfall} units)."
            )
            single_wh_alts = [
                f"{alt_wh} ({stock_by_wh.get(alt_wh, 0)} available)"
                for alt_wh in other_warehouses
                if int(stock_by_wh.get(alt_wh, 0)) >= kit.quantity
            ]
            total_network_stock = sum(int(v) for v in stock_by_wh.values())
            if single_wh_alts:
                alternate_suggestions.append(
                    f"Reroute {sku} to {', '.join(single_wh_alts)} for single-warehouse fulfillment, "
                    f"or ship {available} units from {warehouse} and split-ship the remaining "
                    f"{shortfall} units from {other_warehouses[0]}."
                )
            elif total_network_stock >= kit.quantity:
                alt_breakdown = ", ".join(
                    f"{alt_wh}: {stock_by_wh.get(alt_wh, 0)}"
                    for alt_wh in other_warehouses
                )
                alternate_suggestions.append(
                    f"Split shipment required for {sku}: ship {available} units from {warehouse} "
                    f"and fulfill the remaining {shortfall} units across alternate warehouses ({alt_breakdown}; "
                    f"total network stock: {total_network_stock})."
                )
            else:
                alternate_suggestions.append(
                    f"Backorder warning for {sku}: total national stock ({total_network_stock}) "
                    f"is below requested quantity ({kit.quantity})."
                )

    all_in_stock = len(shortfalls) == 0 and len(kit.skus) > 0

    return WarehouseStockReport(
        warehouse=warehouse,
        destination=kit.destination,
        quantity=kit.quantity,
        all_in_stock=all_in_stock,
        sku_stock=sku_stock,
        shortfalls=shortfalls,
        alternate_warehouse_suggestions=alternate_suggestions,
    )


def optimize_margins(node_input: SelectedKit) -> MarginOptimizationReport:
    """Calculate volume tier discounts, partner margins, budget compliance, and next-tier upsell math."""
    kit = (
        SelectedKit.model_validate(node_input)
        if isinstance(node_input, dict)
        else node_input
    )
    catalog = load_catalog()
    sku_map = get_sku_map()
    volume_tiers = sorted(
        catalog.get("metadata", {}).get("volume_tiers", []),
        key=lambda t: int(t["min_qty"]),
    )

    active_tier = volume_tiers[0]
    active_tier_idx = 0
    for idx, tier_info in enumerate(volume_tiers):
        if kit.quantity >= int(tier_info["min_qty"]):
            active_tier = tier_info
            active_tier_idx = idx

    applied_tier = str(active_tier["tier_name"])
    discount_pct = float(active_tier["discount_pct"])
    discount_factor = 1.0 - (discount_pct / 100.0)

    known_items = [sku_map[sku] for sku in kit.skus if sku in sku_map]
    unit_msrp = round(sum(float(item["msrp"]) for item in known_items), 2)
    unit_reseller_cost = round(
        sum(float(item["reseller_cost"]) for item in known_items), 2
    )

    unit_discounted_price = round(unit_msrp * discount_factor, 2)
    discounted_unit_reseller_cost = round(unit_reseller_cost * discount_factor, 2)

    total_msrp = round(unit_msrp * kit.quantity, 2)
    current_total_customer_price = round(unit_discounted_price * kit.quantity, 2)
    total_reseller_cost = round(discounted_unit_reseller_cost * kit.quantity, 2)
    total_reseller_margin_dollars = round(
        current_total_customer_price - total_reseller_cost, 2
    )
    reseller_margin_pct = (
        round((total_reseller_margin_dollars / current_total_customer_price) * 100.0, 2)
        if current_total_customer_price > 0
        else 0.0
    )

    line_items: list[dict[str, Any]] = []
    for item in known_items:
        item_msrp = float(item["msrp"])
        item_cost = float(item["reseller_cost"])
        item_disc_price = round(item_msrp * discount_factor, 2)
        item_disc_cost = round(item_cost * discount_factor, 2)
        line_items.append(
            {
                "sku": item["sku"],
                "name": item["name"],
                "category": item["category"],
                "quantity": kit.quantity,
                "unit_msrp": item_msrp,
                "unit_discounted_price": item_disc_price,
                "unit_reseller_cost": item_cost,
                "discounted_unit_reseller_cost": item_disc_cost,
                "extended_customer_price": round(item_disc_price * kit.quantity, 2),
                "extended_reseller_cost": round(item_disc_cost * kit.quantity, 2),
            }
        )

    within_budget: Optional[bool] = None
    budget_delta_usd: Optional[float] = None
    if kit.budget_usd is not None and kit.budget_usd > 0:
        if kit.quantity > 1 and kit.budget_usd <= unit_msrp * 2.0:
            # Per-kit budget comparison
            within_budget = unit_discounted_price <= kit.budget_usd
            budget_delta_usd = round(kit.budget_usd - unit_discounted_price, 2)
        else:
            # Total order budget comparison
            within_budget = current_total_customer_price <= kit.budget_usd
            budget_delta_usd = round(kit.budget_usd - current_total_customer_price, 2)

    # Evaluate next volume tier upsell strictly when next_tier_total_customer_price < current_total_customer_price
    recommend_upsell = False
    next_tier_upsell: Optional[dict[str, Any]] = None
    if active_tier_idx + 1 < len(volume_tiers):
        next_tier = volume_tiers[active_tier_idx + 1]
        next_min_qty = int(next_tier["min_qty"])
        next_discount_pct = float(next_tier["discount_pct"])
        next_factor = 1.0 - (next_discount_pct / 100.0)

        next_unit_discounted_price = round(unit_msrp * next_factor, 2)
        next_discounted_unit_cost = round(unit_reseller_cost * next_factor, 2)
        next_tier_total_customer_price = round(
            next_unit_discounted_price * next_min_qty, 2
        )
        next_tier_total_reseller_cost = round(
            next_discounted_unit_cost * next_min_qty, 2
        )
        next_tier_margin_dollars = round(
            next_tier_total_customer_price - next_tier_total_reseller_cost, 2
        )

        if next_tier_total_customer_price < current_total_customer_price:
            recommend_upsell = True
            customer_savings_usd = round(
                current_total_customer_price - next_tier_total_customer_price, 2
            )
            additional_units = next_min_qty - kit.quantity
            next_tier_upsell = {
                "recommend_upsell": True,
                "current_quantity": kit.quantity,
                "next_tier_name": str(next_tier["tier_name"]),
                "next_tier_min_qty": next_min_qty,
                "additional_units_needed": additional_units,
                "next_tier_discount_pct": next_discount_pct,
                "current_total_customer_price": current_total_customer_price,
                "next_tier_unit_discounted_price": next_unit_discounted_price,
                "next_tier_total_customer_price": next_tier_total_customer_price,
                "next_tier_total_discounted_price": next_tier_total_customer_price,
                "customer_savings_usd": customer_savings_usd,
                "next_tier_total_reseller_cost": next_tier_total_reseller_cost,
                "next_tier_reseller_margin_dollars": next_tier_margin_dollars,
                "recommendation": (
                    f"Bumping order from {kit.quantity} to {next_min_qty} kits (+{additional_units} kit) "
                    f"unlocks {next_tier['tier_name']} ({next_discount_pct:.0f}% off), reducing total "
                    f"customer spend from ${current_total_customer_price:,.2f} to "
                    f"${next_tier_total_customer_price:,.2f} (saving ${customer_savings_usd:,.2f})."
                ),
            }

    return MarginOptimizationReport(
        quantity=kit.quantity,
        applied_tier=applied_tier,
        discount_pct=discount_pct,
        unit_msrp=unit_msrp,
        unit_reseller_cost=unit_reseller_cost,
        unit_discounted_price=unit_discounted_price,
        discounted_unit_reseller_cost=discounted_unit_reseller_cost,
        total_msrp=total_msrp,
        current_total_customer_price=current_total_customer_price,
        total_discounted_price=current_total_customer_price,
        total_reseller_cost=total_reseller_cost,
        total_reseller_margin_dollars=total_reseller_margin_dollars,
        reseller_margin_pct=reseller_margin_pct,
        budget_usd=kit.budget_usd,
        within_budget=within_budget,
        budget_delta_usd=budget_delta_usd,
        recommend_upsell=recommend_upsell,
        next_tier_upsell=next_tier_upsell,
        line_items=line_items,
    )
