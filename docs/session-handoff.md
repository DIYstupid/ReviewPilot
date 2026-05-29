# ReviewPilot Session Handoff

This document is safe to commit. It intentionally excludes local secrets and API keys.

## Current State

- Latest implementation commit before this handoff update: `6a2cedc`.
- Test suite: 85 tests were passing after the latest implementation phase.
- The project now supports an offline-safe default flow, live GitHub + DeepSeek + ruff mode, OAuth login, live SSE result rendering, local PR checkout helpers, and feedback persistence.

## Local Rules

- Do not push; only create local commits.
- Use Chinese commit messages, under 100 characters.
- Do not use `uv`; dependencies are pinned in `requirements*.txt`.
- Do not commit `.env` or `ReviewPilot-Plan.md`.
- `ReviewPilot-Plan.md` contains local secret material and is intentionally ignored.
- A local `.gitignore` change currently ignores `docs/session-handoff.md`; verify before committing if you want this file tracked in future updates.
- Use this Git form on Windows if needed:

```powershell
git -c safe.directory=D:/Forwork/ReviewPilot status --short
```

## Useful Commands

```powershell
D:\mincondapy39\envs\agent\python.exe -m pip install -r requirements-dev.txt
D:\mincondapy39\envs\agent\python.exe -m pytest
D:\mincondapy39\envs\agent\python.exe -m ruff check .
D:\mincondapy39\envs\agent\python.exe -m compileall reviewpilot tests
D:\mincondapy39\envs\agent\python.exe -m uvicorn reviewpilot.main:app --reload
```

## Configuration

Offline mode is the default and does not need secrets:

```env
REVIEW_FETCH_MODE=offline
REVIEW_LLM_PROVIDER=offline
REVIEW_STATIC_VALIDATOR=none
```

Live review mode:

```env
REVIEW_FETCH_MODE=github
REVIEW_LLM_PROVIDER=deepseek
REVIEW_STATIC_VALIDATOR=ruff
GITHUB_PAT=...
DEEPSEEK_API_KEY=...
```

OAuth login mode:

```env
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...
APP_SECRET_KEY=replace-with-local-random-secret
```

GitHub OAuth App settings:

```text
Homepage URL: http://localhost:8000
Callback URL: http://localhost:8000/auth/github/callback
```

## Completed Capabilities

- GitHub PR URL parsing.
- GitHub PR metadata, commits, changed files, unified diff fetching.
- GitHub PR head file content fetching through the contents API.
- Context builder:
  - unified diff parsing
  - hunk flattening
  - file content trimming
  - Python AST symbol context
- LLM client:
  - OpenAI-compatible chat completions
  - DeepSeek/Qwen configuration skeleton
  - request cache key and cache read/write
- Agents:
  - Summary Agent
  - Risk Agent with JSON schema parsing
  - LineReview Agent per hunk
  - offline fallback paths
- Post-processing:
  - finding merge/deduplication
  - severity/confidence sorting
  - merge conclusion
  - static validation confidence hook
- Review service:
  - injectable snapshot fetcher
  - injectable LLM clients
  - injectable static validator
  - OAuth token handoff from encrypted/signed session cookie to GitHub jobs
  - configured offline/GitHub and offline/DeepSeek paths
  - in-memory pending/running/complete/failed job lifecycle
  - event log for SSE
- API:
  - `POST /review`
  - `GET /review/{job_id}`
  - `GET /review/{job_id}/stream`
  - `GET /auth/github/login`
  - `GET /auth/github/callback`
  - `POST /feedback`
  - background review execution
  - SSE status/report/error events
- Frontend:
  - usable index form
  - live SSE status timeline
  - server-rendered and JS-rendered review reports
  - summary, merge conclusion, risk cards, inline findings, error state
  - finding feedback buttons
- Feedback persistence:
  - SQLite `FeedbackRecord`
  - form and JSON payload support
  - feedback read helper for tests/future usage
- Git local utility:
  - checkout directory builder
  - authenticated GitHub HTTPS URL builder
  - shallow clone/fetch/checkout for PR head refs
  - token redaction in git error messages
- Ruff static validation:
  - ruff JSON runner
  - file contents temp-dir execution
  - ruff diagnostics mapped to `ReviewFinding`
  - configurable with `REVIEW_STATIC_VALIDATOR=ruff`

## Key Files

- `reviewpilot/review_service.py`
- `reviewpilot/api/review.py`
- `reviewpilot/api/auth.py`
- `reviewpilot/api/feedback.py`
- `reviewpilot/auth/github_oauth.py`
- `reviewpilot/auth/session.py`
- `reviewpilot/fetcher/github_api.py`
- `reviewpilot/fetcher/git_local.py`
- `reviewpilot/validator/ruff_runner.py`
- `reviewpilot/context/builder.py`
- `reviewpilot/context/diff.py`
- `reviewpilot/context/files.py`
- `reviewpilot/context/ast_graph.py`
- `reviewpilot/analyzer/llm.py`
- `reviewpilot/analyzer/summary.py`
- `reviewpilot/analyzer/risk.py`
- `reviewpilot/analyzer/line_review.py`
- `reviewpilot/post/report.py`
- `reviewpilot/static/js/htmx-sse.js`
- `tests/test_review_service.py`
- `tests/test_review_api.py`
- `tests/test_auth_api.py`
- `tests/test_feedback_api.py`
- `tests/test_github_api.py`
- `tests/test_git_local.py`
- `tests/test_ruff_runner.py`

## Current Flow

1. `POST /review` parses `pr_url`.
2. The API reads an OAuth GitHub token from the encrypted/signed session cookie if available.
3. The API creates a pending `ReviewJob`.
4. FastAPI `BackgroundTasks` runs `run_configured_review_job`.
5. The configured pipeline chooses:
   - offline or GitHub fetch
   - offline or DeepSeek LLM
   - no static validator or ruff
6. GitHub mode fetches PR snapshot and changed file contents, using OAuth token first and `GITHUB_PAT` as fallback.
7. Context is built from metadata, diff, file contents, and Python symbols.
8. Summary, Risk, and LineReview agents run.
9. Static validator findings are merged into risks.
10. Post-processing builds `ReviewReport`.
11. SSE emits events from the job event log.
12. The result page renders progress and final report; feedback buttons persist to SQLite.

## SSE Events

Known status values:

- `pending`
- `fetching`
- `fetching_files`
- `building_context`
- `analyzing_summary`
- `analyzing_risks`
- `analyzing_lines`
- `validating_static`
- `postprocessing`
- `complete`
- `failed`

Other event names:

- `report`
- `error`

## Known Gaps

- Semgrep is still only a command placeholder.
- SQLite persistence is not implemented for jobs/reports; only feedback is persisted.
- GitHub OAuth exists, but there is no logged-in user profile page or token refresh handling.
- GitHub PR comment posting is not implemented.
- CLI only fetches PR snapshots/diffs; full CLI review is not implemented.
- Qwen provider is configured but not selected in the pipeline.
- Large PR budgets, retries, rate-limit handling, and content caching need hardening.
- Multi-language AST support is not implemented; current AST context is Python-focused.

## Suggested Next Stage

Implement SQLite-backed job/report persistence:

- Store review job status, events, errors, and final reports outside memory.
- Rehydrate `GET /review/{job_id}` and SSE event logs after process restart.
- Add tests for pending/running/complete/failed persisted jobs.

Alternative next stage: implement full CLI review output or GitHub PR comment posting.
