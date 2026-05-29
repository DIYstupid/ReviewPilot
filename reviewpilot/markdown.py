from __future__ import annotations

import html
import re


def render_markdown(markdown: str | None) -> str:
    text = markdown or ""
    lines = text.splitlines()
    parts: list[str] = []
    paragraph: list[str] = []
    list_mode: str | None = None
    code_lines: list[str] = []
    in_code = False

    def flush_paragraph() -> None:
        if paragraph:
            parts.append(f"<p>{_render_inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def close_list() -> None:
        nonlocal list_mode
        if list_mode:
            parts.append(f"</{list_mode}>")
            list_mode = None

    for line in lines:
        stripped = line.strip()
        if in_code:
            if stripped.startswith("```"):
                parts.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
                code_lines.clear()
                in_code = False
            else:
                code_lines.append(line)
            continue

        if stripped.startswith("```"):
            flush_paragraph()
            close_list()
            in_code = True
            continue

        if not stripped:
            flush_paragraph()
            close_list()
            continue

        heading = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            parts.append(f"<h{level}>{_render_inline(heading.group(2))}</h{level}>")
            continue

        unordered = re.match(r"^[-*]\s+(.+)$", stripped)
        if unordered:
            flush_paragraph()
            if list_mode != "ul":
                close_list()
                parts.append("<ul>")
                list_mode = "ul"
            parts.append(f"<li>{_render_inline(unordered.group(1))}</li>")
            continue

        ordered = re.match(r"^\d+\.\s+(.+)$", stripped)
        if ordered:
            flush_paragraph()
            if list_mode != "ol":
                close_list()
                parts.append("<ol>")
                list_mode = "ol"
            parts.append(f"<li>{_render_inline(ordered.group(1))}</li>")
            continue

        paragraph.append(stripped)

    if in_code:
        parts.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
    flush_paragraph()
    close_list()
    return "\n".join(parts)


def _render_inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", escaped)
    return escaped
