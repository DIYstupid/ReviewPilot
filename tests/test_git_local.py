from pathlib import Path
from subprocess import CompletedProcess

import pytest

from reviewpilot.fetcher.git_local import (
    GitLocalError,
    build_repo_url,
    clone_pull_request_head,
    redact_repo_url,
    repo_checkout_dir,
)
from reviewpilot.fetcher.github_api import PullRequestRef


def test_repo_checkout_dir_uses_owner_repo_and_pr_number() -> None:
    assert repo_checkout_dir(Path("cache"), "owner", "repo", 12) == Path("cache/owner/repo/pr-12")


def test_build_repo_url_injects_and_escapes_token() -> None:
    assert build_repo_url("owner", "repo") == "https://github.com/owner/repo.git"
    assert (
        build_repo_url("owner", "repo", token="gho_a/b")
        == "https://x-access-token:gho_a%2Fb@github.com/owner/repo.git"
    )


def test_redact_repo_url_removes_token() -> None:
    url = "https://x-access-token:secret@github.com/owner/repo.git"

    assert redact_repo_url(url) == "https://x-access-token:***@github.com/owner/repo.git"


def test_clone_pull_request_head_runs_clone_fetch_and_checkout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        _ = kwargs
        calls.append(args)
        return CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("reviewpilot.fetcher.git_local.run", fake_run)

    checkout = clone_pull_request_head(
        PullRequestRef(owner="owner", repo="repo", number=7),
        base_dir=tmp_path,
        token="secret",
    )

    assert checkout == tmp_path / "owner" / "repo" / "pr-7"
    assert calls[0][:4] == ["git", "clone", "--depth", "1"]
    assert calls[0][-2] == "https://x-access-token:secret@github.com/owner/repo.git"
    assert calls[1][-2:] == ["origin", "pull/7/head"]
    assert calls[2][-3:] == ["checkout", "--detach", "FETCH_HEAD"]


def test_clone_pull_request_head_reuses_existing_checkout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkout_dir = tmp_path / "owner" / "repo" / "pr-7"
    checkout_dir.mkdir(parents=True)
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        _ = kwargs
        calls.append(args)
        return CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("reviewpilot.fetcher.git_local.run", fake_run)

    clone_pull_request_head(PullRequestRef(owner="owner", repo="repo", number=7), base_dir=tmp_path)

    assert [call[2] for call in calls] == [str(checkout_dir), str(checkout_dir)]
    assert calls[0][3] == "fetch"
    assert calls[1][3] == "checkout"


def test_clone_pull_request_head_redacts_token_in_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(args, **kwargs):
        _ = kwargs
        return CompletedProcess(
            args=args,
            returncode=1,
            stdout="",
            stderr="fatal: https://x-access-token:secret@github.com/owner/repo.git",
        )

    monkeypatch.setattr("reviewpilot.fetcher.git_local.run", fake_run)

    with pytest.raises(GitLocalError) as exc_info:
        clone_pull_request_head(
            PullRequestRef(owner="owner", repo="repo", number=7),
            base_dir=tmp_path,
            token="secret",
        )

    assert "secret" not in str(exc_info.value)
    assert "https://x-access-token:***@github.com/owner/repo.git" in str(exc_info.value)
