# BundleBot — Coding Agent Context (`GEMINI.md`)

## Overview
**BundleBot** is an ADK agent for B2B technology distribution. It helps channel resellers configure hardware + software kits from `data/catalog.json`, verifies technical & power compatibility, checks regional warehouse stock, and optimizes partner margins and volume discount tiers.

## Project Structure
- `README.md` — Live demo script and walkthrough instructions.
- `data/catalog.json` — Self-contained 12-SKU B2B distribution catalog with MSRP, reseller cost, power/display specs, regional warehouse inventory, and volume discount tiers.
- `app/catalog_tools.py` — Deterministic Python helpers for SKU selection, technical/power compatibility validation, regional warehouse stock checks, and volume-tier / margin optimization.
- `app/agent.py` — Root agent (`parse_requirements -> build_kit -> [validate_compatibility || check_warehouse_stock || optimize_margins] -> format_quote`) wrapped in `App(name="bundle_bot", root_agent=root_agent)`.
- `app/agent_runtime_app.py` & `app/app_utils/deploy.py` — Vertex AI Agent Runtime (`AdkApp`) deployment entrypoint.
- `tests/test_workflow.py` — Unit tests for catalog, compatibility, and tier-upsell math.
- `tests/eval/` — ADK evaluation config (`eval_config.yaml`) and dataset (`datasets/bundle_bot_eval.json`).

## Conventions
- Keep all catalog lookups self-contained against `data/catalog.json` (no external DB or API keys required).
- Use Google Cloud Application Default Credentials (ADC) via Vertex AI (`GOOGLE_GENAI_USE_VERTEXAI=true`) rather than Gemini API keys.
- Use Pydantic `BaseModel` schemas (`output_schema`) for structured state transitions between pipeline stages.
