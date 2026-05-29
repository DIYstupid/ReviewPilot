from dataclasses import dataclass
from urllib.parse import urlencode


@dataclass(frozen=True)
class GitHubOAuthConfig:
    client_id: str
    client_secret: str
    callback_url: str


@dataclass(frozen=True)
class GitHubOAuthToken:
    access_token: str
    token_type: str = "bearer"
    scope: str = ""


class GitHubOAuthError(RuntimeError):
    """Raised when the GitHub OAuth exchange fails."""


def build_authorization_url(
    config: GitHubOAuthConfig,
    *,
    state: str,
    scope: str = "repo",
) -> str:
    query = urlencode(
        {
            "client_id": config.client_id,
            "redirect_uri": config.callback_url,
            "scope": scope,
            "state": state,
            "allow_signup": "true",
        }
    )
    return f"https://github.com/login/oauth/authorize?{query}"


async def exchange_code_for_token(
    config: GitHubOAuthConfig,
    code: str,
) -> GitHubOAuthToken:
    import httpx

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": config.client_id,
                "client_secret": config.client_secret,
                "code": code,
                "redirect_uri": config.callback_url,
            },
            headers={"Accept": "application/json"},
        )

    if response.status_code >= 400:
        raise GitHubOAuthError(f"GitHub OAuth token exchange failed: {response.status_code}")

    data = response.json()
    if data.get("error"):
        message = data.get("error_description") or data["error"]
        raise GitHubOAuthError(str(message))

    access_token = data.get("access_token")
    if not access_token:
        raise GitHubOAuthError("GitHub OAuth token response did not include access_token")

    return GitHubOAuthToken(
        access_token=str(access_token),
        token_type=str(data.get("token_type") or "bearer"),
        scope=str(data.get("scope") or ""),
    )
