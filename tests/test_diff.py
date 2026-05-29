from reviewpilot.context.diff import DiffHunk


def test_diff_hunk_stores_header() -> None:
    hunk = DiffHunk(header="@@ -1 +1 @@")
    assert hunk.header == "@@ -1 +1 @@"
