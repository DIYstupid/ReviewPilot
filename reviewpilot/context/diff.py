from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum


class DiffLineKind(StrEnum):
    context = "context"
    addition = "addition"
    deletion = "deletion"
    metadata = "metadata"


@dataclass(frozen=True)
class DiffLine:
    kind: DiffLineKind
    text: str
    raw: str
    old_line: int | None = None
    new_line: int | None = None


@dataclass(frozen=True)
class DiffHunk:
    header: str
    file_path: str = ""
    old_start: int | None = None
    old_count: int | None = None
    new_start: int | None = None
    new_count: int | None = None
    section_header: str = ""
    lines: list[DiffLine] = field(default_factory=list)


@dataclass(frozen=True)
class DiffFile:
    old_path: str
    new_path: str
    hunks: list[DiffHunk] = field(default_factory=list)

    @property
    def path(self) -> str:
        return self.new_path if self.new_path != "/dev/null" else self.old_path


_HUNK_RE = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? "
    r"\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@"
    r"(?: (?P<section>.*))?$"
)


def parse_unified_diff(diff_text: str) -> list[DiffFile]:
    files: list[DiffFile] = []
    current_file: DiffFile | None = None
    current_hunk: DiffHunk | None = None
    old_line: int | None = None
    new_line: int | None = None

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("diff --git "):
            if current_file is not None:
                files.append(current_file)
            current_file = _parse_diff_file_header(raw_line)
            current_hunk = None
            old_line = None
            new_line = None
            continue

        if current_file is None:
            continue

        if raw_line.startswith("--- "):
            current_file = DiffFile(
                old_path=_normalize_diff_path(raw_line[4:]),
                new_path=current_file.new_path,
                hunks=current_file.hunks,
            )
            continue

        if raw_line.startswith("+++ "):
            current_file = DiffFile(
                old_path=current_file.old_path,
                new_path=_normalize_diff_path(raw_line[4:]),
                hunks=current_file.hunks,
            )
            continue

        if raw_line.startswith("@@ "):
            hunk = _parse_hunk_header(raw_line, current_file.path)
            current_file.hunks.append(hunk)
            current_hunk = hunk
            old_line = hunk.old_start
            new_line = hunk.new_start
            continue

        if current_hunk is None:
            continue

        line = _parse_hunk_line(raw_line, old_line, new_line)
        current_hunk.lines.append(line)
        if line.kind == DiffLineKind.context:
            old_line = None if old_line is None else old_line + 1
            new_line = None if new_line is None else new_line + 1
        elif line.kind == DiffLineKind.deletion:
            old_line = None if old_line is None else old_line + 1
        elif line.kind == DiffLineKind.addition:
            new_line = None if new_line is None else new_line + 1

    if current_file is not None:
        files.append(current_file)

    return files


def flatten_hunks(files: list[DiffFile]) -> list[DiffHunk]:
    return [hunk for diff_file in files for hunk in diff_file.hunks]


def _parse_diff_file_header(raw_line: str) -> DiffFile:
    parts = raw_line.split()
    old_path = _normalize_diff_path(parts[2]) if len(parts) > 2 else ""
    new_path = _normalize_diff_path(parts[3]) if len(parts) > 3 else old_path
    return DiffFile(old_path=old_path, new_path=new_path)


def _parse_hunk_header(raw_line: str, file_path: str) -> DiffHunk:
    match = _HUNK_RE.match(raw_line)
    if match is None:
        return DiffHunk(header=raw_line, file_path=file_path)

    return DiffHunk(
        header=raw_line,
        file_path=file_path,
        old_start=int(match.group("old_start")),
        old_count=int(match.group("old_count") or 1),
        new_start=int(match.group("new_start")),
        new_count=int(match.group("new_count") or 1),
        section_header=match.group("section") or "",
    )


def _parse_hunk_line(raw_line: str, old_line: int | None, new_line: int | None) -> DiffLine:
    marker = raw_line[:1]
    text = raw_line[1:] if marker in {" ", "+", "-", "\\"} else raw_line
    if marker == " ":
        return DiffLine(
            kind=DiffLineKind.context,
            text=text,
            raw=raw_line,
            old_line=old_line,
            new_line=new_line,
        )
    if marker == "+":
        return DiffLine(kind=DiffLineKind.addition, text=text, raw=raw_line, new_line=new_line)
    if marker == "-":
        return DiffLine(kind=DiffLineKind.deletion, text=text, raw=raw_line, old_line=old_line)
    return DiffLine(kind=DiffLineKind.metadata, text=text, raw=raw_line)


def _normalize_diff_path(path: str) -> str:
    path = path.strip()
    if path == "/dev/null":
        return path
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path
