"""Custom LLM-as-judge evaluation metric for BundleBot B2B reseller quotes."""

from __future__ import annotations

import os
import threading
from typing import Any

from google import genai
from google.genai import types
from pydantic import BaseModel

_PROMPT_TEMPLATE = """\
You are an expert evaluator of B2B hardware and software distribution quote assistants (BundleBot).
Rate the quality of the AI assistant's response to the channel reseller's request on a scale of 1 to 5.

Evaluation Criteria:
1. Bill of Materials & SKUs: Includes concrete catalog SKUs (e.g., IM-LPT-*, IM-DCK-*, IM-MON-*, IM-PER-*, IM-SW-SEC365, IM-WAR-NBD3Y) with accurate descriptions and pricing.
2. Technical Compatibility: Verifies USB-C power delivery wattage, display interface compatibility, and software license seat/OS bounds.
3. Regional Warehouse Inventory: Checks stock in the resolved regional warehouse (US-Central Austin, US-East Harrisburg, or US-West Mira Loma) and suggests alternate warehouses or split shipments when shortfalls exist.
4. Partner Margin & Volume Tier Optimization: Reports the applied volume discount tier, customer price, reseller cost/margin, budget compliance, and proactive next-tier volume upsell (such as bumping 24 to 25 kits for the Gold Partner 12% discount when total customer spend decreases).

Scoring Rubric:
5 - Excellent: Accurately covers BOM SKUs, compatibility checks, regional warehouse stock, and volume tier/margin/upsell analysis.
4 - Good: Covers all core areas with only minor formatting or detail omissions.
3 - Adequate: Provides a kit quote but misses one of the validation, warehouse, or margin sections.
2 - Poor: Incomplete quote missing multiple required sections or containing inaccurate SKU/tier figures.
1 - Very Poor: Empty or irrelevant response that fails to address the B2B bundle request.

User Prompt: {prompt}
Assistant Response: {response}"""

_local = threading.local()


class _Verdict(BaseModel):
    score: int
    explanation: str


def _get_client() -> genai.Client:
    if not hasattr(_local, "client"):
        if (
            "GOOGLE_GENAI_USE_VERTEXAI" not in os.environ
            and "GOOGLE_GENAI_USE_ENTERPRISE" not in os.environ
        ):
            os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
        _local.client = genai.Client()
    return _local.client


def _extract_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        parts = value.get("parts") or []
        return " ".join(
            p.get("text", "") for p in parts if isinstance(p, dict) and "text" in p
        )
    return ""


def _extract_prompt(instance: dict[str, Any]) -> str:
    if "prompt" in instance and instance["prompt"]:
        text = _extract_text(instance["prompt"])
        if text:
            return text
    agent_data = instance.get("agent_data") or {}
    if isinstance(agent_data, dict):
        text = _extract_text(agent_data.get("prompt"))
        if text:
            return text
        turns = agent_data.get("turns") or []
        for turn in turns:
            if isinstance(turn, dict):
                content = turn.get("content") or turn
                text = _extract_text(content)
                if text:
                    return text
    return ""


def evaluate(instance: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a single BundleBot trace instance and return a 1-5 quality score."""
    response_text = _extract_text(instance.get("response", ""))
    if not response_text or not response_text.strip():
        return {"score": 1, "explanation": "Empty response from agent."}

    prompt_text = _extract_prompt(instance)
    result = _get_client().models.generate_content(
        model="gemini-2.5-flash",
        contents=_PROMPT_TEMPLATE.format(prompt=prompt_text, response=response_text),
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_schema=_Verdict,
        ),
    )
    verdict = result.parsed
    return {"score": verdict.score, "explanation": verdict.explanation}
