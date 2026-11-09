#!/usr/bin/env python3
"""Antigravity SDK PR Maintainability Reviewer (Vertex AI WIF Edition)."""

import asyncio
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Literal

from github import Auth, Github, GithubException
from github.PullRequest import PullRequest
from google.antigravity import Agent, LocalAgentConfig
from google.antigravity.types import BuiltinTools, CapabilitiesConfig
from pydantic import BaseModel, Field

BOT_REVIEW_MARKER = "<!-- agy-maintainability-review -->"
BOT_FINDING_MARKER_PREFIX = "<!-- agy-finding:"
RUBRIC_PATH = Path(".github/maintainability-rubric.md")
MAX_DIFF_CHARS = 60_000

EXCLUDED_PATHSPECS = [
    ":(exclude)*lock*",
    ":(exclude)*.lock",
    ":(exclude)package-lock.json",
    ":(exclude)pnpm-lock.yaml",
    ":(exclude)yarn.lock",
    ":(exclude)uv.lock",
    ":(exclude)poetry.lock",
    ":(exclude)Cargo.lock",
    ":(exclude)go.sum",
    ":(exclude)*.min.js",
    ":(exclude)*.min.css",
    ":(exclude)*.map",
    ":(exclude)*.pb.go",
    ":(exclude)*_pb2.py",
    ":(exclude)*.generated.*",
    ":(exclude)dist/**",
    ":(exclude)build/**",
    ":(exclude)vendor/**",
    ":(exclude)node_modules/**",
    ":(exclude).svelte-kit/**",
    ":(exclude)*.db",
    ":(exclude)*.db-shm",
    ":(exclude)*.db-wal",
]


class InlineFinding(BaseModel):
    path: str = Field(description="Relative file path from the repository root.")
    line: int = Field(
        description="Line number in the NEW version of the file (right side of diff) where the issue occurs."
    )
    category: Literal[
        "Complexity",
        "Modularity & Coupling",
        "Naming & Readability",
        "Duplication (DRY)",
        "Error Handling",
        "Testability",
    ] = Field(description="Maintainability pillar for this finding.")
    severity: Literal["HIGH", "MEDIUM", "NIT"] = Field(
        description="Impact on long-term code maintainability."
    )
    comment: str = Field(
        description="Concise explanation of why this hurts maintainability and how to refactor it."
    )
    suggestion: str | None = Field(
        default=None,
        description=(
            "Optional exact replacement code for the single target line `line`. "
            "Leave null if the fix spans multiple lines or requires broader refactoring."
        ),
    )


class MaintainabilityReview(BaseModel):
    overall_score: int = Field(
        ge=1,
        le=10,
        description="Maintainability score from 1 (severe technical debt) to 10 (exemplary maintainability).",
    )
    summary: str = Field(
        description="Concise 2-3 sentence executive summary of the PR's maintainability impact."
    )
    findings: list[InlineFinding] = Field(
        default_factory=list,
        description="Actionable maintainability findings anchored to changed lines (maximum 8).",
    )


def get_filtered_diff(base_sha: str, head_sha: str) -> str:
    cmd = ["git", "diff", "--no-color", "--unified=3", f"{base_sha}...{head_sha}", "--", "."] + EXCLUDED_PATHSPECS
    return subprocess.check_output(cmd, text=True, errors="replace")


def parse_valid_diff_lines(diff_text: str) -> dict[str, set[int]]:
    """Parses a unified diff and returns the set of valid RIGHT-side line numbers per file."""
    valid_lines: dict[str, set[int]] = {}
    current_file: str | None = None
    right_line: int | None = None
    hunk_header_re = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("+++ b/"):
            current_file = raw_line[6:].strip()
            valid_lines.setdefault(current_file, set())
            right_line = None
        elif raw_line.startswith("@@ ") and current_file is not None:
            match = hunk_header_re.match(raw_line)
            if match:
                right_line = int(match.group(1))
        elif current_file is not None and right_line is not None:
            if raw_line.startswith("+") and not raw_line.startswith("+++"):
                valid_lines[current_file].add(right_line)
                right_line += 1
            elif raw_line.startswith("-") and not raw_line.startswith("---"):
                continue
            elif raw_line.startswith(" "):
                valid_lines[current_file].add(right_line)
                right_line += 1
    return valid_lines


def finding_fingerprint(path: str, category: str, comment: str) -> str:
    normalized = f"{path.strip()}::{category.strip()}::{comment.strip().lower()[:120]}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]


def get_existing_bot_findings(pr: PullRequest) -> tuple[set[str], list[str]]:
    """Returns (set of fingerprints, human-readable list of prior findings) to prevent duplicate spam."""
    fingerprints: set[str] = set()
    summaries: list[str] = []
    marker_re = re.compile(r"<!-- agy-finding:([a-f0-9]+) -->")

    for comment in pr.get_review_comments():
        body = comment.body or ""
        match = marker_re.search(body)
        if match:
            fingerprints.add(match.group(1))
            clean_text = marker_re.sub("", body).strip().splitlines()[0]
            summaries.append(f"- `{comment.path}:{comment.line or comment.original_line}`: {clean_text}")

    return fingerprints, summaries


