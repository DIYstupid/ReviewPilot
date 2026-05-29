from dataclasses import dataclass


@dataclass(frozen=True)
class GitHubOAuthConfig:
    client_id: str
    client_secret: str
    callback_url: str
