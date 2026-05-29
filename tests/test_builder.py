from reviewpilot.context.builder import build_review_context
from reviewpilot.fetcher.github_api import (
    ChangedFile,
    PullRequestMetadata,
    PullRequestRef,
    PullRequestSnapshot,
)


def test_build_review_context_uses_snapshot_metadata_diff_and_file_context() -> None:
    snapshot = PullRequestSnapshot(
        ref=PullRequestRef(owner="owner", repo="repo", number=1),
        metadata=PullRequestMetadata(
            title="Fix parser",
            body="Adds line numbers",
            state="open",
            draft=False,
            html_url="https://github.com/owner/repo/pull/1",
            base_ref="main",
            head_ref="fix-parser",
            author="alice",
            changed_files=1,
            additions=1,
            deletions=1,
        ),
        commits=["abc123"],
        files=[
            ChangedFile(
                filename="app.py",
                status="modified",
                additions=1,
                deletions=1,
                changes=2,
                patch="@@ -1 +1 @@\n-a\n+b\n",
            )
        ],
        diff="""diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-a
+b
""",
    )

    context = build_review_context(
        snapshot,
        file_contents={"app.py": "def changed():\n    return helper()\n"},
        max_chars_per_file=4,
        max_total_file_chars=4,
    )

    assert context.pr_title == "Fix parser"
    assert context.pr_body == "Adds line numbers"
    assert context.commits == ["abc123"]
    assert list(context.changed_files) == ["app.py"]
    assert len(context.diff_files) == 1
    assert len(context.hunks) == 1
    assert context.hunks[0].file_path == "app.py"
    assert context.file_contexts["app.py"].content == "def "
    assert context.file_contexts["app.py"].truncated is True
    assert context.symbols[0].name == "changed"
