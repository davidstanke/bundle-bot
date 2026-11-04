# Application Default Credentials (ADC) Configuration

When building or updating agent entrypoints, evaluation judges, or CLI scripts in this repository:

1. **Vertex AI / ADC Priority**: Never require or prompt for `GEMINI_API_KEY`. The workspace exclusively authenticates via Google Cloud Application Default Credentials (ADC) backed by Vertex AI.
2. **Environment Fallback**: In agent entrypoints (e.g. `app/agent.py`) and custom LLM judges (e.g. `tests/eval/*.py`), ensure `GOOGLE_GENAI_USE_VERTEXAI="true"` is set if neither `GOOGLE_GENAI_USE_VERTEXAI` nor `GOOGLE_GENAI_USE_ENTERPRISE` is present in `os.environ`.
3. **Environment Template**: Always maintain `.env.example` with `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`, and `GOOGLE_CLOUD_LOCATION`.
4. **Git Hygiene**: Keep `.env` and `.google-agents-cli/` in `.gitignore`.
