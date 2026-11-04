"""Comprehensive unit, topology, and evaluation schema tests for BundleBot (ADK 2.0)."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest
import yaml
from google.adk.agents import LlmAgent
from google.adk.workflow import FunctionNode, JoinNode, START, Workflow

import app.catalog_tools as catalog_tools
from app.agent import app, root_agent
from app.catalog_tools import (
    CompatibilityReport,
    KitRequirements,
    MarginOptimizationReport,
    SelectedKit,
    WarehouseStockReport,
    check_warehouse_stock,
    get_catalog_summary,
    get_sku_map,
    load_catalog,
    optimize_margins,
    resolve_warehouse,
    select_default_kit_skus,
    validate_compatibility,
)


# ---------------------------------------------------------------------------
# 1. Self-Contained Catalog Loading & Helper Tests
# ---------------------------------------------------------------------------


def test_load_catalog_and_get_sku_map():
    catalog = load_catalog()
    assert "metadata" in catalog
    assert "skus" in catalog
    assert len(catalog["metadata"]["warehouses"]) == 3
    assert len(catalog["metadata"]["volume_tiers"]) == 4
    assert len(catalog["skus"]) == 12

    sku_map = get_sku_map()
    assert len(sku_map) == 12
    assert "IM-LPT-PRO14" in sku_map
    assert sku_map["IM-LPT-PRO14"]["msrp"] == 1120.00
    assert sku_map["IM-LPT-PRO14"]["reseller_cost"] == 920.00


def test_get_catalog_summary_structure():
    summary = get_catalog_summary()
    assert isinstance(summary, dict)
    assert len(summary["warehouses"]) == 3
    assert len(summary["volume_tiers"]) == 4
    assert len(summary["skus"]) == 12
    sku_ids = {item["sku"] for item in summary["skus"]}
    assert "IM-LPT-ULT16" in sku_ids
    assert "IM-SW-SEC365" in sku_ids


@pytest.mark.parametrize(
    "tier,include_headset,expected_skus",
    [
        (
            "value",
            False,
            [
                "IM-LPT-VAL14",
                "IM-DCK-65W",
                "IM-MON-24FHD",
                "IM-PER-COMBO",
                "IM-SW-SEC365",
                "IM-WAR-NBD3Y",
            ],
        ),
        (
            "standard",
            False,
            [
                "IM-LPT-PRO14",
                "IM-DCK-100W",
                "IM-MON-27QHD",
                "IM-PER-COMBO",
                "IM-SW-SEC365",
                "IM-WAR-NBD3Y",
            ],
        ),
        (
            "performance",
            True,
            [
                "IM-LPT-ULT16",
                "IM-DCK-100W",
                "IM-MON-32UHD",
                "IM-PER-COMBO",
                "IM-PER-ANC",
                "IM-SW-SEC365",
                "IM-WAR-NBD3Y",
            ],
        ),
    ],
)
def test_select_default_kit_skus(
    tier: str, include_headset: bool, expected_skus: list[str]
):
    skus = select_default_kit_skus(tier=tier, include_headset=include_headset)
    assert skus == expected_skus


# ---------------------------------------------------------------------------
# 2. Compatibility Validation Tests (3 Rules: Power, Display, Software/OS)
# ---------------------------------------------------------------------------


def test_validate_compatibility_standard_kit_passes():
    kit = SelectedKit(
        kit_name="Standard Hybrid Kit",
        tier="standard",
        quantity=24,
        destination="Austin, TX",
        skus=select_default_kit_skus("standard", include_headset=False),
    )
    report = validate_compatibility(kit)
    assert isinstance(report, CompatibilityReport)
    assert report.compatible is True
    assert report.usb_c_power_ok is True
    assert report.display_interface_ok is True
    assert report.software_license_ok is True
    assert report.laptop_power_watts_required == 65
    assert report.dock_power_delivery_watts == 100
    assert "DisplayPort" in report.shared_display_protocols
    assert "HDMI" in report.shared_display_protocols
    assert report.issues == []


def test_validate_compatibility_rule1_usb_c_power_mismatch_fails():
    # IM-LPT-ULT16 requires 100W USB-C power, but IM-DCK-65W only supplies 65W
    kit = SelectedKit(
        kit_name="Underpowered Performance Kit",
        tier="performance",
        quantity=10,
        destination="Austin, TX",
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
    assert report.usb_c_power_ok is False
    assert report.display_interface_ok is True
    assert report.software_license_ok is True
    assert any("65W" in issue and "100W" in issue for issue in report.issues)
    assert any("IM-DCK-100W" in rec for rec in report.recommendations)


def test_validate_compatibility_rule2_display_interface_mismatch_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    base_map = copy.deepcopy(get_sku_map())
    # Force monitor inputs to a legacy protocol family disjoint from dock display_ports
    base_map["IM-MON-24FHD"]["specs"]["inputs"] = ["VGA", "DVI-D"]
    monkeypatch.setattr(catalog_tools, "get_sku_map", lambda: base_map)

    kit = SelectedKit(
        kit_name="Disjoint Display Kit",
        tier="value",
        quantity=10,
        destination="Austin, TX",
        skus=select_default_kit_skus("value", include_headset=False),
    )
    report = validate_compatibility(kit)
    assert report.compatible is False
    assert report.usb_c_power_ok is True
    assert report.display_interface_ok is False
    assert report.shared_display_protocols == []
    assert any("display interface mismatch" in issue.lower() for issue in report.issues)


def test_validate_compatibility_rule3_software_seat_bounds_and_os_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    # Below min_seats (3 < 5 for IM-SW-SEC365)
    kit_too_few = SelectedKit(
        kit_name="Small Kit",
        tier="standard",
        quantity=3,
        destination="Austin, TX",
        skus=select_default_kit_skus("standard"),
    )
    report_low = validate_compatibility(kit_too_few)
    assert report_low.compatible is False
    assert report_low.software_license_ok is False
    assert any("minimum is 5 seats" in issue for issue in report_low.issues)

    # Above max_seats (550 > 500 for IM-SW-SEC365)
    kit_too_many = SelectedKit(
        kit_name="Large Kit",
        tier="standard",
        quantity=550,
        destination="Austin, TX",
        skus=select_default_kit_skus("standard"),
    )
    report_high = validate_compatibility(kit_too_many)
    assert report_high.compatible is False
    assert report_high.software_license_ok is False
    assert any("maximum is 500 seats" in issue for issue in report_high.issues)

    # Unsupported laptop OS
    base_map = copy.deepcopy(get_sku_map())
    base_map["IM-LPT-PRO14"]["specs"]["os"] = "Ubuntu Linux 24.04"
    monkeypatch.setattr(catalog_tools, "get_sku_map", lambda: base_map)

    kit_bad_os = SelectedKit(
        kit_name="Linux Kit",
        tier="standard",
        quantity=10,
        destination="Austin, TX",
        skus=select_default_kit_skus("standard"),
    )
    report_os = validate_compatibility(kit_bad_os)
    assert report_os.compatible is False
    assert report_os.software_license_ok is False
    assert any("Ubuntu Linux 24.04" in issue for issue in report_os.issues)


# ---------------------------------------------------------------------------
# 3. Warehouse Resolution & Regional Stock Check Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "destination,expected_warehouse",
    [
        ("Austin, TX", "US-Central (Austin, TX)"),
        ("Dallas, Texas", "US-Central (Austin, TX)"),
        ("Chicago, IL", "US-Central (Austin, TX)"),
        ("US-Central", "US-Central (Austin, TX)"),
        ("Harrisburg, PA", "US-East (Harrisburg, PA)"),
        ("New York, NY", "US-East (Harrisburg, PA)"),
        ("Boston, MA", "US-East (Harrisburg, PA)"),
        ("US-East", "US-East (Harrisburg, PA)"),
        ("Mira Loma, CA", "US-West (Mira Loma, CA)"),
        ("Seattle, WA", "US-West (Mira Loma, CA)"),
        ("San Francisco, California", "US-West (Mira Loma, CA)"),
        ("US-West", "US-West (Mira Loma, CA)"),
    ],
)
def test_resolve_warehouse(destination: str, expected_warehouse: str):
    assert resolve_warehouse(destination) == expected_warehouse


def test_check_warehouse_stock_all_in_stock():
    kit = SelectedKit(
        kit_name="Austin 24 Standard Kits",
        tier="standard",
        quantity=24,
        destination="Austin, TX",
        skus=select_default_kit_skus("standard"),
    )
    report = check_warehouse_stock(kit)
    assert isinstance(report, WarehouseStockReport)
    assert report.warehouse == "US-Central (Austin, TX)"
    assert report.all_in_stock is True
    assert report.shortfalls == []
    assert len(report.sku_stock) == 6
    assert all(item["in_stock"] is True for item in report.sku_stock)


def test_check_warehouse_stock_shortfall_and_alternates():
    # IM-LPT-ULT16 has 30 in US-West, 45 in US-Central, 40 in US-East
    # IM-MON-32UHD has 40 in US-West, 55 in US-Central, 60 in US-East
    kit = SelectedKit(
        kit_name="Mira Loma 60 Performance Kits",
        tier="performance",
        quantity=60,
        destination="Mira Loma, CA",
        skus=select_default_kit_skus("performance"),
    )
    report = check_warehouse_stock(kit)
    assert report.warehouse == "US-West (Mira Loma, CA)"
    assert report.all_in_stock is False
    assert any("IM-LPT-ULT16" in s for s in report.shortfalls)
    assert any("IM-MON-32UHD" in s for s in report.shortfalls)
    assert len(report.alternate_warehouse_suggestions) >= 2
    assert any(
        "US-Central" in s or "US-East" in s
        for s in report.alternate_warehouse_suggestions
    )


# ---------------------------------------------------------------------------
# 4. Margin Optimization & 24 -> 25 Gold Partner Upsell Math Tests
# ---------------------------------------------------------------------------


def test_optimize_margins_24_to_25_gold_tier_upsell():
    kit = SelectedKit(
        kit_name="Austin 24 Standard Kits",
        tier="standard",
        quantity=24,
        destination="Austin, TX",
        skus=select_default_kit_skus("standard", include_headset=False),
        budget_usd=45000.0,
    )
    report = optimize_margins(kit)
    assert isinstance(report, MarginOptimizationReport)

    # 24 kits -> Silver Partner (10+) at 5% discount
    assert report.quantity == 24
    assert report.applied_tier == "Silver Partner (10+)"
    assert report.discount_pct == pytest.approx(5.0)
    assert report.unit_msrp == pytest.approx(1890.00)
    assert report.unit_reseller_cost == pytest.approx(1480.00)
    assert report.unit_discounted_price == pytest.approx(1795.50)
    assert report.discounted_unit_reseller_cost == pytest.approx(1406.00)
    assert report.total_msrp == pytest.approx(45360.00)
    assert report.current_total_customer_price == pytest.approx(43092.00)
    assert report.total_discounted_price == pytest.approx(43092.00)
    assert report.total_reseller_cost == pytest.approx(33744.00)
    assert report.total_reseller_margin_dollars == pytest.approx(9348.00)
    assert report.within_budget is True
    assert report.budget_delta_usd == pytest.approx(1908.00)

    # 24 -> 25 kits unlocks Gold Partner (25+) 12% discount: $41,580.00 < $43,092.00 (saves $1,512.00)
    assert report.recommend_upsell is True
    assert report.next_tier_upsell is not None
    upsell = report.next_tier_upsell
    assert upsell["next_tier_name"] == "Gold Partner (25+)"
    assert upsell["next_tier_min_qty"] == 25
    assert upsell["additional_units_needed"] == 1
    assert upsell["next_tier_discount_pct"] == pytest.approx(12.0)
    assert upsell["next_tier_total_customer_price"] == pytest.approx(41580.00)
    assert upsell["customer_savings_usd"] == pytest.approx(1512.00)
    assert (
        upsell["next_tier_total_customer_price"] < report.current_total_customer_price
    )


def test_optimize_margins_no_upsell_when_next_tier_costs_more():
    # At quantity=20 standard kits: current total = 20 * $1,795.50 = $35,910.00
    # Next tier (25 kits) total = $41,580.00 >= $35,910.00 -> recommend_upsell must be False
    kit = SelectedKit(
        kit_name="20 Standard Kits",
        tier="standard",
        quantity=20,
        destination="Austin, TX",
        skus=select_default_kit_skus("standard"),
        budget_usd=1700.0,  # Per-kit budget ($1,795.50 > $1,700.00 -> over budget)
    )
    report = optimize_margins(kit)
    assert report.applied_tier == "Silver Partner (10+)"
    assert report.current_total_customer_price == pytest.approx(35910.00)
    assert report.recommend_upsell is False
    assert report.next_tier_upsell is None
    assert report.within_budget is False
    assert report.budget_delta_usd == pytest.approx(-95.50)


def test_function_nodes_accept_dict_coercion():
    kit_dict = {
        "kit_name": "Dict Input Kit",
        "tier": "standard",
        "quantity": 24,
        "destination": "Austin, TX",
        "skus": select_default_kit_skus("standard"),
        "budget_usd": 2000.0,
    }
    compat = validate_compatibility(kit_dict)  # type: ignore[arg-type]
    stock = check_warehouse_stock(kit_dict)  # type: ignore[arg-type]
    margin = optimize_margins(kit_dict)  # type: ignore[arg-type]

    assert compat.compatible is True
    assert stock.all_in_stock is True
    assert margin.recommend_upsell is True


# ---------------------------------------------------------------------------
# 5. ADK 2.0 Diamond Workflow Graph Topology & Execution Tests
# ---------------------------------------------------------------------------


def test_adk2_workflow_diamond_topology():
    assert app.name == "bundle_bot"
    assert app.root_agent is root_agent
    assert isinstance(root_agent, Workflow)
    assert root_agent.name == "bundle_bot_workflow"

    graph = root_agent.graph
    assert graph is not None
    nodes_by_name = {node.name: node for node in graph.nodes}

    expected_nodes = {
        "__START__",
        "parse_requirements",
        "build_kit",
        "validate_compatibility",
        "check_warehouse_stock",
        "optimize_margins",
        "join_checks",
        "format_quote",
    }
    assert set(nodes_by_name.keys()) == expected_nodes

    # Verify node types and schema contracts
    parse_node = nodes_by_name["parse_requirements"]
    assert isinstance(parse_node, LlmAgent)
    assert parse_node.output_schema is KitRequirements
    assert parse_node.output_key == "requirements"

    build_node = nodes_by_name["build_kit"]
    assert isinstance(build_node, LlmAgent)
    assert build_node.output_schema is SelectedKit
    assert build_node.output_key == "selected_kit"
    tool_names = {getattr(t, "__name__", getattr(t, "name", "")) for t in build_node.tools}
    assert "select_default_kit_skus" in tool_names
    assert "get_catalog_summary" in tool_names

    for fn_name, expected_out_schema in [
        ("validate_compatibility", CompatibilityReport),
        ("check_warehouse_stock", WarehouseStockReport),
        ("optimize_margins", MarginOptimizationReport),
    ]:
        fn_node = nodes_by_name[fn_name]
        assert isinstance(fn_node, FunctionNode)
        assert fn_node.input_schema is SelectedKit
        assert fn_node.output_schema is expected_out_schema

    join_node = nodes_by_name["join_checks"]
    assert isinstance(join_node, JoinNode)

    quote_node = nodes_by_name["format_quote"]
    assert isinstance(quote_node, LlmAgent)
    assert quote_node.output_key == "final_quote"

    # Verify exact 9 directed edges forming the diamond topology
    edge_pairs = {(edge.from_node.name, edge.to_node.name) for edge in graph.edges}
    expected_edges = {
        ("__START__", "parse_requirements"),
        ("parse_requirements", "build_kit"),
        ("build_kit", "validate_compatibility"),
        ("build_kit", "check_warehouse_stock"),
        ("build_kit", "optimize_margins"),
        ("validate_compatibility", "join_checks"),
        ("check_warehouse_stock", "join_checks"),
        ("optimize_margins", "join_checks"),
        ("join_checks", "format_quote"),
    }
    assert edge_pairs == expected_edges


@pytest.mark.asyncio
async def test_parallel_function_nodes_and_join_node_runtime_execution():
    """Verify ADK 2.0 Workflow runtime executes the 3 parallel FunctionNodes and merges outputs at JoinNode."""
    captured: dict = {}

    def emit_selected_kit() -> SelectedKit:
        return SelectedKit(
            kit_name="Runtime Test Standard Kit",
            tier="standard",
            quantity=24,
            destination="Austin, TX",
            skus=select_default_kit_skus("standard"),
            budget_usd=45000.0,
        )

    def capture_joined(node_input: dict) -> dict:
        captured.update(node_input)
        return node_input

    join_barrier = JoinNode(name="join_checks")
    sub_workflow = Workflow(
        name="deterministic_diamond_check",
        edges=[
            (START, emit_selected_kit),
            (
                emit_selected_kit,
                (validate_compatibility, check_warehouse_stock, optimize_margins),
            ),
            (
                (validate_compatibility, check_warehouse_stock, optimize_margins),
                join_barrier,
            ),
            (join_barrier, capture_joined),
        ],
    )

    from google.adk.runners import InMemoryRunner
    from google.genai import types

    runner = InMemoryRunner(app_name="test_diamond", agent=sub_workflow)
    session = await runner.session_service.create_session(
        app_name="test_diamond", user_id="reseller_1"
    )
    async for _ in runner.run_async(
        user_id="reseller_1",
        session_id=session.id,
        new_message=types.Content(
            role="user", parts=[types.Part.from_text(text="Run checks")]
        ),
    ):
        pass

    assert set(captured.keys()) == {
        "validate_compatibility",
        "check_warehouse_stock",
        "optimize_margins",
    }
    compat_out = captured["validate_compatibility"]
    stock_out = captured["check_warehouse_stock"]
    margin_out = captured["optimize_margins"]
    assert (
        compat_out.compatible
        if isinstance(compat_out, CompatibilityReport)
        else compat_out["compatible"]
    ) is True
    assert (
        stock_out.all_in_stock
        if isinstance(stock_out, WarehouseStockReport)
        else stock_out["all_in_stock"]
    ) is True
    assert (
        margin_out.recommend_upsell
        if isinstance(margin_out, MarginOptimizationReport)
        else margin_out["recommend_upsell"]
    ) is True


# ---------------------------------------------------------------------------
# 6. ADK Evaluation Suite Schema & Metric Validation Tests
# ---------------------------------------------------------------------------


def test_eval_suite_files_and_schema():
    repo_root = Path(__file__).resolve().parent.parent
    config_path = repo_root / "tests" / "eval" / "eval_config.yaml"
    metric_path = repo_root / "tests" / "eval" / "response_quality.py"
    dataset_path = repo_root / "tests" / "eval" / "datasets" / "bundle_bot_eval.json"

    assert config_path.exists()
    assert metric_path.exists()
    assert dataset_path.exists()

    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert "custom_response_quality" in cfg["metrics_to_run"]
    custom_names = {m["name"] for m in cfg["custom_metrics"]}
    assert "custom_response_quality" in custom_names

    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    assert "eval_cases" in dataset
    assert len(dataset["eval_cases"]) >= 3
    for case in dataset["eval_cases"]:
        assert case.get("eval_case_id")
        assert isinstance(case.get("prompt"), dict)
        assert case["prompt"].get("role") == "user"
        assert case["prompt"].get("parts")
        assert isinstance(case.get("reference"), dict)

    spec = importlib.util.spec_from_file_location("response_quality", metric_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.evaluate)
    empty_res = module.evaluate({"response": ""})
    assert empty_res["score"] == 1

