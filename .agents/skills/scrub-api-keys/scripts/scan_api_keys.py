#!/usr/bin/env python3
"""Deterministic scanner for potential API keys, tokens, and secrets.

Uses provider-specific regular expressions, generic credential assignment
patterns, and Shannon entropy heuristics to locate candidate secrets in a
codebase. Matched secret values are redacted in output.

Exit codes:
    0 - No findings detected.
    1 - One or more potential secrets detected.
    2 - Usage or runtime error.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".tox",
    ".nox",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "coverage",
    ".idea",
    ".vscode",
}

DEFAULT_EXCLUDED_FILES = {
    "uv.lock",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Cargo.lock",
    "Gemfile.lock",
    "composer.lock",
    "go.sum",
}

BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".svg",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".tgz",
    ".bz2",
    ".xz",
    ".7z",
    ".jar",
    ".whl",
    ".pyc",
    ".pyo",
    ".so",
    ".dylib",
    ".dll",
    ".exe",
    ".bin",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".mp3",
    ".mp4",
    ".wav",
    ".mov",
    ".ttf",
    ".otf",
    ".woff",
    ".woff2",
}

# Patterns for known secret formats: (rule_id, severity, description, compiled_regex)
PROVIDER_PATTERNS: list[tuple[str, str, str, re.Pattern[str]]] = [
    (
        "google-api-key",
        "high",
        "Google / Gemini / GCP API key",
        re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"),
    ),
    (
        "private-key-block",
        "high",
        "Private key PEM block",
        re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
    ),
    (
        "gcp-service-account",
        "high",
        "GCP service account JSON credential",
        re.compile(r'"type"\s*:\s*"service_account"'),
    ),
    (
        "aws-access-key-id",
        "high",
        "AWS Access Key ID",
        re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    ),
    (
        "openai-api-key",
        "high",
        "OpenAI API key",
        re.compile(r"\bsk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9\-_]{20,}\b"),
    ),
    (
        "anthropic-api-key",
        "high",
        "Anthropic API key",
        re.compile(r"\bsk-ant-(?:api\d{2}-)?[A-Za-z0-9\-_]{20,}\b"),
    ),
    (
        "github-token",
        "high",
        "GitHub personal/OAuth/app token",
        re.compile(
            r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b"
            r"|\bgithub_pat_[A-Za-z0-9_]{22,}\b"
        ),
    ),
    (
        "slack-token",
        "high",
        "Slack API token",
        re.compile(r"\bxox[baprs]-[0-9A-Za-z\-]{10,}\b"),
    ),
    (
        "stripe-key",
        "high",
        "Stripe API key",
        re.compile(r"\b(?:sk|rk)_(?:live|test)_[0-9a-zA-Z]{16,}\b"),
    ),
    (
        "huggingface-token",
        "high",
        "Hugging Face access token",
        re.compile(r"\bhf_[A-Za-z0-9]{20,}\b"),
    ),
    (
        "sendgrid-api-key",
        "high",
        "SendGrid API key",
        re.compile(r"\bSG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{43}\b"),
    ),
    (
        "auth-header-token",
        "medium",
        "Hardcoded Authorization header credential",
        re.compile(
            r"(?i)Authorization['\"]?\s*[:=]\s*['\"]?(?:Bearer|Basic)\s+[A-Za-z0-9\-._~+/]{16,}={0,2}"
        ),
    ),
    (
        "connection-string-password",
        "high",
        "Connection string with embedded credentials",
        re.compile(
            r"(?i)\b(?:postgres|postgresql|mysql|mongodb(?:\+srv)?|redis|amqp)://"
            r"[^:\s'\"`]+:[^@\s'\"`]+@[^\s'\"`]+"
        ),
    ),
]

# Generic assignment pattern: e.g. API_KEY = "..." or "api_key": "..." or API_KEY=...
GENERIC_ASSIGNMENT_RE = re.compile(
    r"""(?ix)
    (?:^|[\s,{(\[])
    ['"]?
    (?P<name>
        [A-Z0-9_]*
        (?:API[_-]?KEY|SECRET[_-]?KEY|ACCESS[_-]?TOKEN|AUTH[_-]?TOKEN|
           CLIENT[_-]?SECRET|PRIVATE[_-]?KEY|BEARER[_-]?TOKEN|
           ACCESS[_-]?KEY|SECRET[_-]?TOKEN|SIGNING[_-]?SECRET|
           WEBHOOK[_-]?SECRET|ENCRYPTION[_-]?KEY)
        [A-Z0-9_]*
    )
    ['"]?
    \s*[:=]\s*
    (?P<quote>['"]?)
    (?P<value>[^\s'"#,;)}\]]{12,})
    (?P=quote)
    """
)

# Quoted string literal candidates for entropy scanning
QUOTED_LITERAL_RE = re.compile(r"""(['"])([A-Za-z0-9+/=_\-]{20,})\1""")

# Placeholder / non-secret value patterns to suppress obvious false positives
PLACEHOLDER_RE = re.compile(
    r"(?i)(?:your[_-]?|my[_-]?|example|sample|dummy|fake|test[_-]?key|"
    r"placeholder|changeme|replace[_-]?me|insert[_-]?|todo|fixme|"
    r"redacted|masked|none|null|true|false|xxxx+|0000+|\$\{|<\w+>|"
    r"os\.environ|os\.getenv|process\.env|env\[)"
)

# Common non-secret high-entropy shapes (URLs, file paths, UUIDs, pure hex hashes)
NON_SECRET_LITERAL_RE = re.compile(
    r"^(?:"
    r"https?://|"
    r"[./~]?[A-Za-z0-9_\-]+(?:/[A-Za-z0-9_\-.]+){2,}|"
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    r")"
)


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    rule_id: str
    severity: str
    description: str
    redacted_match: str


def shannon_entropy(text: str) -> float:
    """Calculate Shannon entropy in bits per character."""
    if not text:
        return 0.0
    counts: dict[str, int] = {}
    for ch in text:
        counts[ch] = counts.get(ch, 0) + 1
    length = len(text)
    return -sum((c / length) * math.log2(c / length) for c in counts.values())


def redact(value: str) -> str:
    """Redact a matched secret, preserving only a short prefix/suffix for triage."""
    cleaned = value.strip()
    if len(cleaned) <= 8:
        return "*" * len(cleaned)
    return f"{cleaned[:4]}...{cleaned[-4:]}"


def is_placeholder(value: str) -> bool:
    if PLACEHOLDER_RE.search(value):
        return True
    # Single repeated character (e.g., "aaaaaaaaaaaa")
    if len(set(value)) <= 3:
        return True
    return False


def is_binary_file(path: Path) -> bool:
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    try:
        with path.open("rb") as fh:
            chunk = fh.read(2048)
        return b"\x00" in chunk
    except OSError:
        return True


def iter_files(
    root: Path,
    excluded_dirs: set[str],
    excluded_files: set[str],
    max_file_bytes: int,
) -> Iterable[Path]:
    self_path = Path(__file__).resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames if d not in excluded_dirs
        )
        for filename in sorted(filenames):
            if filename in excluded_files:
                continue
            path = Path(dirpath) / filename
            try:
                if path.resolve() == self_path:
                    continue
                if path.is_symlink():
                    continue
                if path.stat().st_size > max_file_bytes:
                    continue
            except OSError:
                continue
            if is_binary_file(path):
                continue
            yield path


def scan_line(
    rel_path: str,
    line_num: int,
    line: str,
    min_entropy: float,
    enable_entropy: bool,
) -> list[Finding]:
    findings: list[Finding] = []
    matched_spans: list[tuple[int, int]] = []

    # 1. Provider-specific high-confidence regexes
    for rule_id, severity, desc, pattern in PROVIDER_PATTERNS:
        for match in pattern.finditer(line):
            value = match.group(0)
            if is_placeholder(value):
                continue
            matched_spans.append(match.span())
            findings.append(
                Finding(
                    file=rel_path,
                    line=line_num,
                    rule_id=rule_id,
                    severity=severity,
                    description=desc,
                    redacted_match=redact(value),
                )
            )

    # 2. Generic secret variable assignments
    for match in GENERIC_ASSIGNMENT_RE.finditer(line):
        value = match.group("value")
        if is_placeholder(value):
            continue
        if any(s <= match.start("value") and match.end("value") <= e for s, e in matched_spans):
            continue
        matched_spans.append(match.span("value"))
        findings.append(
            Finding(
                file=rel_path,
                line=line_num,
                rule_id="generic-secret-assignment",
                severity="medium",
                description=f"Potential hardcoded secret assigned to {match.group('name')}",
                redacted_match=redact(value),
            )
        )

    # 3. High-entropy quoted string literals
    if enable_entropy:
        for match in QUOTED_LITERAL_RE.finditer(line):
            value = match.group(2)
            if is_placeholder(value) or NON_SECRET_LITERAL_RE.match(value):
                continue
            if any(s <= match.start(2) and match.end(2) <= e for s, e in matched_spans):
                continue
            # Require mix of character classes to reduce false positives on long identifiers
            has_upper = any(c.isupper() for c in value)
            has_lower = any(c.islower() for c in value)
            has_digit = any(c.isdigit() for c in value)
            if (has_upper + has_lower + has_digit) < 3:
                continue
            entropy = shannon_entropy(value)
            if entropy >= min_entropy:
                findings.append(
                    Finding(
                        file=rel_path,
                        line=line_num,
                        rule_id="high-entropy-literal",
                        severity="low",
                        description=f"High-entropy string literal (entropy={entropy:.2f}, len={len(value)})",
                        redacted_match=redact(value),
                    )
                )

    return findings


def scan_path(
    target: Path,
    excluded_dirs: set[str],
    excluded_files: set[str],
    min_entropy: float,
    enable_entropy: bool,
    max_file_bytes: int,
) -> tuple[int, list[Finding]]:
    findings: list[Finding] = []
    files_scanned = 0

    if target.is_file():
        files: Iterable[Path] = [target]
        base = target.parent
    else:
        files = iter_files(target, excluded_dirs, excluded_files, max_file_bytes)
        base = target

    for path in files:
        files_scanned += 1
        rel_path = str(path.relative_to(base)) if path != base else path.name
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line_num, line in enumerate(text.splitlines(), start=1):
            findings.extend(
                scan_line(rel_path, line_num, line, min_entropy, enable_entropy)
            )

    return files_scanned, findings


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deterministically scan a codebase for potential API keys and secrets."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="File or directory to scan (default: current directory).",
    )
    parser.add_argument(
        "--exclude-dir",
        action="append",
        default=[],
        help="Additional directory name to exclude (repeatable).",
    )
    parser.add_argument(
        "--min-entropy",
        type=float,
        default=4.3,
        help="Minimum Shannon entropy for flagging quoted literals (default: 4.3).",
    )
    parser.add_argument(
        "--no-entropy",
        action="store_true",
        help="Disable high-entropy literal detection (regex rules only).",
    )
    parser.add_argument(
        "--max-file-bytes",
        type=int,
        default=1_048_576,
        help="Skip files larger than this size in bytes (default: 1048576).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Emit results as JSON.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    target = Path(args.path).resolve()
    if not target.exists():
        print(f"Error: path does not exist: {target}", file=sys.stderr)
        return 2

    excluded_dirs = DEFAULT_EXCLUDED_DIRS | set(args.exclude_dir)
    files_scanned, findings = scan_path(
        target=target,
        excluded_dirs=excluded_dirs,
        excluded_files=DEFAULT_EXCLUDED_FILES,
        min_entropy=args.min_entropy,
        enable_entropy=not args.no_entropy,
        max_file_bytes=args.max_file_bytes,
    )

    if args.as_json:
        payload = {
            "target": str(target),
            "files_scanned": files_scanned,
            "finding_count": len(findings),
            "findings": [asdict(f) for f in findings],
        }
        print(json.dumps(payload, indent=2))
    else:
        print(f"Scanned {files_scanned} file(s) under {target}")
        if not findings:
            print("No potential API keys or secrets detected.")
        else:
            print(f"Found {len(findings)} potential secret(s):\n")
            for f in findings:
                print(
                    f"[{f.severity.upper()}] {f.file}:{f.line} "
                    f"({f.rule_id}) {f.description} -> {f.redacted_match}"
                )

    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
