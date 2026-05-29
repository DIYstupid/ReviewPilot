from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess, run
from urllib.parse import quote

from reviewpilot.fetcher.github_api import PullRequestRef


class GitLocalError(RuntimeError):
    """Raised when a local git command fails."""


def repo_checkout_dir(base_dir: Path, owner: str, repo: str, pr_number: int) -> Path:
    return base_dir / owner / repo / f"pr-{pr_number}"


def build_repo_url(owner: str, repo: str, *, token: str | None = None) -> str:
    if token:
        escaped_token = quote(token, safe="")
        return f"https://x-access-token:{escaped_token}@github.com/{owner}/{repo}.git"
    return f"https://github.com/{owner}/{repo}.git"


def redact_repo_url(value: str) -> str:
    marker = "https://x-access-token:"
    if marker not in value:
        return value
    prefix, rest = value.split(marker, 1)
    if "@" not in rest:
        return value
    _, suffix = rest.split("@", 1)
    return f"{prefix}{marker}***@{suffix}"


def clone_pull_request_head(
    ref: PullRequestRef,
    *,
    base_dir: Path,
    token: str | None = None,
    depth: int = 1,
    git_executable: str = "git",
) -> Path:
    checkout_dir = repo_checkout_dir(base_dir, ref.owner, ref.repo, ref.number)
    remote_url = build_repo_url(ref.owner, ref.repo, token=token)
    redacted_remote_url = redact_repo_url(remote_url)
    refspec = f"pull/{ref.number}/head"

    checkout_dir.parent.mkdir(parents=True, exist_ok=True)
    if not checkout_dir.exists():
        _run_git(
            [
                git_executable,
                "clone",
                "--depth",
                str(depth),
                "--no-checkout",
                remote_url,
                str(checkout_dir),
            ],
            redacted_args=[
                git_executable,
                "clone",
                "--depth",
                str(depth),
                "--no-checkout",
                redacted_remote_url,
                str(checkout_dir),
            ],
        )

    _run_git(
        [
            git_executable,
            "-C",
            str(checkout_dir),
            "fetch",
            "--depth",
            str(depth),
            "origin",
            refspec,
        ]
    )
    _run_git([git_executable, "-C", str(checkout_dir), "checkout", "--detach", "FETCH_HEAD"])
    return checkout_dir


def _run_git(args: list[str], *, redacted_args: list[str] | None = None) -> None:
    result: CompletedProcess[str] = run(
        args,
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        safe_args = redacted_args or args
        stderr = redact_repo_url(result.stderr.strip())
        command = " ".join(safe_args)
        raise GitLocalError(f"Git command failed ({result.returncode}): {command}\n{stderr}")
