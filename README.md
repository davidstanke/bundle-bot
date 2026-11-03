# BundleBot — B2B Tech Kit & Margin Optimizer (Ingram Micro Demo)

**Scenario:** A channel reseller asks in natural language: *"Build a remote-work hardware + software kit for 24 new hires under \$45k shipping to Austin."*
**BundleBot** (built with **ADK 2.0 Graph Workflows**) parses requirements, selects SKUs from `data/catalog.json`, validates hardware/power compatibility (e.g., USB-C dock wattage vs. laptop draw), and optimizes reseller margin—flagging when adding 1–2 units unlocks the **Gold 25+ Volume Tier (12% off)** for a lower total price.

---

## Pre-Demo Setup (5 mins before meeting)

```bash
# 1. Install agents-cli and its 7 ADK lifecycle skills
uvx google-agents-cli setup

# 2. Export your demo GCP project & pre-warmed Agent Runtime / Gemini Enterprise IDs
export GOOGLE_CLOUD_PROJECT="your-demo-project-id"
export GOOGLE_CLOUD_LOCATION="us-central1"
export GEMINI_ENTERPRISE_APP_ID="projects/${GOOGLE_CLOUD_PROJECT}/locations/global/collections/default_collection/engines/your-ge-app-id"

# 3. Start on the `main` starter branch (has data/catalog.json + minimal stub)
git checkout main
```

---

## Act I: Antigravity App ("2.0") — Plugins, `/grill-me`, and `/teamwork-preview`

### 1. Showcase a "Build with Google" Plugin
1. Open the `bundle-bot` workspace in **Antigravity App (2.0)**.
2. Open **Plugins → Browse → Build with Google** shelf.
3. Point out **`Google Developer Knowledge`** (`google-developer-knowledge`) and **`Gemini API`** (`gemini-api`), plus the **`google-agents-cli-*`** skills installed by `agents-cli setup`.
4. Ensure **Google Developer Knowledge** is enabled so the agent can query live `adk.dev` and Google Cloud Agent Runtime documentation via MCP.

### 2. Interactive Spec Design with `/grill-me`
Paste into **Antigravity App (2.0)**:

```text
/grill-me We want to turn this starter project into "BundleBot", a B2B IT Kit Builder and Margin Optimizer powered by an ADK 2.0 Graph Workflow (`START -> parse_requirements -> build_kit -> validate_compatibility -> optimize_margins`) over `data/catalog.json`. Use the Google Developer Knowledge plugin if you need ADK 2.0 Workflow syntax. Interview me on the compatibility rules, volume-tier upsell math, and output format, then write `SPEC.md`.
```

*(Answer 1–2 multiple-choice questions in the UI to show how `/grill-me` resolves ambiguity before any code is written.)*

### 3. Multi-Agent Parallel Build with `/teamwork-preview`
Once `SPEC.md` is written, launch Stellar Teamwork in **Antigravity App (2.0)**:

```text
/teamwork-preview [skip-interview] Implement `SPEC.md`:
1. Build deterministic catalog, compatibility (dock wattage >= laptop requirement, seat count check, regional warehouse stock), and volume-tier upsell tools in `app/catalog_tools.py`.
2. Build the ADK 2.0 `Workflow` (`START -> parse_requirements -> build_kit -> validate_compatibility -> optimize_margins`) in `app/agent.py`.
3. Add unit tests in `tests/test_workflow.py` and an evaluation dataset in `tests/eval/datasets/bundle_bot_eval.json`.
```

*(Show the Orchestrator decomposing milestones and spawning Explorers, Workers, and Critics in parallel. While the team works, transition to the terminal for Act II.)*

---

## Act II: Antigravity CLI (`agy`) — Cooking-Show Cut, Evals, and `/learn`

### 1. Switch to the Pre-Baked `solution` Branch & Test Locally
In your terminal:

```bash
git checkout solution
agents-cli playground
```

Open `http://127.0.0.1:8080/dev-ui/?app=app` and test with:

