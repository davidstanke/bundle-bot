---
name: scrub-api-keys
description: >-
  Scans and scrubs a codebase for hardcoded API keys, tokens, and secrets using
  both a deterministic regex/entropy script and a non-deterministic semantic
  review. Use when the user asks to audit, scan, or scrub the repo for API keys,
  credentials, or secrets, or before committing or publishing code.
---

# Scrub API Keys

This skill combines **deterministic scanning** (regex + Shannon entropy) with
**non-deterministic semantic review** (LLM inspection of code, configs, and git
hygiene) to detect and safely remediate exposed API keys and secrets.

> **Security Rule:** Never print full, unredacted secret values in your final
> report or commit messages. Always redact to a short prefix/suffix (e.g.,
> `AIza...9xQp`).

---

## Step 1: Deterministic Scan (Script)

Run the bundled scanner script [scan_api_keys.py](./scripts/scan_api_keys.py)
against the target directory (default: repository root `.`):

```bash
python3 .agents/skills/scrub-api-keys/scripts/scan_api_keys.py .
```

Useful flags:
- `--json`: Structured JSON output for programmatic triage.
- `--exclude-dir <name>`: Skip additional directories (repeatable; e.g., `--exclude-dir solution` if a directory is out of scope).
- `--min-entropy <float>`: Adjust Shannon entropy threshold (default: `4.3`).
- `--no-entropy`: Run only provider and generic assignment regexes.

Exit codes:
- `0`: No deterministic findings.
- `1`: One or more candidate secrets found.
- `2`: Error.

Record every finding from Step 1; you will triage them alongside Step 2.

---

## Step 2: Non-Deterministic Scan (Semantic Review)

Deterministic patterns miss obfuscated, context-dependent, or unconventionally
named credentials. Perform a targeted semantic audit across the codebase:

1. **Check git tracking & credential file hygiene**:
   - Run `git ls-files` to check whether sensitive files are tracked in git
     (e.g., `.env`, `.env.*` other than `.env.example`, `*.pem`, `*.key`,
     `*credentials*.json`, `*service-account*.json`, `.netrc`).
   - Verify `.gitignore` excludes `.env` and any local credential files.

2. **Inspect high-risk files and patterns**:
   - Review config files (`.env.example`, `*.yaml`, `*.yml`, `*.toml`, `*.json`,
     `.github/workflows/*`), documentation (`README.md`, `docs/`), and test
     fixtures for accidentally pasted real keys.
   - Look for **non-deterministic leak patterns** that regexes miss:
     - **Default fallback secrets**: e.g., `os.getenv("API_KEY", "<real-key>")`
       or `config.get("token") or "<real-key>"`.
     - **Split, concatenated, or encoded secrets**: Base64/hex blobs, joined
       string fragments, or byte arrays reconstructed into a key at runtime.
     - **Unconventional variable names**: Secrets assigned to innocuous names
       like `val`, `cfg`, `header`, `token`, `pwd`, `key`, or inline arguments
       to SDK clients (`Client(api_key="...")`, `requests.get(..., headers=...)`).
     - **URL query credentials**: Signed URLs or endpoints containing
       `?key=...`, `?api_key=...`, `?token=...`, or `?sig=...`.
     - **Secret logging**: Code that prints or logs environment variables,
       request headers, or client configs containing credentials.

3. **Triage all findings (Deterministic + Semantic)**:
   - Classify each hit as **True Positive**, **Needs Confirmation**, or
     **False Positive** (e.g., obvious placeholder, public identifier, schema
     example, or test mock).

---

## Step 3: Report & Scrub

1. **Present a concise summary table** grouped by severity:
   - Columns: `File:Line`, `Detection` (`Deterministic` / `Semantic`), `Rule / Reason`, `Redacted Preview`, `Verdict`, `Recommended Fix`.
2. **Scrub confirmed secrets** (if the user asked to scrub/fix, or after user
   confirmation if they only asked to scan):
   - Replace hardcoded keys in source code with environment variable lookups
     (e.g., `os.environ["..."]` / `os.getenv(...)`) or Application Default
     Credentials (ADC) where appropriate.
   - Replace real keys in `.env.example`, docs, or tests with unmistakable
     placeholders (e.g., `YOUR_API_KEY_HERE`).
   - Untrack accidentally committed secret files with `git rm --cached <file>`
     and add them to `.gitignore`.
3. **Advise key rotation**:
   - Explicitly remind the user that scrubbing a key from the working tree does
     **not** invalidate it. Any real key that was committed, pushed, or shared
     must be **revoked and rotated** with the provider (and git history
     rewritten if already pushed).

---

## Step 4: Verify

Re-run the deterministic scanner after scrubbing to confirm no findings remain:

```bash
python3 .agents/skills/scrub-api-keys/scripts/scan_api_keys.py .
```

Confirm the command exits with code `0` (or that any remaining hits are
verified false positives) and run `git diff` to ensure no unintended edits were
introduced.
