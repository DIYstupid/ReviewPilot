from reviewpilot.fetcher.github_api import (
    ChangedFile,
    PullRequestMetadata,
    PullRequestRef,
    PullRequestSnapshot,
    parse_pr_url,
)


def test_parse_pr_url_extracts_reference() -> None:
    ref = parse_pr_url("https://github.com/owner/repo/pull/123")
    assert ref == PullRequestRef(owner="owner", repo="repo", number=123)
    assert ref.slug == "owner/repo#123"


def test_parse_pr_url_allows_trailing_segments() -> None:
    ref = parse_pr_url("https://github.com/owner/repo/pull/123/files")
    assert ref == PullRequestRef(owner="owner", repo="repo", number=123)


def test_parse_pr_url_rejects_non_github_url() -> None:
    try:
        parse_pr_url("https://example.com/owner/repo/pull/123")
    except ValueError as exc:
        assert "github.com" in str(exc)
    else:
        raise AssertionError("Expected non-GitHub URLs to be rejected")


def test_pull_request_snapshot_serializes_to_dict() -> None:
    snapshot = PullRequestSnapshot(
        ref=PullRequestRef(owner="owner", repo="repo", number=123),
        metadata=PullRequestMetadata(
            title="Fix bug",
            body="",
            state="open",
            draft=False,
            html_url="https://github.com/owner/repo/pull/123",
            base_ref="main",
            head_ref="fix-bug",
            author="alice",
            changed_files=1,
            additions=2,
            deletions=1,
        ),
        commits=["abc123"],
        files=[
            ChangedFile(
                filename="reviewpilot/fetcher/github_api.py",
                status="modified",
                additions=2,
                deletions=1,
                changes=3,
                patch="@@ -1 +1 @@",
            )
        ],
        diff="diff --git a/file b/file",
    )

    data = snapshot.to_dict()

    assert data["ref"]["owner"] == "owner"
    assert data["metadata"]["title"] == "Fix bug"
    assert data["files"][0]["filename"] == "reviewpilot/fetcher/github_api.py"
