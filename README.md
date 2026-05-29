# ReviewPilot

AI code review assistant for GitHub pull requests.

ReviewPilot is planned as a FastAPI + Jinja2 + HTMX application that turns a GitHub PR URL into a streamed review report: change summary, risk list, inline review suggestions, and a merge recommendation.

## Local Setup

```powershell
D:\mincondapy39\envs\agent\python.exe -m pip install -r requirements-dev.txt
D:\mincondapy39\envs\agent\python.exe -m uvicorn reviewpilot.main:app --reload
```

Copy `.env.example` to `.env` and fill in secrets before using live GitHub or LLM integrations.

By default the web review flow runs in offline mode, so local tests and UI checks do not need API keys.
To enable live PR fetching and DeepSeek analysis, set:

```env
REVIEW_FETCH_MODE=github
REVIEW_LLM_PROVIDER=deepseek
REVIEW_STATIC_VALIDATOR=ruff
GITHUB_PAT=github_pat_or_token_here
DEEPSEEK_API_KEY=deepseek_key_here
```

Supported modes:

| Variable | Default | Values |
| --- | --- | --- |
| `REVIEW_FETCH_MODE` | `offline` | `offline`, `github` |
| `REVIEW_LLM_PROVIDER` | `offline` | `offline`, `deepseek` |
| `REVIEW_STATIC_VALIDATOR` | `none` | `none`, `ruff` |

## CLI

Fetch a pull request snapshot:

```powershell
D:\mincondapy39\envs\agent\python.exe -m reviewpilot fetch https://github.com/OWNER/REPO/pull/123
```

Print only the unified diff:

```powershell
D:\mincondapy39\envs\agent\python.exe -m reviewpilot fetch https://github.com/OWNER/REPO/pull/123 --format diff
```
