"""Per-case domain rubric evaluator for `domain_rubric_pass_rate` (see eval_config.yaml)."""

import os
import threading

import google.auth
from google import genai
from google.genai import types
from pydantic import BaseModel

_local = threading.local()


class _RubricItemVerdict(BaseModel):
    rubric_id: str
    passed: bool
    reason: str


class _RubricEvaluation(BaseModel):
    verdicts: list[_RubricItemVerdict]


_RubricEvaluation.model_rebuild()


def _client() -> genai.Client:
    """One client per grading thread using Vertex AI ADC by default."""
    client = getattr(_local, "client", None)
    if client is None:
        if (
            "GEMINI_API_KEY" not in os.environ
            and "GOOGLE_API_KEY" not in os.environ
        ):
            os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
            os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")
            if "GOOGLE_CLOUD_PROJECT" not in os.environ:
                try:
                    _, default_project = google.auth.default()
                    if default_project:
                        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", default_project)
                except Exception:
                    pass
        client = _local.client = genai.Client()
    return client


def evaluate(instance):
    rubric_groups = instance.get("rubric_groups") or {}
    rubrics = [
        (r.get("rubric_id", "criterion"), r["content"]["property"]["description"])
        for group in rubric_groups.values()
        for r in group.get("rubrics", [])
        if "content" in r and "property" in r["content"]
    ]
    if not rubrics:
        return {"score": 1.0, "explanation": "No per-case domain rubrics specified."}

    rubrics_formatted = "\n".join(
        f"- {rubric_id}: {desc}" for rubric_id, desc in rubrics
    )
    prompt = (
        "You are an expert B2B distribution QA judge. Evaluate whether the agent's "
        "response and tool trace satisfy each domain rubric below.\n\n"
        f"User Prompt: {instance.get('prompt', '')}\n"
        f"Final Response: {instance.get('response', '')}\n"
        f"Expected Ground Truth Reference: {instance.get('reference', '')}\n"
        f"Full Agent Trace: {instance.get('agent_data', '')}\n\n"
        f"Domain Rubrics to Evaluate:\n{rubrics_formatted}\n"
    )

    response = _client().models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_schema=_RubricEvaluation,
        ),
    )
    parsed = response.parsed
    if parsed is None or not parsed.verdicts:
        return {"score": 0.0, "explanation": response.text or "No verdicts returned."}

    passed_count = sum(1 for v in parsed.verdicts if v.passed)
    total_count = len(rubrics)
    score = round(passed_count / total_count, 4)
    summary = "; ".join(
        f"{v.rubric_id}={'PASS' if v.passed else 'FAIL'} ({v.reason})"
        for v in parsed.verdicts
    )
    return {
        "score": score,
        "explanation": f"Passed {passed_count}/{total_count} domain rubrics: {summary}",
    }
