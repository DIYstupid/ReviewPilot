import pytest
from fastapi.testclient import TestClient

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


def test_create_review_returns_503_for_pipeline_configuration_error(
    monkeypatch,
) -> None:
    job_store.clear()
    client = TestClient(app)

    def fail_review(pr_url: str):
        _ = pr_url
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