async def run_maintainability_agent(
    diff_text: str, prior_finding_summaries: list[str]
) -> MaintainabilityReview:
    rubric = (
        RUBRIC_PATH.read_text(encoding="utf-8")
        if RUBRIC_PATH.exists()
        else "Review the code changes strictly for long-term maintainability, modularity, readability, and testability."
    )

    prior_context = ""
    if prior_finding_summaries:
        joined = "\n".join(prior_finding_summaries[:20])
        prior_context = (
            "\n\n### Previously Reported Findings on This PR (Do NOT Repeat)\n"
            "The following findings have already been posted on earlier commits. "
            "Do NOT report them again:\n"
            f"{joined}\n"
        )

    config = LocalAgentConfig(
        vertex=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
        model=os.environ.get("AGY_MODEL", "gemini-3.5-flash"),
        capabilities=CapabilitiesConfig(
            enabled_tools=BuiltinTools.read_only(),
            enable_subagents=False,
        ),
        system_instructions=rubric,
        response_schema=MaintainabilityReview,
    )

    truncated_note = (
        f"\n\n*(Note: Diff truncated to {MAX_DIFF_CHARS} characters; use your read_file tool to inspect full files.)*"
        if len(diff_text) > MAX_DIFF_CHARS
        else ""
    )

    prompt = (
        "Review the following Pull Request git diff strictly for code maintainability. "
        "Use your read-only workspace tools (`read_file`, search) whenever you need surrounding file or caller "
        "context to verify whether a pattern is maintainable. "
        "Only anchor findings to lines that appear on the `+` (right) side of the diff."
        f"{prior_context}\n\n"
        f"```diff\n{diff_text[:MAX_DIFF_CHARS]}\n```{truncated_note}"
    )

    async with Agent(config) as agent:
        response = await agent.chat(prompt)
        raw_output = await response.structured_output()
        if raw_output is None:
            raise RuntimeError("Maintainability agent returned no structured output.")
        if isinstance(raw_output, MaintainabilityReview):
            return raw_output
        return MaintainabilityReview.model_validate(raw_output)


def post_github_review(
    pr: PullRequest,
    head_sha: str,
    review: MaintainabilityReview,
    valid_diff_lines: dict[str, set[int]],
    existing_fingerprints: set[str],
) -> None:
    commit = pr.base.repo.get_commit(head_sha)

    inline_comments: list[dict[str, object]] = []
    off_diff_notes: list[str] = []

    for finding in review.findings[:8]:
        fp = finding_fingerprint(finding.path, finding.category, finding.comment)
        if fp in existing_fingerprints:
            continue
        existing_fingerprints.add(fp)

        marker = f"{BOT_FINDING_MARKER_PREFIX}{fp} -->"
        body = f"{marker}\n**[{finding.severity} · {finding.category}]** {finding.comment}"
        if finding.suggestion:
            body += f"\n```suggestion\n{finding.suggestion}\n```"

        file_valid_lines = valid_diff_lines.get(finding.path, set())
        if finding.line in file_valid_lines:
            inline_comments.append(
                {
                    "path": finding.path,
                    "line": finding.line,
                    "side": "RIGHT",
                    "body": body,
                }
            )
        else:
            off_diff_notes.append(
                f"- **`{finding.path}:{finding.line}` [{finding.severity} · {finding.category}]**: {finding.comment}"
            )

    # Skip posting a noisy empty review on synchronize commits if all findings were already reported
    if not inline_comments and not off_diff_notes and existing_fingerprints:
        print("No new maintainability findings since the previous review. Skipping comment.")
        return

    header = (
        f"{BOT_REVIEW_MARKER}\n"
        f"### 🧭 Antigravity Maintainability Review (Score: **{review.overall_score}/10**)\n\n"
        f"{review.summary}\n"
    )
    if off_diff_notes:
        header += "\n#### Additional File-Level Observations\n" + "\n".join(off_diff_notes) + "\n"

    try:
        pr.create_review(
            commit=commit,
            body=header,
            event="COMMENT",
            comments=inline_comments,
        )
        print(f"Posted review with {len(inline_comments)} inline comment(s).")
    except GithubException as exc:
        print(f"Inline review submission failed ({exc.status}); falling back to summary review.", file=sys.stderr)
        all_notes = list(off_diff_notes)
        for c in inline_comments:
            all_notes.append(f"- **`{c['path']}:{c['line']}`**: {c['body']}")
        fallback_body = header
        if all_notes:
            fallback_body += "\n#### Findings\n" + "\n".join(all_notes)
        pr.create_review(commit=commit, body=fallback_body, event="COMMENT")


async def main() -> None:
    base_sha = os.environ["BASE_SHA"]
    head_sha = os.environ["HEAD_SHA"]
    diff_text = get_filtered_diff(base_sha, head_sha)

    if not diff_text.strip():
        print("No reviewable code changes found after filtering excluded paths.")
        return

    gh = Github(auth=Auth.Token(os.environ["GITHUB_TOKEN"]))
    repo = gh.get_repo(os.environ["GITHUB_REPOSITORY"])
    pr = repo.get_pull(int(os.environ["PR_NUMBER"]))

    valid_diff_lines = parse_valid_diff_lines(diff_text)
    existing_fingerprints, prior_summaries = get_existing_bot_findings(pr)

    review = await run_maintainability_agent(diff_text, prior_summaries)
    post_github_review(pr, head_sha, review, valid_diff_lines, existing_fingerprints)


if __name__ == "__main__":
    asyncio.run(main())
