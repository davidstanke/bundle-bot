# BundleBot — B2B Tech Kit & Margin Optimizer

**Scenario:** A channel reseller asks in natural language: *"Build a remote-work hardware + software kit for 24 new hires under \$45k shipping to Austin."*
**BundleBot** (built with **ADK 2.0 Graph Workflows**) parses requirements, selects SKUs from `data/catalog.json`, fans out in parallel to validate hardware/power compatibility, check regional warehouse stock, and optimize reseller margins—flagging when adding 1–2 units unlocks the **Gold 25+ Volume Tier (12% off)** for a lower total price—and joins the results into a final partner quote.

---

## Pre-Demo Setup (5 mins before meeting)

```bash
# 1. Install agents-cli and its 7 ADK lifecycle skills
uvx google-agents-cli setup

# 2. Export your demo GCP project & pre-warmed Agent Runtime / Gemini Enterprise IDs
export GOOGLE_CLOUD_PROJECT="$(gcloud config get-value project)"
export GOOGLE_CLOUD_LOCATION="us-central1"
export GEMINI_ENTERPRISE_APP_ID="$(agents-cli publish gemini --list 2>/dev/null | tail -n 1 | jq -r '.apps[0].name')"

# 3. Start in the repository root on `main` (has data/catalog.json + minimal starter stub)
git checkout main
```

---

## Act I: Antigravity App ("2.0") — Plugins, `/grill-me`, and `/teamwork`

### 0. Run the agent locally
In **Antigravity App**, start a new conversation in a new git worktree. Enter the prompt:
```
Run the agent locally on an unused port between 8080 and 8180
```

Show the local running agent UI.

### 1. Showcase a "Build with Google" Plugin
1. Open **`Customizations`**
2. Point out **`Google Developer Knowledge`** (`google-developer-knowledge`) and **`Gemini API`** (`gemini-api`), plus the **`google-agents-cli-*`** skills installed by `agents-cli setup`.
3. Ensure **Google Developer Knowledge** is enabled so the agent can query live `adk.dev` and Google Cloud Agent Runtime documentation via MCP.

### 2. Spec Design
Paste into **Antigravity App**:

```text
[/plan](slashCommand;plan) We want to turn this starter project into "BundleBot", a B2B IT Kit Builder and Margin Optimizer over `data/catalog.json` using an ADK `SequentialAgent` + `ParallelAgent` pipeline: run `parse_requirements` and `build_kit` sequentially, then run `validate_compatibility`, `check_warehouse_stock`, and `optimize_margins` in parallel via `ParallelAgent`, and finally run `format_quote` (with `LlmAgent` sub-agents passing state via `output_key`).
```

*Review the generated ADK 1.0-style `SequentialAgent` + `ParallelAgent` plan artifact.*

### 3. Refine Spec with socratic `/grill-me` process
Paste into **Antigravity App**:

```text
[/grill-me](slashCommand;grill-me) Let's upgrade our implementation plan from an ADK 1.0 `SequentialAgent` + `ParallelAgent` hierarchy to an ADK 2.0 Graph `Workflow` (`START -> parse_requirements -> build_kit -> (validate_compatibility || check_warehouse_stock || optimize_margins) -> join_checks -> format_quote`). Use the Google Developer Knowledge plugin if you need ADK 2.0 `Workflow` and `JoinNode` syntax. Interview me on using `LlmAgent` nodes for the natural-language stages and deterministic Python function nodes for the 3 parallel branches, plus our compatibility rules, volume-tier upsell math, and output format, then update the plan artifact in place.
```

*Answer the Socratic interview questions one by one to refine the plan artifact to an ADK 2.0 diamond Graph `Workflow`.*

"Now, I could click `Proceed` here, but I want to use this as an opportunity to show off one of the newer features in Antigravity..."

### 4. Multi-Agent Parallel Build with `/teamwork`
Proceed to implement in **Antigravity App**:

```text
/teamwork Implement the plan. Use the `pro` model for architectural design, security review, and complex core logic subagents, and use `flash` for subagents handling well-specified implementation tasks, boilerplate updates, documentation, and test execution.
```

*(Show the Orchestrator decomposing milestones and spawning Explorers, Workers, and Critics in parallel. While the team works, transition to the terminal for Act II.)*

---

## Act II: Antigravity CLI (`agy`) — Cooking-Show Cut, Evals, and `/learn`

### 1. Switch to the Pre-Baked `solution` Folder & Test Locally
In your terminal, move into the `solution` folder and launch **Antigravity CLI**:

```bash
cd solution
agy
```

In AGY,
```
run the agent locally on an unused port between 8080 and 8180
```

> **Highlight in the Playground UI:**
> - **Diamond Graph Execution:** Watch the ADK 2.0 `Workflow` run `parse_requirements` → `build_kit` sequentially, fan out in parallel to `validate_compatibility`, `check_warehouse_stock`, and `optimize_margins`, and fan in via `join_checks` → `format_quote`.
> - **Compatibility & Warehouse Checks:** Confirms in parallel that the USB-C dock matches the laptop's power draw and the Austin warehouse (`US-Central`) has stock for all SKUs.
> - **Margin & Tier Optimizer:** Spots that ordering **25 kits instead of 24** crosses into the **Gold Partner Tier (12% off)**, reducing the customer's total price while increasing reseller margin dollars.

### 2. Run Evals in `agy` CLI & Capture Institutional Memory with `/learn`


Prompt inside `agy` CLI:

```text
Run our ADK evaluation suite using `agents-cli eval run` against `tests/eval/datasets/bundle_bot_eval.json` and fix any dependency or configuration issues so the eval passes cleanly.
```

*(Watch `agy` diagnose the scaffolded `pyproject.toml` gotcha—where `google-adk[eval]` sits in optional extras—and run `uv add --prerelease=allow "google-adk[eval]>=2.0.0a1"` so `agents-cli eval run` succeeds.)*

Now persist that operational lesson with **`/learn`** inside `agy` CLI:

```text
/learn
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
   - Inspect the OpenTelemetry span hierarchy (`invocation` → `Workflow[bundle_bot_workflow]` → sequential `parse_requirements` → `build_kit` → parallel `validate_compatibility` / `check_warehouse_stock` / `optimize_margins` → `join_checks` → `format_quote`).
   - Show per-node latency, parallel fan-out execution, token counts, and deterministic node payloads.

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
