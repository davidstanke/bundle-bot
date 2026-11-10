# BundleBot 📦🤖 — Coding Agent Context (`GEMINI.md`)

## Overview
**BundleBot** is an ADK agent for B2B technology distribution. It helps channel resellers configure hardware + software kits from `data/catalog.json`, verifies technical & power compatibility, checks regional warehouse stock, and optimizes partner margins and volume discount tiers.

## Project Structure
- `README.md` — Live demo script and walkthrough instructions.
- `data/catalog.json` — Self-contained 12-SKU B2B distribution catalog with MSRP, reseller cost, power/display specs, regional warehouse inventory, and volume discount tiers.
- `app/agent.py` — Root ADK agent (`App(name="bundle_bot", root_agent=root_agent)`).

## Conventions
- Keep all catalog lookups self-contained against `data/catalog.json` (no external DB or API keys required).
- Use Google Cloud Application Default Credentials (ADC) via Vertex AI (`GOOGLE_GENAI_USE_VERTEXAI=true`) rather than Gemini API keys.
- Use Pydantic `BaseModel` schemas (`output_schema`) for structured state transitions between pipeline stages.
