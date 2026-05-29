from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Node, Parser
from tree_sitter_language_pack import get_parser

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


_SUFFIX_LANGUAGE = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
}

_DEF_KIND_MAP: dict[str, str] = {
    "function_definition": "function",
    "class_definition": "class",
    "function_declaration": "function",
    "class_declaration": "class",
    "method_definition": "method",
    "interface_declaration": "interface",
    "type_alias_declaration": "type",
    "type_declaration": "type",
}

_CALL_NODE_TYPES = {"call", "call_expression"}

_parser_cache: dict[str, Parser] = {}


def _get_cached_parser(language: str) -> Parser:
    if language not in _parser_cache:
        parser = get_parser(language)
        parser.timeout_ms = 2000
        _parser_cache[language] = parser
    return _parser_cache[language]


def build_symbol_contexts(
    file_contents: dict[str, str],
    hunks: list[DiffHunk],
) -> list[SymbolContext]:
    changed_lines_by_file = _changed_lines_by_file(hunks)
    contexts: list[SymbolContext] = []
    seen: set[tuple[str, str, int]] = set()

    for file_path, changed_lines in changed_lines_by_file.items():
        language = _language_for_file(file_path)
        if language is None:
            continue

        content = file_contents.get(file_path)
        if content is None:
            continue

        definitions = _extract_symbols(content, language)
        for definition in definitions:
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
        language = _language_for_file(file_path)
        if language is None:
            continue
        for definition in _extract_symbols(content, language):
            for callee in definition.callees:
                index.setdefault(callee, set()).add(definition.name)
    return {name: sorted(callers) for name, callers in index.items()}


def _language_for_file(file_path: str) -> str | None:
    suffix = Path(file_path).suffix.lower()
    return _SUFFIX_LANGUAGE.get(suffix)


def _extract_symbols(content: str, language: str) -> list[SymbolDefinition]:
    if language == "python":
        return extract_python_symbols(content)
    return _extract_tree_sitter_symbols(content, language)


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

    return sorted(definitions, key=lambda d: (d.start_line, d.name))


def _extract_tree_sitter_symbols(content: str, language: str) -> list[SymbolDefinition]:
    parser = _get_cached_parser(language)
    tree = parser.parse(content.encode("utf-8"))
    definitions: list[SymbolDefinition] = []

    def walk(node: Node) -> None:
        kind = _DEF_KIND_MAP.get(node.type)
        if kind:
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = name_node.text.decode("utf-8")
                definitions.append(
                    SymbolDefinition(
                        name=name,
                        kind=kind,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        callees=_collect_callees(node),
                    )
                )
        for child in node.children:
            walk(child)

    walk(tree.root_node)
    return sorted(definitions, key=lambda d: (d.start_line, d.name))


def _collect_callees(node: Node) -> list[str]:
    names: set[str] = set()

    def walk(n: Node) -> None:
        if n.type in _CALL_NODE_TYPES:
            func_node = n.child_by_field_name("function")
            if func_node is not None:
                name = _call_name_from_node(func_node)
                if name:
                    names.add(name)
        for child in n.children:
            walk(child)

    walk(node)
    return sorted(names)


def _call_name_from_node(node: Node) -> str | None:
    if node.type == "identifier":
        return node.text.decode("utf-8")
    if node.type in {"attribute", "member_expression"}:
        obj = node.child_by_field_name("object")
        prop = node.child_by_field_name("property") or node.child_by_field_name("attribute")
        owner = _call_name_from_node(obj) if obj else None
        attr = prop.text.decode("utf-8") if prop else None
        if owner and attr:
            return f"{owner}.{attr}"
        return attr
    return None


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
