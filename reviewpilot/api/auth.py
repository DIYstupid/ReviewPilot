from secrets import token_urlsafe

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from reviewpilot.auth.github_oauth import (
    GitHubOAuthConfig,
    GitHubOAuthError,
    build_authorization_url,
    exchange_code_for_token,
)
from reviewpilot.auth.session import (
    OAUTH_STATE_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    build_github_session,
    dump_session,
    load_session,
)
from reviewpilot.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/github/login")
async def github_login(request: Request) -> RedirectResponse:
    config = _github_oauth_config(request)
    state = token_urlsafe(24)
    response = RedirectResponse(
        build_authorization_url(config, state=state),
        status_code=status.HTTP_302_FOUND,
    )
    response.set_cookie(
        OAUTH_STATE_COOKIE_NAME,
        dump_session({"state": state}),
        max_age=600,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/github/callback")
async def github_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
) -> RedirectResponse:
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing GitHub OAuth code or state")

    expected_state = load_session(request.cookies.get(OAUTH_STATE_COOKIE_NAME)).get("state")
    if not expected_state or expected_state != state:
        raise HTTPException(status_code=400, detail="Invalid GitHub OAuth state")

    config = _github_oauth_config(request)
    try:
        token = await exchange_code_for_token(config, code)
    except GitHubOAuthError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        build_github_session(
            token.access_token,
            scope=token.scope,
            token_type=token.token_type,
        ),
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(OAUTH_STATE_COOKIE_NAME)
    return response


def _github_oauth_config(request: Request) -> GitHubOAuthConfig:
    settings = get_settings()
    if not settings.github_client_id or not settings.github_client_secret:
        raise HTTPException(status_code=503, detail="GitHub OAuth is not configured")
    return GitHubOAuthConfig(
        client_id=settings.github_client_id,
        client_secret=settings.github_client_secret,
        callback_url=str(request.url_for("github_callback")),
    )
