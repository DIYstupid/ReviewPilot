from dataclasses import dataclass

import pytest

from reviewpilot.analyzer.llm import LLMRequest, LLMResponse
from reviewpilot.analyzer.summary import generate_summary, render_summary_prompt, summarize_context
from reviewpilot.context.builder import build_review_context
from reviewpilot.fetcher.github_api import (
    ChangedFile,
    PullRequestMetadata,
    PullRequestRef,
    PullRequestSnapshot,
)


@dataclass
class FakeClient:
    response: LLMResponse
    request: LLMRequest | None = None

    async def complete(self, request: LLMRequest, use_cache: bool = True) -> LLMResponse:
        self.request = request
        return self.response


def make_context():
    snapshot = PullRequestSnapshot(
        ref=PullRequestRef(owner="owner", repo="repo", number=7),
        metadata=PullRequestMetadata(
            title="Fix parser",
            body="Handle changed line numbers",
            state="open",
            draft=False,
            html_url="https://github.com/owner/repo/pull/7",
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
@@ -1,2 +1,2 @@
 def changed():
-    return 1
+    return helper()
""",
    )
    return build_review_context(
        snapshot,
        file_contents={"app.py": "def changed():\n    return helper()\n"},
    )


def test_summarize_context_includes_title_files_hunks_and_symbols() -> None:
    summary = summarize_context(make_context())

    assert "Fix parser" in summary
    assert "app.py" in summary
    assert "Diff hunks: 1" in summary
    assert "changed" in summary


def test_render_summary_prompt_includes_context_sections() -> None:
    prompt = render_summary_prompt(make_context())

    assert "PR title:" in prompt
    assert "Fix parser" in prompt
    assert "Changed files:" in prompt
    assert "app.py" in prompt
    assert "Changed symbols:" in prompt


@pytest.mark.asyncio
async def test_generate_summary_uses_client_when_provided() -> None:
    client = FakeClient(response=LLMResponse(content="Summary from model", model="deepseek-chat"))

    result = await generate_summary(make_context(), client=client)

    assert result.content == "Summary from model"
    assert result.model == "deepseek-chat"
    assert client.request is not None
    assert client.request.metadata == {"agent": "summary"}
    assert client.request.temperature == 0.3


@pytest.mark.asyncio
async def test_generate_summary_falls_back_without_client() -> None:
    result = await generate_summary(make_context(), client=None)

    assert result.model == "offline"
    assert "Fix parser" in result.content
