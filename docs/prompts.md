# Prompts

Prompt changes live in `reviewpilot/analyzer/prompts/*.j2`.

Record every material prompt change here with the reason, expected behavior change, and fixture or snapshot that covers it.

## Summary Markdown Structure

- Reason: summary output was hard to scan when rendered as one plain paragraph.
- Change: `summary.j2` now asks for concise Markdown with `Intent`, `Changed Areas`, and `Review Focus` sections.
- Expected behavior: the result page can render Summary as headings and bullets instead of dense prose.
- Coverage: `tests/test_markdown.py` covers Markdown rendering, and `tests/test_review_api.py` verifies server-rendered Summary HTML.
