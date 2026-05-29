from dataclasses import dataclass


@dataclass(frozen=True)
class PullRequestRef:
    owner: str
    repo: str
    number: int


def parse_pr_url(url: str) -> PullRequestRef:
    parts = url.rstrip("/").split("/")
    if len(parts) < 7 or parts[-2] != "pull":
        raise ValueError("Expected a GitHub pull request URL")
    return PullRequestRef(owner=parts[-4], repo=parts[-3], number=int(parts[-1]))
