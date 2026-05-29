import pytest

from reviewpilot.analyzer.llm import LLMRequest, LLMResponse
from reviewpilot.analyzer.schemas import ReviewFinding, ReviewReport, Severity
from reviewpilot.review_service import (
    ReviewConfigurationError,
    ReviewPipelineClients,
    build_review_pipeline_clients,
    build_static_validator,
    create_configured_review_job,
    create_deepseek_review_job,
    create_github_review_job,
    create_offline_review_job,
    create_pending_configured_review_job,
    create_review_job,
    job_store,
    run_configured_review_job,
    stable_job_id,
)
from reviewpilot.fetcher.github_api import (
    ChangedFile,
    PullRequestMetadata,
    PullRequestRef,
    PullRequestSnapshot,
)


class FakeSnapshotFetcher:
    def __init__(self, snapshot: PullRequestSnapshot) -> None:
        self.snapshot = snapshot
        self.ref: PullRequestRef | None = None

    async def __call__(self, ref: PullRequestRef) -> PullRequestSnapshot:
        self.ref = ref
        return self.snapshot


class FakeClient:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = responses
        self.requests: list[LLMRequest] = []

    async def complete(self, request: LLMRequest, use_cache: bool = True) -> LLMResponse:
        self.requests.append(request)
        return self.responses.pop(0)


def test_stable_job_id_is_deterministic() -> None:
    ref = PullRequestRef(owner="owner", repo="repo", number=1)

    assert stable_job_id(ref) == stable_job_id(ref)
    assert stable_job_id(ref).startswith("owner-repo-1-")


@pytest.mark.asyncio
async def test_create_offline_review_job_stores_complete_report() -> None:
    job_store.clear()

    job = await create_offline_review_job("https://github.com/owner/repo/pull/1")

    assert job.status == "complete"
    assert job.report is not None
    assert "owner/repo#1" in job.report.summary
    assert job_store.get(job.job_id) == job


def test_create_pending_configured_review_job_stores_pending_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_store.clear()

    class FakeSettings:
        review_fetch_mode = "offline"
        review_llm_provider = "offline"

    monkeypatch.setattr("reviewpilot.review_service.get_settings", lambda: FakeSettings())

    job = create_pending_configured_review_job("https://github.com/owner/repo/pull/1")

    assert job.status == "pending"
    assert job.events[0].event == "status"
    assert job.events[0].data == {"job_id": job.job_id, "status": "pending"}
    assert job_store.get(job.job_id) == job


def test_job_store_clears_github_token_on_terminal_state() -> None:
    job_store.clear()
    pending = job_store.create_pending(
        "https://github.com/owner/repo/pull/1",
        github_token="oauth-token",
    )
    completed = job_store.complete(
        pending.job_id,
        ReviewReport(summary="ok", risks=[], inline_reviews=[], merge_conclusion="ok"),
    )

    failed_pending = job_store.create_pending(
        "https://github.com/owner/repo/pull/2",
        github_token="oauth-token",
    )
    failed = job_store.fail(failed_pending.job_id, "failed")

    assert completed.github_token is None
    assert failed.github_token is None


@pytest.mark.asyncio
async def test_run_configured_review_job_records_status_and_report_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_store.clear()

    class FakeSettings:
        review_fetch_mode = "offline"
        review_llm_provider = "offline"

    monkeypatch.setattr("reviewpilot.review_service.get_settings", lambda: FakeSettings())
    pending = create_pending_configured_review_job("https://github.com/owner/repo/pull/1")

    job = await run_configured_review_job(pending.job_id)

    assert job.status == "complete"
    assert job.report is not None
    assert [event.data.get("status") for event in job.events if event.event == "status"] == [
        "pending",
        "fetching",
        "building_context",
        "analyzing_summary",
        "analyzing_risks",
        "analyzing_lines",
        "validating_static",
        "postprocessing",
        "complete",
    ]
    assert any(event.event == "report" for event in job.events)


