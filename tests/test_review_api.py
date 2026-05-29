from fastapi.testclient import TestClient

from reviewpilot.main import app
from reviewpilot.review_service import job_store


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
    assert "owner/repo#1" in stream_response.text
