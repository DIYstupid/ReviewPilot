from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import create_engine

from reviewpilot.db import list_feedback
from reviewpilot.main import app


def test_create_feedback_persists_form_payload(tmp_path: Path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'feedback.db'}")
    monkeypatch.setattr("reviewpilot.db.get_engine", lambda database_url=None: engine)
    client = TestClient(app)

    response = client.post(
        "/feedback",
        content="job_id=job-1&finding_key=app.py%3A1%3ARisk&vote=up&comment=useful",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )

    records = list_feedback(engine=engine)
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert records[0].job_id == "job-1"
    assert records[0].finding_key == "app.py:1:Risk"
    assert records[0].vote == "up"
    assert records[0].comment == "useful"


def test_create_feedback_accepts_json_payload(tmp_path: Path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'feedback.db'}")
    monkeypatch.setattr("reviewpilot.db.get_engine", lambda database_url=None: engine)
    client = TestClient(app)

    response = client.post(
        "/feedback",
        json={"job_id": "job-1", "finding_key": "risk-1", "vote": "down"},
    )

    records = list_feedback(engine=engine)
    assert response.status_code == 200
    assert records[0].vote == "down"


def test_create_feedback_rejects_invalid_vote(tmp_path: Path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'feedback.db'}")
    monkeypatch.setattr("reviewpilot.db.get_engine", lambda database_url=None: engine)
    client = TestClient(app)

    response = client.post(
        "/feedback",
        content="job_id=job-1&vote=maybe",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid vote"
    assert list_feedback(engine=engine) == []