@pytest.mark.asyncio
async def test_run_configured_review_job_records_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    job_store.clear()

    class FakeSettings:
        review_fetch_mode = "offline"
        review_llm_provider = "offline"

    async def fail_review(pr_url: str, **kwargs):
        _ = pr_url, kwargs
        raise RuntimeError("review failed")

    monkeypatch.setattr("reviewpilot.review_service.get_settings", lambda: FakeSettings())
    monkeypatch.setattr("reviewpilot.review_service.create_configured_review_job", fail_review)
    pending = create_pending_configured_review_job("https://github.com/owner/repo/pull/1")

    job = await run_configured_review_job(pending.job_id)

    assert job.status == "failed"
    assert job.error == "review failed"
    assert job.events[-2].event == "error"
    assert job.events[-1].data["status"] == "failed"


@pytest.mark.asyncio
async def test_create_configured_review_job_defaults_to_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    job_store.clear()

    class FakeSettings:
        review_fetch_mode = "offline"
        review_llm_provider = "offline"

    monkeypatch.setattr("reviewpilot.review_service.get_settings", lambda: FakeSettings())

    job = await create_configured_review_job("https://github.com/owner/repo/pull/1")

    assert job.status == "complete"
    assert job.report is not None
    assert "owner/repo#1" in job.report.summary


