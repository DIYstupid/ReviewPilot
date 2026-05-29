# ReviewPilot

ReviewPilot is a FastAPI + Jinja2 + HTMX application for AI-assisted GitHub pull
request review. Given a PR URL, it builds review context from the PR diff and
changed files, then generates a structured review report with:

- Markdown summary of the author's intent and changed areas
- risk findings with severity, confidence, file and line evidence
- inline review suggestions for changed hunks
- merge recommendation
- optional feedback persistence for generated findings

The default mode is offline-safe, so the app and tests can run without GitHub or
LLM credentials. Live review mode can fetch GitHub PRs and call DeepSeek through
an OpenAI-compatible chat completion API.

## Requirements

- Python 3.11 or newer
- Git, required for local checkout helpers
- A GitHub token for live PR fetching, especially for private repositories
- A DeepSeek or Qwen API key if you want real LLM analysis

Dependencies are pinned in `requirements*.txt`. This project does not require
`uv`.

## Install

Create or activate your Python environment, then install development
dependencies:

```powershell
python -m pip install -r requirements-dev.txt
```

If you only need runtime dependencies:

```powershell
python -m pip install -r requirements.txt
```

Optional Semgrep dependencies are needed if you use `REVIEW_STATIC_VALIDATOR=semgrep`
or `ruff+semgrep`:

```powershell
python -m pip install -r requirements-optional.txt
```

## Configure

Copy the example environment file and edit local values:

```powershell
Copy-Item .env.example .env
```

Offline mode is the default and does not need secrets:

```env
REVIEW_FETCH_MODE=offline
REVIEW_LLM_PROVIDER=offline
REVIEW_STATIC_VALIDATOR=none
```

Use this mode for UI checks, tests, and local pipeline smoke tests. It does not
fetch real PR content.

For live GitHub + DeepSeek review:

```env
APP_SECRET_KEY=replace-with-a-local-random-secret
REVIEW_FETCH_MODE=github
REVIEW_LLM_PROVIDER=deepseek
REVIEW_STATIC_VALIDATOR=ruff
GITHUB_PAT=github_pat_or_fine_grained_token
DEEPSEEK_API_KEY=deepseek_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

`REVIEW_STATIC_VALIDATOR` runs static analysis tools against fetched file contents
and merges diagnostics into the risk list. Supported values: `ruff`, `semgrep`,
or `ruff+semgrep` to run both.

To use Qwen instead of DeepSeek:

```env
REVIEW_LLM_PROVIDER=qwen
QWEN_API_KEY=your_qwen_key
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen2.5-coder
```

Production deployments should split the session secret into separate signing and
encryption keys:

```env
APP_SECRET_KEY=replace-with-a-local-random-secret
SESSION_SIGNING_KEY=replace-with-a-local-random-signing-key
SESSION_ENCRYPTION_KEY=replace-with-a-local-random-encryption-key
APP_ENV=production
```

Supported configuration values:

| Variable | Default | Values |
| --- | --- | --- |
| `REVIEW_FETCH_MODE` | `offline` | `offline`, `github` |
| `REVIEW_LLM_PROVIDER` | `offline` | `offline`, `deepseek`, `qwen` |
| `REVIEW_STATIC_VALIDATOR` | `none` | `none`, `ruff`, `semgrep`, `ruff+semgrep` |

GitHub OAuth login is optional. Configure it if you want the browser session to
provide the GitHub token instead of relying only on `GITHUB_PAT`:

```env
GITHUB_CLIENT_ID=your_oauth_client_id
GITHUB_CLIENT_SECRET=your_oauth_client_secret
APP_SECRET_KEY=replace-with-a-local-random-secret
```

GitHub OAuth App settings for local development:

```text
Homepage URL: http://localhost:8000
Callback URL: http://localhost:8000/auth/github/callback
```

## Run The Web App

Start the local server:

```powershell
python -m uvicorn reviewpilot.main:app --host 127.0.0.1 --port 8000 --reload
```

Open:

```text
http://127.0.0.1:8000/
```

Use the review form:

1. Paste a GitHub PR URL, for example `https://github.com/OWNER/REPO/pull/123`.
2. Submit the form.
3. The result page opens at `/review/{job_id}`.
4. Progress is streamed through `/review/{job_id}/stream`.
5. When complete, the page shows Summary, Merge Conclusion, Risks, Inline
   Reviews, and feedback buttons.

If OAuth is configured, visit `/auth/github/login` first, complete GitHub login,
and then submit PR URLs from the web UI.

## CLI

The CLI provides `fetch` and `review` subcommands.

### Fetch PR snapshots

Fetch PR metadata, commits, changed files, and diff as JSON:

```powershell
python -m reviewpilot fetch https://github.com/OWNER/REPO/pull/123
```

Print only the unified diff:

```powershell
python -m reviewpilot fetch https://github.com/OWNER/REPO/pull/123 --format diff
```

Use a token explicitly:

```powershell
python -m reviewpilot fetch https://github.com/OWNER/REPO/pull/123 --token github_pat_or_token
```

If `--token` is omitted, the CLI reads `GITHUB_PAT` or `GITHUB_TOKEN` from the
environment.

### Run a full review

Run the configured AI review pipeline and print a Markdown report:

```powershell
python -m reviewpilot review https://github.com/OWNER/REPO/pull/123
```

Options:

```powershell
python -m reviewpilot review <pr_url> \
  --format json|markdown \   # default: markdown
  --out report.md \          # write to file instead of stdout
  --token github_pat \       # GitHub token (falls back to env)
  --post-comment             # post review summary as a PR comment
```

Pipeline configuration (`REVIEW_FETCH_MODE`, `REVIEW_LLM_PROVIDER`,
`REVIEW_STATIC_VALIDATOR`) is read from `.env` / environment variables.

## Development Checks

Run the full test suite:

```powershell
python -m pytest
```

Run lint checks:

```powershell
python -m ruff check .
```

Compile Python files:

```powershell
python -m compileall reviewpilot tests
```

## Project Layout

```text
reviewpilot/
  api/          FastAPI routes for review, auth, and feedback
  analyzer/     summary, risk, line-review agents and prompts
  auth/         GitHub OAuth and signed session helpers
  context/      diff parsing, file trimming, multi-language AST context
  fetcher/      GitHub API and local git checkout helpers
  post/         finding merge, sorting, confidence, report assembly
  static/       CSS and JavaScript for the HTMX/SSE UI
  templates/    Jinja2 pages and report partials
  validator/    Ruff and Semgrep validator integration points
tests/          unit and API tests
docs/           design, prompts, slides, and handoff notes
examples/       sample PR payloads
```

## Current Limitations

- Diff hunk review is capped at 20 hunks per job (a P3 finding is emitted when
  truncation occurs).
- `get_settings()` caches the first read; runtime env changes require a restart.
- Frontend report streaming depends on a browser `EventSource` connection; there
  is no reconnect with missed-event catch-up.
