#!/usr/bin/env python3
"""Posts BundleBot eval results to a pull request and gates on metric thresholds.

Reads the newest `agents-cli eval run` grade results (JSON), renders a Markdown
report, creates or updates a single sticky PR comment, and exits non-zero when
the eval did not run or any gated metric is below its threshold.
"""

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from github import Auth, Github

BOT_EVAL_MARKER = "<!-- agy-eval-results -->"
RESULTS_GLOB = "*.json"
MAX_PROMPT_CHARS = 70

# Default thresholds on each metric's `mean_score`. Override with the
# EVAL_THRESHOLDS env var, e.g. "custom_response_quality=4.0,domain_rubric_pass_rate=0.9".
DEFAULT_THRESHOLDS = {
    "custom_response_quality": 4.0,  # judge scale is 1-5
    "domain_rubric_pass_rate": 0.9,  # fraction of rubric items passed (0-1)
}


@dataclass
class MetricOutcome:
    name: str
    mean: float | None
    threshold: float | None
    valid: int
    total: int

    @property
    def gated(self) -> bool:
        return self.threshold is not None

    @property
    def passed(self) -> bool:
        if not self.gated:
            return True
        return self.mean is not None and self.mean >= self.threshold

    @property
    def status(self) -> str:
        if not self.gated:
            return "ℹ️ info"
        return "✅ pass" if self.passed else "❌ fail"


def parse_thresholds(raw: str | None) -> dict[str, float]:
    if not raw:
        return dict(DEFAULT_THRESHOLDS)
    thresholds: dict[str, float] = {}
    for item in raw.split(","):
        if item.strip():
            name, _, value = item.partition("=")
            thresholds[name.strip()] = float(value)
    return thresholds


def find_latest_results(results_dir: Path) -> Path | None:
    candidates = sorted(results_dir.glob(RESULTS_GLOB), key=lambda p: p.stat().st_mtime)
    return candidates[-1] if candidates else None


def summarize_metrics(results: dict, thresholds: dict[str, float]) -> list[MetricOutcome]:
    outcomes: list[MetricOutcome] = []
    seen: set[str] = set()
    for metric in results.get("summary_metrics") or []:
        name = metric["metric_name"]
        seen.add(name)
        outcomes.append(
            MetricOutcome(
                name=name,
                mean=metric.get("mean_score"),
                threshold=thresholds.get(name),
                valid=metric.get("num_cases_valid", 0),
                total=metric.get("num_cases_total", 0),
            )
        )
    # A gated metric that produced no summary at all is a failure, not a pass.
    for name, threshold in thresholds.items():
        if name not in seen:
            outcomes.append(MetricOutcome(name, None, threshold, 0, 0))
    return outcomes


def case_prompts(results: dict) -> list[str]:
    prompts: list[str] = []
    for dataset in results.get("evaluation_dataset") or []:
        for case in dataset.get("eval_cases") or []:
            parts = (case.get("prompt") or {}).get("parts") or []
            text = next((p["text"] for p in parts if p.get("text")), "")
            text = " ".join(text.split())
            if len(text) > MAX_PROMPT_CHARS:
                text = text[: MAX_PROMPT_CHARS - 1] + "…"
            prompts.append(text)
    return prompts


def format_score(score: float | None) -> str:
    return "n/a" if score is None else f"{score:.2f}"


def render_case_table(results: dict, metric_names: list[str]) -> str:
    prompts = case_prompts(results)
    header = "| # | Prompt | " + " | ".join(f"`{n}`" for n in metric_names) + " |"
    divider = "|---|---|" + "|".join("---" for _ in metric_names) + "|"
    rows = [header, divider]
    for case in results.get("eval_case_results") or []:
        index = case["eval_case_index"]
        prompt = prompts[index] if index < len(prompts) else ""
        candidates = case.get("response_candidate_results") or [{}]
        metric_results = candidates[0].get("metric_results") or {}
        cells = []
        for name in metric_names:
            result = metric_results.get(name) or {}
            cells.append("⚠️ error" if result.get("error_message") else format_score(result.get("score")))
        rows.append(f"| {index} | {prompt} | " + " | ".join(cells) + " |")
    return "\n".join(rows)


def render_comment(
    outcomes: list[MetricOutcome],
    results: dict | None,
    head_sha: str,
    run_url: str,
    artifact_url: str,
    eval_outcome: str,
) -> str:
    overall_pass = results is not None and all(o.passed for o in outcomes)
    if results is None:
        verdict = f"❌ **Eval did not produce results** (eval step: `{eval_outcome}`)."
    elif overall_pass:
        verdict = "✅ **All gated metrics met their thresholds.**"
    else:
        verdict = "❌ **One or more gated metrics are below threshold.**"

    lines = [
        BOT_EVAL_MARKER,
        "### 📊 BundleBot Eval Results",
        "",
        f"{verdict}",
        "",
        f"Commit `{head_sha[:7]}` · [workflow run]({run_url})"
        + (f" · [download full report]({artifact_url})" if artifact_url else ""),
    ]

    if results is not None:
        lines += [
            "",
            "#### Summary",
            "",
            "| Metric | Mean score | Threshold | Valid cases | Status |",
            "|---|---|---|---|---|",
        ]
        for o in outcomes:
            threshold = f"≥ {o.threshold:g}" if o.gated else "—"
            lines.append(
                f"| `{o.name}` | {format_score(o.mean)} | {threshold} | {o.valid}/{o.total} | {o.status} |"
            )
        metric_names = [o.name for o in outcomes if o.total]
        if metric_names:
            lines += ["", "#### Per-case scores", "", render_case_table(results, metric_names)]
    return "\n".join(lines) + "\n"


def upsert_sticky_comment(pr, body: str) -> None:
    for comment in pr.get_issue_comments():
        if BOT_EVAL_MARKER in (comment.body or ""):
            comment.edit(body)
            print("Updated existing eval results comment.")
            return
    pr.create_issue_comment(body)
    print("Posted new eval results comment.")


def main() -> int:
    results_dir = Path(os.environ.get("EVAL_RESULTS_DIR", "solution/artifacts/grade_results"))
    thresholds = parse_thresholds(os.environ.get("EVAL_THRESHOLDS"))

    results_path = find_latest_results(results_dir) if results_dir.exists() else None
    results = json.loads(results_path.read_text(encoding="utf-8")) if results_path else None
    outcomes = summarize_metrics(results, thresholds) if results else []

    body = render_comment(
        outcomes=outcomes,
        results=results,
        head_sha=os.environ["HEAD_SHA"],
        run_url=os.environ["RUN_URL"],
        artifact_url=os.environ.get("ARTIFACT_URL", ""),
        eval_outcome=os.environ.get("EVAL_OUTCOME", "unknown"),
    )

    gh = Github(auth=Auth.Token(os.environ["GITHUB_TOKEN"]))
    pr = gh.get_repo(os.environ["GITHUB_REPOSITORY"]).get_pull(int(os.environ["PR_NUMBER"]))
    upsert_sticky_comment(pr, body)

    if results is None:
        print(f"No eval results found in {results_dir}.", file=sys.stderr)
        return 1
    failing = [o.name for o in outcomes if not o.passed]
    if failing:
        print(f"Gated metrics below threshold: {', '.join(failing)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
