from reviewpilot.markdown import render_markdown


def test_render_markdown_supports_headings_lists_and_inline_styles() -> None:
    html = render_markdown(
        """## Summary

- Handles **renamed** fields
- Keeps `legacy_name` fallback
"""
    )

    assert "<h2>Summary</h2>" in html
    assert "<li>Handles <strong>renamed</strong> fields</li>" in html
    assert "<li>Keeps <code>legacy_name</code> fallback</li>" in html


def test_render_markdown_escapes_html_and_code_blocks() -> None:
    html = render_markdown(
        """<script>alert(1)</script>

```
if x < y:
    return x
```
"""
    )

    assert "<script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "if x &lt; y:" in html