@pytest.mark.asyncio
async def test_create_configured_review_job_can_use_github_and_deepseek(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_store.clear()
    llm_client = FakeClient(
        [
            LLMResponse(content="Configured summary", model="deepseek-chat"),
            LLMResponse(
                content="""{"risks":[{"severity":"P1","title":"Risk","evidence":"diff","confidence":0.8,"recommendation":"Fix","file_path":"app.py","line_number":2}]}""",
                model="deepseek-chat",
            ),
            LLMResponse(
                content="""{"inline_reviews":[{"severity":"P2","title":"Inline","evidence":"line","confidence":0.7,"recommendation":"Clean up","file_path":"app.py","line_number":2}]}""",
                model="deepseek-chat",
            ),
        ]
    )

    class FakeSettings:
        review_fetch_mode = "github"
        review_llm_provider = "deepseek"
        github_pat = "test-token"

    class FakeGitHubClient:
        token: str | None = None

        def __init__(self, token: str | None = None) -> None:
            FakeGitHubClient.token = token

        async def fetch_pull_request(self, ref: PullRequestRef) -> PullRequestSnapshot:
            return _make_snapshot(ref)

        async def fetch_changed_file_contents(
            self,
            snapshot: PullRequestSnapshot,
        ) -> dict[str, str]:
            _ = snapshot
            return {"app.py": "def changed():\n    return helper()\n"}

    monkeypatch.setattr("reviewpilot.review_service.get_settings", lambda: FakeSettings())
    monkeypatch.setattr("reviewpilot.review_service.create_deepseek_client", lambda: llm_client)
    monkeypatch.setattr("reviewpilot.review_service.GitHubClient", FakeGitHubClient)

    job = await create_configured_review_job("https://github.com/owner/repo/pull/2")

    assert FakeGitHubClient.token == "test-token"
    assert job.report is not None
    assert job.report.summary == "Configured summary"
    assert job.report.risks[0].title == "Risk"
    assert job.report.inline_reviews[0].title == "Inline"
    assert [request.metadata["agent"] for request in llm_client.requests] == [
        "summary",
        "risk",
        "line_review",
    ]


@pytest.mark.asyncio
async def test_create_configured_review_job_prefers_oauth_token_for_github(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_store.clear()

    class FakeSettings:
        review_fetch_mode = "github"
        review_llm_provider = "offline"
        github_pat = "pat-token"

    class FakeGitHubClient:
        token: str | None = None

        def __init__(self, token: str | None = None) -> None:
            FakeGitHubClient.token = token

        async def fetch_pull_request(self, ref: PullRequestRef) -> PullRequestSnapshot:
            return _make_snapshot(ref)

        async def fetch_changed_file_contents(
            self,
            snapshot: PullRequestSnapshot,
        ) -> dict[str, str]:
            _ = snapshot
            return {"app.py": "def changed():\n    return helper()\n"}

    monkeypatch.setattr("reviewpilot.review_service.get_settings", lambda: FakeSettings())
    monkeypatch.setattr("reviewpilot.review_service.GitHubClient", FakeGitHubClient)

    job = await create_configured_review_job(
        "https://github.com/owner/repo/pull/2",
        github_token="oauth-token",
    )

    assert FakeGitHubClient.token == "oauth-token"
    assert job.report is not None


@pytest.mark.asyncio
async def test_create_review_job_uses_injected_snapshot_and_clients() -> None:
    job_store.clear()
    snapshot = _make_snapshot()
    fetcher = FakeSnapshotFetcher(snapshot)
    summary_client = FakeClient([LLMResponse(content="Model summary", model="deepseek-chat")])
    risk_client = FakeClient(
        [
            LLMResponse(
                content="""{"risks":[{"severity":"P1","title":"Risk","evidence":"diff","confidence":0.8,"recommendation":"Fix","file_path":"app.py","line_number":2}]}""",
                model="deepseek-chat",
            )
        ]
    )
    line_client = FakeClient(
        [
            LLMResponse(
                content="""{"inline_reviews":[{"severity":"P2","title":"Inline","evidence":"line","confidence":0.7,"recommendation":"Clean up","file_path":"app.py","line_number":2}]}""",
                model="deepseek-chat",
            )
        ]
    )

    job = await create_review_job(
        "https://github.com/owner/repo/pull/2",
        snapshot_fetcher=fetcher,
        clients=ReviewPipelineClients(
            summary=summary_client,
            risk=risk_client,
            line_review=line_client,
        ),
        file_contents={"app.py": "def changed():\n    return helper()\n"},
    )

    assert fetcher.ref == PullRequestRef(owner="owner", repo="repo", number=2)
    assert job.status == "complete"
    assert job.report is not None
    assert job.report.summary == "Model summary"
    assert job.report.risks[0].title == "Risk"
    assert job.report.inline_reviews[0].title == "Inline"
    assert summary_client.requests[0].metadata == {"agent": "summary"}
    assert risk_client.requests[0].metadata == {"agent": "risk"}
    assert line_client.requests[0].metadata["agent"] == "line_review"
    assert job_store.get(job.job_id) == job


@pytest.mark.asyncio
async def test_create_review_job_includes_static_validator_findings() -> None:
    job_store.clear()

    async def static_validator(file_contents: dict[str, str]) -> list[ReviewFinding]:
        assert file_contents == {"app.py": "print(user)\n"}
        return [
            ReviewFinding(
                severity=Severity.p1,
                title="Ruff F821: Undefined name `user`",
                evidence="app.py:1 - F821: Undefined name `user`",
                confidence=1.0,
                recommendation="Define user before using it.",
                file_path="app.py",
                line_number=1,
                source="ruff",
            )
        ]

    job = await create_review_job(
        "https://github.com/owner/repo/pull/2",
        snapshot_fetcher=FakeSnapshotFetcher(_make_snapshot()),
        file_contents={"app.py": "print(user)\n"},
        static_validator=static_validator,
    )

    assert job.report is not None
    assert job.report.risks[0].title == "Ruff F821: Undefined name `user`"
    assert job.report.risks[0].confidence == 1.0


@pytest.mark.asyncio
async def test_create_github_review_job_uses_configured_client(monkeypatch: pytest.MonkeyPatch) -> None:
    job_store.clear()

    class FakeSettings:
        github_pat = "test-token"

    class FakeGitHubClient:
        token: str | None = None

        def __init__(self, token: str | None = None) -> None:
            FakeGitHubClient.token = token

        async def fetch_pull_request(self, ref: PullRequestRef) -> PullRequestSnapshot:
            return _make_snapshot(ref)

        async def fetch_changed_file_contents(
            self,
            snapshot: PullRequestSnapshot,
        ) -> dict[str, str]:
            _ = snapshot
            return {"app.py": "def changed():\n    return helper()\n"}

    monkeypatch.setattr("reviewpilot.review_service.get_settings", lambda: FakeSettings())
    monkeypatch.setattr("reviewpilot.review_service.GitHubClient", FakeGitHubClient)

    job = await create_github_review_job("https://github.com/owner/repo/pull/2")

    assert FakeGitHubClient.token == "test-token"
    assert job.status == "complete"
    assert job.report is not None
    assert "Fix parser" in job.report.summary


@pytest.mark.asyncio
async def test_create_github_review_job_fetches_file_contents_for_static_validator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_store.clear()

    async def static_validator(file_contents: dict[str, str]) -> list[ReviewFinding]:
        assert file_contents == {"app.py": "print(user)\n"}
        return [
            ReviewFinding(
                severity=Severity.p1,
                title="Ruff F821: Undefined name `user`",
                evidence="app.py:1 - F821: Undefined name `user`",
                confidence=1.0,
                recommendation="Define user before using it.",
                file_path="app.py",
                line_number=1,
                source="ruff",
            )
        ]

    class FakeSettings:
        github_pat = "test-token"

    class FakeGitHubClient:
        fetched_contents = False

        def __init__(self, token: str | None = None) -> None:
            _ = token

        async def fetch_pull_request(self, ref: PullRequestRef) -> PullRequestSnapshot:
            return _make_snapshot(ref)

        async def fetch_changed_file_contents(
            self,
            snapshot: PullRequestSnapshot,
        ) -> dict[str, str]:
            _ = snapshot
            FakeGitHubClient.fetched_contents = True
            return {"app.py": "print(user)\n"}

    monkeypatch.setattr("reviewpilot.review_service.get_settings", lambda: FakeSettings())
    monkeypatch.setattr("reviewpilot.review_service.GitHubClient", FakeGitHubClient)

    job = await create_github_review_job(
        "https://github.com/owner/repo/pull/2",
        static_validator=static_validator,
    )

    assert FakeGitHubClient.fetched_contents is True
    assert job.report is not None
    assert job.report.risks[0].title == "Ruff F821: Undefined name `user`"


@pytest.mark.asyncio
async def test_create_deepseek_review_job_reuses_one_client(monkeypatch: pytest.MonkeyPatch) -> None:
    job_store.clear()
    llm_client = FakeClient(
        [
            LLMResponse(content="DeepSeek summary", model="deepseek-chat"),
            LLMResponse(content="""{"risks":[]}""", model="deepseek-chat"),
            LLMResponse(content="""{"inline_reviews":[]}""", model="deepseek-chat"),
        ]
    )
    monkeypatch.setattr("reviewpilot.review_service.create_deepseek_client", lambda: llm_client)

    job = await create_deepseek_review_job(
        "https://github.com/owner/repo/pull/2",
        snapshot_fetcher=FakeSnapshotFetcher(_make_snapshot()),
    )

    assert job.report is not None
    assert job.report.summary == "DeepSeek summary"
    assert [request.metadata["agent"] for request in llm_client.requests] == [
        "summary",
        "risk",
        "line_review",
    ]


def test_build_review_pipeline_clients_rejects_unknown_provider() -> None:
    with pytest.raises(ReviewConfigurationError):
        build_review_pipeline_clients("unknown")


def test_build_static_validator_supports_ruff_and_rejects_unknown() -> None:
    assert build_static_validator("ruff") is not None
    assert build_static_validator("none") is None
    with pytest.raises(ReviewConfigurationError):
        build_static_validator("unknown")


def _make_snapshot(ref: PullRequestRef | None = None) -> PullRequestSnapshot:
    pr_ref = ref or PullRequestRef(owner="owner", repo="repo", number=2)
    return PullRequestSnapshot(
        ref=pr_ref,
        metadata=PullRequestMetadata(
            title="Fix parser",
            body="Handle changed line numbers",
            state="open",
            draft=False,
            html_url=f"https://github.com/{pr_ref.owner}/{pr_ref.repo}/pull/{pr_ref.number}",
            base_ref="main",
            head_ref="fix-parser",
            author="alice",
            changed_files=1,
            additions=1,
            deletions=1,
        ),
        commits=["abc123"],
        files=[
            ChangedFile(
                filename="app.py",
                status="modified",
                additions=1,
                deletions=1,
                changes=2,
                patch="@@ -1 +1 @@\n-a\n+b\n",
            )
        ],
        diff="""diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,2 +1,2 @@
 def changed():
-    return 1
+    return helper()
""",
    )
