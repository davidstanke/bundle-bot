"""Local LLM-as-judge for `custom_response_quality` (see eval_config.yaml)."""

import os
import threading

import google.auth
from google import genai
from google.genai import types
from pydantic import BaseModel

_local = threading.local()


class _Verdict(BaseModel):
    score: int  # 1-5
    explanation: str


def _client() -> genai.Client:
    """One client per grading thread.

    The eval SDK grades cases on its own thread pool; this initialization runs once
    per thread. Avoids creating a new client for each eval case, which would re-do
    ADC and the TLS handshake every time. Each thread gets its own client, because
    google-auth freezes the SSL context after the first connection when a client
    certificate is present.
    """
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
        # AI Studio (GEMINI_API_KEY) or Gemini platform (ADC).
        client = _local.client = genai.Client()
    return client


def evaluate(instance):
    reference = instance.get("reference")
    rubric_groups = instance.get("rubric_groups") or {}
    case_rubrics = [
        f"- [{r.get('rubric_id', 'criterion')}] {r['content']['property']['description']}"
        for group in rubric_groups.values()
        for r in group.get("rubrics", [])
        if "content" in r and "property" in r["content"]
    ]
    rubric = (
        "Grade the agent's final response on a 1-5 scale (1 poor, 5 excellent) for "
        "accuracy, relevance, and clarity."
    )
    if reference:
        rubric += (
            " The response should agree with the expected answer below; penalize "
            "factual disagreement with it."
        )
    if case_rubrics:
        rubric += (
            " Verify that the response satisfies every case-specific domain rubric "
            "listed below."
        )
    prompt = (
        f"You are an expert QA evaluator for an enterprise AI assistant. {rubric}\n"
        f"User Prompt: {instance.get('prompt', '')}\n"
        f"Final Response: {instance.get('response', '')}\n"
    )
    if reference:
        prompt += f"Expected Answer (ground truth): {reference}\n"
    if case_rubrics:
        prompt += "Case-Specific Domain Rubrics:\n" + "\n".join(case_rubrics) + "\n"
    prompt += f"Full Agent Trace: {instance.get('agent_data', '')}\n"

    response = _client().models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0,  # deterministic grading
            response_mime_type="application/json",
            response_schema=_Verdict,  # guaranteed schema-valid JSON
        ),
    )
    verdict = response.parsed
    if verdict is None:  # model returned nothing usable
        return {"score": 0, "explanation": response.text or ""}
    return {"score": max(1, min(5, verdict.score)), "explanation": verdict.explanation}
