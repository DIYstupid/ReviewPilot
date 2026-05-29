from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FileContext:
    path: str
    content: str
    original_chars: int
    included_chars: int
    truncated: bool


def trim_text(text: str, max_chars: int) -> str:
    if max_chars < 0:
        raise ValueError("max_chars must be non-negative")
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def build_file_context(path: str, content: str, max_chars: int) -> FileContext:
    trimmed = trim_text(content, max_chars)
    return FileContext(
        path=path,
        content=trimmed,
        original_chars=len(content),
        included_chars=len(trimmed),
        truncated=len(trimmed) < len(content),
    )


def build_file_contexts(
    contents: dict[str, str],
    max_chars_per_file: int,
    max_total_chars: int,
) -> dict[str, FileContext]:
    if max_chars_per_file < 0:
        raise ValueError("max_chars_per_file must be non-negative")
    if max_total_chars < 0:
        raise ValueError("max_total_chars must be non-negative")

    remaining = max_total_chars
    contexts: dict[str, FileContext] = {}
    for path in sorted(contents):
        allowed = min(max_chars_per_file, remaining)
        context = build_file_context(path, contents[path], allowed)
        contexts[path] = context
        remaining -= context.included_chars
        if remaining <= 0:
            remaining = 0

    return contexts
