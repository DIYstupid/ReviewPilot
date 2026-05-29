from __future__ import annotations

import ast
from dataclasses import dataclass, field

from reviewpilot.context.diff import DiffHunk, DiffLineKind


@dataclass(frozen=True)
class SymbolContext:
    name: str
    file_path: str = ""
    kind: str = ""
    start_line: int | None = None
    end_line: int | None = None
    callers: list[str] = field(default_factory=list)
    callees: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SymbolDefinition:
    name: str
    kind: str
    start_line: int
    end_line: int
    callees: list[str] = field(default_factory=list)


def build_symbol_contexts(
    file_contents: dict[str, str],
    hunks: list[DiffHunk],
) -> list[SymbolContext]:
    changed_lines_by_file = _changed_lines_by_file(hunks)
    contexts: list[SymbolContext] = []
    seen: set[tuple[str, str, int]] = set()

    for file_path, changed_lines in changed_lines_by_file.items():
        if not file_path.endswith(".py"):
            continue

        content = file_contents.get(file_path)
        if content is None:
            continue

        for definition in extract_python_symbols(content):
            if not any(definition.start_line <= line <= definition.end_line for line in changed_lines):
                continue

            key = (file_path, definition.name, definition.start_line)
            if key in seen:
                continue
            seen.add(key)
            contexts.append(
                SymbolContext(
                    name=definition.name,
                    file_path=file_path,
                    kind=definition.kind,
                    start_line=definition.start_line,
                    end_line=definition.end_line,
                    callees=definition.callees,
                )
            )

    callers_by_name = _build_caller_index(file_contents)
    result: list[SymbolContext] = []
    for ctx in contexts:
        result.append(
            SymbolContext(
                name=ctx.name,
                file_path=ctx.file_path,
                kind=ctx.kind,
                start_line=ctx.start_line,
                end_line=ctx.end_line,
                callees=ctx.callees,
                callers=callers_by_name.get(ctx.name, []),
            )
        )
    return result


def _build_caller_index(file_contents: dict[str, str]) -> dict[str, list[str]]:
    index: dict[str, set[str]] = {}
    for file_path, content in file_contents.items():
        if not file_path.endswith(".py"):
            continue
        for definition in extract_python_symbols(content):
            for callee in definition.callees:
                index.setdefault(callee, set()).add(definition.name)
    return {name: sorted(callers) for name, callers in index.items()}


def extract_python_symbols(content: str) -> list[SymbolDefinition]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []

    definitions: list[SymbolDefinition] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            definitions.append(
                SymbolDefinition(
                    name=node.name,
                    kind="class",
                    start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno),
                    callees=_call_names(node),
                )
            )
        elif isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            definitions.append(
                SymbolDefinition(
                    name=node.name,
                    kind="function",
                    start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno),
                    callees=_call_names(node),
                )
            )

    return sorted(definitions, key=lambda definition: (definition.start_line, definition.name))


def _changed_lines_by_file(hunks: list[DiffHunk]) -> dict[str, set[int]]:
    changed: dict[str, set[int]] = {}
    for hunk in hunks:
        if not hunk.file_path:
            continue
        lines = changed.setdefault(hunk.file_path, set())
        for line in hunk.lines:
            if line.kind == DiffLineKind.addition and line.new_line is not None:
                lines.add(line.new_line)
            elif line.kind == DiffLineKind.deletion and line.old_line is not None:
                lines.add(line.old_line)
    return changed


def _call_names(node: ast.AST) -> list[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        name = _call_name(child.func)
        if name:
            names.add(name)
    return sorted(names)


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        owner = _call_name(node.value)
        return f"{owner}.{node.attr}" if owner else node.attr
    return None
