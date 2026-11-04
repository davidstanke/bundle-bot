# Application Default Credentials (ADC) Configuration

When building, updating, or running agent entrypoints, evaluation judges, or local playground servers in this repository:

1. **Vertex AI / ADC Priority**: Never require or prompt for `GEMINI_API_KEY`. The workspace exclusively authenticates via Google Cloud Application Default Credentials (ADC) backed by Vertex AI.
2. **Environment Fallback in Python Entrypoints**: In agent entrypoints (e.g. `app/agent.py`) and custom LLM judges (e.g. `tests/eval/*.py`), always initialize ADC environment defaults before instantiating models or agents:
   - Resolve the default project via `google.auth.default()` and set `os.environ.setdefault("GOOGLE_CLOUD_PROJECT", _default_project)`.
   - Set `os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")`.
   - Set `os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")` if neither `GOOGLE_GENAI_USE_VERTEXAI` nor `GOOGLE_GENAI_USE_ENTERPRISE` is set.
3. **Environment Template**: Always maintain `.env.example` with `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`, and `GOOGLE_CLOUD_LOCATION`.
4. **Git Hygiene**: Keep `.env` and `.google-agents-cli/` in `.gitignore`.
5. **Local Server & CLI Execution**: When launching `agents-cli playground`, `agents-cli run`, or `agents-cli eval run`, ensure `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_LOCATION=us-central1`, and `GOOGLE_CLOUD_PROJECT="$(gcloud config get-value project)"` are active in the environment.

