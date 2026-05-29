import pytest
from fastapi.testclient import TestClient

from reviewpilot.analyzer.schemas import ReviewFinding, ReviewReport, Severity
from reviewpilot.main import app
from reviewpilot.review_service import ReviewConfigurationError, job_store


@pytest.fixture(autouse=True)
def offline_review_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSettings:
        review_fetch_mode = "offline"
        review_llm_provider = "offline"

    monkeypatch.setattr("reviewpilot.review_service.get_settings", lambda: FakeSettings())


def test_create_review_redirects_to_review_page() -> None:
    job_store.clear()
    client = TestClient(app)

    response = client.post(
        "/review",
        content="pr_url=https%3A%2F%2Fgithub.com%2Fowner%2Frepo%2Fpull%2F1",
        headers={"content-type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/review/owner-repo-1-")


def test_review_page_renders_pending_job_and_stream_target() -> None:
    job_store.clear()
    client = TestClient(app)
    job = job_store.create_pending("https://github.com/owner/repo/pull/1")

    response = client.get(f"/review/{job.job_id}")

    assert response.status_code == 200
    assert f'data-review-stream-url="/review/{job.job_id}/stream"' in response.text
    assert "owner/repo#1" in response.text
    assert "Review running" in response.text
    assert "Queued" in response.text


def test_review_page_renders_complete_report() -> None:
    job_store.clear()
    client = TestClient(app)
    job = job_store.create_pending("https://github.com/owner/repo/pull/1")
    report = ReviewReport(
        summary="Parser now handles renamed fields.",
        merge_conclusion="Merge is not recommended until P1 bugs are fixed.",
        risks=[
            ReviewFinding(
                severity=Severity.p1,
                title="Missing fallback for old field",
                evidence="app.py:12 removed legacy_name",
                confidence=0.82,
                recommendation="Keep a compatibility fallback.",
                file_path="app.py",
                line_number=12,
            )
        ],
        inline_reviews=[
            ReviewFinding(
                severity=Severity.p2,
                title="Extract repeated parsing branch",
                evidence="+ if payload.get('new_name')",
                confidence=0.67,
                recommendation="Move the branch into a helper.",
                file_path="app.py",
                line_number=18,
            )
        ],
    )
    job_store.complete(job.job_id, report)

    response = client.get(f"/review/{job.job_id}")

    assert response.status_code == 200
    assert "Parser now handles renamed fields." in response.text
    assert "Merge is not recommended until P1 bugs are fixed." in response.text
    assert "Missing fallback for old field" in response.text
    assert "app.py:12" in response.text
    assert "Extract repeated parsing branch" in response.text
    assert "67%" in response.text


def test_review_page_renders_failed_job_error() -> None:
    job_store.clear()
    client = TestClient(app)
    job = job_store.create_pending("https://github.com/owner/repo/pull/1")
    job_store.fail(job.job_id, "review failed")

    response = client.get(f"/review/{job.job_id}")

    assert response.status_code == 200
    assert "Review failed" in response.text
    assert "review failed" in response.text


def test_stream_review_returns_status_and_report_events() -> None:
    job_store.clear()
    client = TestClient(app)
    create_response = client.post(
        "/review",
        content="pr_url=https%3A%2F%2Fgithub.com%2Fowner%2Frepo%2Fpull%2F1",
        headers={"content-type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )
    job_path = create_response.headers["location"]

    stream_response = client.get(f"{job_path}/stream")

    assert stream_response.status_code == 200
    assert "event: status" in stream_response.text
    assert "event: report" in stream_response.text
    assert '"status": "pending"' in stream_response.text
    assert '"status": "complete"' in stream_response.text
    assert "owner/repo#1" in stream_response.text


def test_review_page_loads_sse_client_asset() -> None:
    client = TestClient(app)

    response = client.get("/static/js/htmx-sse.js")

    assert response.status_code == 200
    assert "EventSource" in response.text


def test_create_review_returns_503_for_pipeline_configuration_error(
    monkeypatch,
) -> None:
    job_store.clear()
    client = TestClient(app)

    def fail_review(pr_url: str, **kwargs):
        _ = pr_url, kwargs
        raise ReviewConfigurationError("Unsupported review_fetch_mode: custom")

    monkeypatch.setattr("reviewpilot.api.review.create_pending_configured_review_job", fail_review)

    response = client.post(
        "/review",
        content="pr_url=https%3A%2F%2Fgithub.com%2Fowner%2Frepo%2Fpull%2F1",
        headers={"content-type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Unsupported review_fetch_mode: custom"
