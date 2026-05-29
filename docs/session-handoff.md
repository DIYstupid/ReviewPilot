# ReviewPilot Session Handoff

This document is safe to commit. It intentionally excludes local secrets and API keys.

## Current State

- Branch worktree is clean after the latest commit.
- Latest commit: `7b38513 feat: 支持抓取PR文件内容并启用ruff`
- Test suite: 65 tests were passing after the latest implementation phase.
- The project now supports an offline-safe default flow and a configurable live GitHub + DeepSeek + ruff flow.

## Local Rules

- Do not push; only create local commits.
- Use Chinese commit messages, under 100 characters.
- Do not use `uv`; dependencies are pinned in `requirements*.txt`.
- Do not commit `.env` or `ReviewPilot-Plan.md`.
- `ReviewPilot-Plan.md` contains local secret material and is intentionally ignored.
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

`GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` are not required yet because OAuth is not complete.

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
  - configured offline/GitHub and offline/DeepSeek paths
  - in-memory pending/running/complete/failed job lifecycle
  - event log for SSE
- API:
  - `POST /review`
  - `GET /review/{job_id}`
  - `GET /review/{job_id}/stream`
  - background review execution
  - SSE status/report/error events
- Ruff static validation:
  - ruff JSON runner
  - file contents temp-dir execution
  - ruff diagnostics mapped to `ReviewFinding`
  - configurable with `REVIEW_STATIC_VALIDATOR=ruff`

## Key Files

- `reviewpilot/review_service.py`
- `reviewpilot/api/review.py`
- `reviewpilot/fetcher/github_api.py`
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
- `tests/test_review_service.py`
- `tests/test_review_api.py`
- `tests/test_github_api.py`
- `tests/test_ruff_runner.py`

## Current Flow

1. `POST /review` parses `pr_url`.
2. The API creates a pending `ReviewJob`.
3. FastAPI `BackgroundTasks` runs `run_configured_review_job`.
4. The configured pipeline chooses:
   - offline or GitHub fetch
   - offline or DeepSeek LLM
   - no static validator or ruff
5. GitHub mode fetches PR snapshot and changed file contents.
6. Context is built from metadata, diff, file contents, and Python symbols.
7. Summary, Risk, and LineReview agents run.
8. Static validator findings are merged into risks.
9. Post-processing builds `ReviewReport`.
10. SSE emits events from the job event log.

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

- The result page is still minimal; HTMX/SSE rendering is not feature-complete.
- `reviewpilot/static/js/htmx-sse.js` is still a placeholder.
- Semgrep is still only a command placeholder.
- SQLite persistence is not implemented.
- Feedback persistence is not implemented.
- GitHub OAuth/private repo flow is not complete.
- GitHub PR comment posting is not implemented.
- CLI only fetches PR snapshots/diffs; full CLI review is not implemented.
- Qwen provider is configured but not selected in the pipeline.
- Large PR budgets, retries, rate-limit handling, and content caching need hardening.
- Multi-language AST support is not implemented; current AST context is Python-focused.

## Suggested Next Stage

Build the HTMX/SSE result page:

- Replace the placeholder SSE asset or add the real htmx-sse integration.
- Render live status updates.
- Render the final report into:
  - summary
  - merge conclusion
  - risk cards
  - inline findings
  - error state
- Add API/template tests for pending, complete, and failed jobs.

Alternative next stage: implement SQLite-backed job/report persistence before UI polish.
