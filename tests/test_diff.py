from reviewpilot.context.diff import (
    DiffHunk,
    DiffLineKind,
    flatten_hunks,
    parse_unified_diff,
    serialize_diff_files,
)


def test_diff_hunk_stores_header() -> None:
    hunk = DiffHunk(header="@@ -1 +1 @@")
    assert hunk.header == "@@ -1 +1 @@"


def test_parse_unified_diff_extracts_files_hunks_and_line_numbers() -> None:
    diff_text = """diff --git a/app.py b/app.py
index 1111111..2222222 100644
--- a/app.py
+++ b/app.py
@@ -1,3 +1,4 @@ def main():
 import os
-print("old")
+print("new")
+print("extra")
 return None
"""

    files = parse_unified_diff(diff_text)

    assert len(files) == 1
    assert files[0].path == "app.py"
    assert len(files[0].hunks) == 1

    hunk = files[0].hunks[0]
    assert hunk.file_path == "app.py"
    assert hunk.old_start == 1
    assert hunk.old_count == 3
    assert hunk.new_start == 1
    assert hunk.new_count == 4
    assert hunk.section_header == "def main():"

    assert hunk.lines[0].kind == DiffLineKind.context
    assert hunk.lines[0].old_line == 1
    assert hunk.lines[0].new_line == 1
    assert hunk.lines[1].kind == DiffLineKind.deletion
    assert hunk.lines[1].old_line == 2
    assert hunk.lines[1].new_line is None
    assert hunk.lines[2].kind == DiffLineKind.addition
    assert hunk.lines[2].old_line is None
    assert hunk.lines[2].new_line == 2
    assert hunk.lines[3].new_line == 3
    assert hunk.lines[4].old_line == 3
    assert hunk.lines[4].new_line == 4


def test_flatten_hunks_preserves_file_hunks() -> None:
    diff_text = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1 +1 @@
-a
+b
diff --git a/b.py b/b.py
--- a/b.py
+++ b/b.py
@@ -1 +1 @@
-c
+d
"""

    hunks = flatten_hunks(parse_unified_diff(diff_text))

    assert [hunk.file_path for hunk in hunks] == ["a.py", "b.py"]


def test_serialize_diff_files_keeps_line_numbers() -> None:
    diff_text = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,2 +1,2 @@
 def changed():
-    return 1
+    return 2
"""

    serialized = serialize_diff_files(parse_unified_diff(diff_text))

    assert serialized[0]["path"] == "app.py"
    assert serialized[0]["hunks"][0]["lines"][1]["kind"] == "deletion"
    assert serialized[0]["hunks"][0]["lines"][2]["new_line"] == 2
