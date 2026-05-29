from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from reviewpilot.auth.session import (
    GITHUB_TOKEN_FIELD,
    OAUTH_STATE_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    decrypt_session_value,
    load_session,
)
from reviewpilot.main import app


class FakeSettings:
    app_secret_key = "test-secret"
    github_client_id = "client-id"
    github_client_secret = "client-secret"


@pytest.fixture(autouse=True)
def oauth_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("reviewpilot.api.auth.get_settings", lambda: FakeSettings())
    monkeypatch.setattr("reviewpilot.auth.session.get_settings", lambda: FakeSettings())


def test_github_login_redirects_to_authorize_url_with_state_cookie() -> None:
    client = TestClient(app)

    response = client.get("/auth/github/login", follow_redirects=False)

    assert response.status_code == 302
    location = response.headers["location"]
    parsed = urlparse(location)
    params = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "github.com"
    assert parsed.path == "/login/oauth/authorize"
    assert params["client_id"] == ["client-id"]
    assert params["redirect_uri"] == ["http://testserver/auth/github/callback"]
    assert params["scope"] == ["repo"]
    assert load_session(response.cookies.get(OAUTH_STATE_COOKIE_NAME))["state"] == params["state"][0]


def test_github_login_requires_oauth_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    class MissingSettings:
        github_client_id = None
        github_client_secret = None

    monkeypatch.setattr("reviewpilot.api.auth.get_settings", lambda: MissingSettings())
    client = TestClient(app)

    response = client.get("/auth/github/login", follow_redirects=False)

    assert response.status_code == 503
    assert response.json()["detail"] == "GitHub OAuth is not configured"


def test_github_callback_rejects_missing_state_cookie() -> None:
    client = TestClient(app)

    response = client.get("/auth/github/callback?code=abc&state=missing", follow_redirects=False)

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid GitHub OAuth state"


@respx.mock
def test_github_callback_exchanges_code_and_sets_session_cookie() -> None:
    client = TestClient(app)
    login = client.get("/auth/github/login", follow_redirects=False)
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
    token_route = respx.post("https://github.com/login/oauth/access_token").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "gho_test_token",
                "token_type": "bearer",
                "scope": "repo",
            },
        )
    )

    response = client.get(
        f"/auth/github/callback?code=oauth-code&state={state}",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    session = load_session(response.cookies.get(SESSION_COOKIE_NAME))
    assert decrypt_session_value(session[GITHUB_TOKEN_FIELD]) == "gho_test_token"
    assert token_route.called
    assert "client_id=client-id" in token_route.calls[0].request.content.decode()
    assert "code=oauth-code" in token_route.calls[0].request.content.decode()


@respx.mock
def test_github_callback_reports_token_exchange_error() -> None:
    client = TestClient(app)
    login = client.get("/auth/github/login", follow_redirects=False)
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
    respx.post("https://github.com/login/oauth/access_token").mock(
        return_value=httpx.Response(
            200,
            json={"error": "bad_verification_code", "error_description": "code expired"},
        )
    )

    response = client.get(
        f"/auth/github/callback?code=oauth-code&state={state}",
        follow_redirects=False,
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "code expired"