```text
Build a standard remote-work kit (laptop, dock, 27" monitor, peripherals, security license, and 3-year warranty) for 24 new hires shipping to Austin under $45,000.
```

> **Highlight in the Playground UI:**
> - **Graph Execution:** Watch the ADK 2.0 `Workflow` traverse `parse_requirements` → `build_kit` → `validate_compatibility` → `optimize_margins`.
> - **Compatibility Check:** Confirms the 100W/65W USB-C dock matches the laptop's power draw and Austin warehouse has stock.
> - **Margin & Tier Optimizer:** Spots that ordering **25 kits instead of 24** crosses into the **Gold Partner Tier (12% off)**, reducing the customer's total price while increasing reseller margin dollars.

### 2. Run Evals in `agy` CLI & Capture Institutional Memory with `/learn`
Launch **Antigravity CLI**:

```bash
agy
```

Prompt inside `agy` CLI:

```text
Run our ADK evaluation suite using `agents-cli eval run` against `tests/eval/datasets/bundle_bot_eval.json` and fix any dependency or configuration issues so the eval passes cleanly.
```

*(Watch `agy` diagnose the scaffolded `pyproject.toml` gotcha—where `google-adk[eval]` sits in optional extras—and run `uv add --prerelease=allow "google-adk[eval]>=2.0.0a1"` so `agents-cli eval run` succeeds.)*

Now persist that operational lesson with **`/learn`** inside `agy` CLI:

```text
/learn Whenever we scaffold or maintain an `agents-cli` ADK 2.0 project in this repo, always promote `google-adk[eval]>=2.0.0a1` into main `[project.dependencies]` in `pyproject.toml` so `agents-cli eval run` and `agents-cli playground` never strip the eval extra on `uv run`.
```

---

## Act III: Agent Runtime Operations & Gemini Enterprise Publishing

### 1. Deploy to Vertex AI Agent Runtime (Async CLI Flow)
Inside `agy` CLI (or terminal via `!` shell mode):

```bash
# Kick off source-based deployment to Agent Runtime without blocking the demo
agents-cli deploy --no-wait --no-confirm-project

# Check live deployment status and list active Reasoning Engines on Agent Runtime
agents-cli deploy --status
agents-cli deploy --list
```

*(Optional prompt in `agy` CLI to test the pre-warmed remote Agent Runtime instance):*

```text
Query our deployed Agent Runtime instance using `agents-cli run --url` with `--mode adk` for a 10-person performance studio kit shipping to Harrisburg.
```

### 2. Agent Runtime Operations: Cloud Trace & Span Inspection
1. Open **Google Cloud Console → Vertex AI → Agent Runtime** (or **Cloud Trace → Trace Explorer**).
2. Click into the latest trace for `bundle_bot`:
   - Inspect the OpenTelemetry span hierarchy (`invocation` → `Workflow[bundle_bot_workflow]` → `parse_requirements` → `build_kit` → `validate_compatibility` → `optimize_margins`).
   - Show per-node latency, token counts, and deterministic tool execution payloads.

### 3. Publish to Gemini Enterprise App (Gemini Agent)
Register the deployed Agent Runtime engine directly into **Gemini Enterprise** using `deployment_metadata.json`:

```bash
agents-cli publish gemini-enterprise \
  --gemini-enterprise-app-id "${GEMINI_ENTERPRISE_APP_ID}" \
  --display-name "BundleBot — B2B Kit & Margin Advisor" \
  --description "Builds compatible B2B hardware/software kits, checks regional warehouse stock, and optimizes reseller volume tiers." \
  --tool-description "Use this agent to build IT hardware/software bundles, verify SKU compatibility, and calculate partner margins and volume discounts."
```

*(Or run `agents-cli publish gemini-enterprise --interactive` to walk through the interactive selector live.)*

4. Open the **Gemini Enterprise Web App**, select **@BundleBot**, and ask:
   > *"Quote a 24-person remote-work kit shipping to Austin and tell me if bumping to 25 units saves money on the Gold tier."*
