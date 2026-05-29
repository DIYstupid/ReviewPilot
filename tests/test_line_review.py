from dataclasses import dataclass

import pytest

from reviewpilot.analyzer.line_review import (
    LineReviewOutputError,
    collect_inline_reviews,
    generate_inline_reviews,
    parse_inline_review_report,
    render_line_review_prompt,
)
from reviewpilot.analyzer.llm import LLMRequest, LLMResponse
from reviewpilot.analyzer.schemas import ReviewFinding, Severity
from reviewpilot.context.builder import build_review_context
from reviewpilot.fetcher.github_api import PullRequestMetadata, PullRequestRef, PullRequestSnapshot


@dataclass
class FakeClient:
    responses: list[LLMResponse]
    requests: list[LLMRequest] | None = None

    async def complete(self, request: LLMRequest, use_cache: bool = True) -> LLMResponse:
        if self.requests is None:
            self.requests = []
        self.requests.append(request)
        return self.responses.pop(0)


def make_context():
    snapshot = PullRequestSnapshot(
        ref=PullRequestRef(owner="owner", repo="repo", number=10),
        metadata=PullRequestMetadata(
            title="Add user lookup",
            body="",
            state="open",
            draft=False,
            html_url="https://github.com/owner/repo/pull/10",
            base_ref="main",
            head_ref="lookup",
            author="alice",
            changed_files=1,
            additions=1,
            deletions=0,
        ),
        diff="""diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,2 +1,2 @@
 def lookup(name):
-    return None
+    return db.execute("select * from users where name = " + name)
""",
    )
    return build_review_context(
        snapshot,
        file_contents={
            "app.py": 'def lookup(name):\n    return db.execute("select * from users where name = " + name)\n'
        },
    )


def test_collect_inline_reviews_sorts_by_file_and_line() -> None:
    findings = [
        ReviewFinding(
            severity=Severity.p2,
            title="later",
            evidence="line",
            confidence=0.8,
            recommendation="fix",
            file_path="b.py",
            line_number=5,
        ),
        ReviewFinding(
            severity=Severity.p1,
            title="earlier",
            evidence="line",
            confidence=0.8,
            recommendation="fix",
            file_path="a.py",
            line_number=2,
        ),
    ]

    assert [finding.title for finding in collect_inline_reviews(findings)] == ["earlier", "later"]


def test_parse_inline_review_report_validates_json() -> None:
    report = parse_inline_review_report(
        """{"inline_reviews":[{"severity":"P1","title":"Bug","evidence":"line","confidence":0.8,"recommendation":"Fix","file_path":"app.py","line_number":2}]}"""
    )

    assert report.inline_reviews[0].severity == Severity.p1


def test_parse_inline_review_report_rejects_invalid_schema() -> None:
    with pytest.raises(LineReviewOutputError):
        parse_inline_review_report("""{"inline_reviews":[{"severity":"P9"}]}""")


def test_render_line_review_prompt_includes_hunk_and_nearby_symbols() -> None:
    context = make_context()
    prompt = render_line_review_prompt(context, context.hunks[0])

    assert "Add user lookup" in prompt
    assert "db.execute" in prompt
    assert "lookup" in prompt


@pytest.mark.asyncio
async def test_generate_inline_reviews_calls_client_per_hunk() -> None:
    client = FakeClient(
        responses=[
            LLMResponse(
                content="""{"inline_reviews":[{"severity":"P1","title":"Raw SQL","evidence":"db.execute concatenates input","confidence":0.8,"recommendation":"Use parameters","file_path":"app.py","line_number":2}]}""",
                model="deepseek-chat",
            )
        ]
    )

    result = await generate_inline_reviews(make_context(), client=client)

    assert result.model == "deepseek-chat"
    assert result.inline_reviews[0].title == "Raw SQL"
    assert client.requests is not None
    assert len(client.requests) == 1
    assert client.requests[0].response_format == {"type": "json_object"}
    assert client.requests[0].temperature == 0.2


@pytest.mark.asyncio
async def test_generate_inline_reviews_falls_back_empty_without_client() -> None:
    result = await generate_inline_reviews(make_context(), client=None)

    assert result.model == "offline"
    assert result.inline_reviews == []
