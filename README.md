# ReviewPilot

AI code review assistant for GitHub pull requests.

ReviewPilot is planned as a FastAPI + Jinja2 + HTMX application that turns a GitHub PR URL into a streamed review report: change summary, risk list, inline review suggestions, and a merge recommendation.

## Local Setup

```powershell
uv sync --extra dev
uv run uvicorn reviewpilot.main:app --reload
```

Copy `.env.example` to `.env` and fill in secrets before using live GitHub or LLM integrations.
