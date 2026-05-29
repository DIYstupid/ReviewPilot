from dataclasses import dataclass

import pytest

from reviewpilot.analyzer.llm import LLMRequest, LLMResponse
from reviewpilot.analyzer.risk import (
    RiskOutputError,
    generate_risks,
    parse_risk_report,
    rank_risks,
    render_risk_prompt,
)
from reviewpilot.analyzer.schemas import ReviewFinding, Severity
from reviewpilot.context.builder import build_review_context
from reviewpilot.fetcher.github_api import PullRequestMetadata, PullRequestRef, PullRequestSnapshot


@dataclass
class FakeClient:
    response: LLMResponse
    request: LLMRequest | None = None

    async def complete(self, request: LLMRequest, use_cache: bool = True) -> LLMResponse:
        self.request = request
        return self.response


def make_context():
    snapshot = PullRequestSnapshot(
        ref=PullRequestRef(owner="owner", repo="repo", number=9),
        metadata=PullRequestMetadata(
            title="Add SQL lookup",
            body="Adds raw lookup endpoint",
            state="open",
            draft=False,
            html_url="https://github.com/owner/repo/pull/9",
            base_ref="main",
            head_ref="sql-lookup",
            author="alice",
            changed_files=1,
            additions=1,
            deletions=0,
        ),
        diff="""diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1 +1,2 @@
 def lookup(name):
+    return db.execute("select * from users where name = " + name)
""",
    )
    return build_review_context(
        snapshot,
        file_contents={
            "app.py": 'def lookup(name):\n    return db.execute("select * from users where name = " + name)\n'
        },
    )


def test_rank_risks_sorts_by_severity_then_confidence() -> None:
    findings = [
        ReviewFinding(
            severity=Severity.p2,
            title="minor",
            evidence="line",
            confidence=0.9,
            recommendation="fix",
        ),
        ReviewFinding(
            severity=Severity.p0,
            title="major",
            evidence="line",
            confidence=0.4,
            recommendation="fix",
        ),
        ReviewFinding(
            severity=Severity.p0,
            title="major high",
            evidence="line",
            confidence=0.8,
            recommendation="fix",
        ),
    ]

    assert [finding.title for finding in rank_risks(findings)] == ["major high", "major", "minor"]


def test_parse_risk_report_validates_json() -> None:
    report = parse_risk_report(
        """{"risks":[{"severity":"P1","title":"Bug","evidence":"diff","confidence":0.7,"recommendation":"Fix it","file_path":"app.py","line_number":2}]}"""
    )

    assert report.risks[0].severity == Severity.p1
    assert report.risks[0].file_path == "app.py"
    assert report.risks[0].line_number == 2


def test_parse_risk_report_rejects_invalid_schema() -> None:
    with pytest.raises(RiskOutputError):
        parse_risk_report("""{"risks":[{"severity":"P9"}]}""")


def test_render_risk_prompt_includes_diff_and_symbols() -> None:
    prompt = render_risk_prompt(make_context())

    assert "Add SQL lookup" in prompt
    assert "db.execute" in prompt
    assert "Symbol context:" in prompt


@pytest.mark.asyncio
async def test_generate_risks_uses_json_object_response_format() -> None:
    client = FakeClient(
        response=LLMResponse(
            content="""{"risks":[{"severity":"P0","title":"SQL injection","evidence":"db.execute concatenates name","confidence":0.9,"recommendation":"Use parameters","file_path":"app.py","line_number":2}]}""",
            model="deepseek-chat",
        )
    )

    result = await generate_risks(make_context(), client=client)

    assert result.model == "deepseek-chat"
    assert result.risks[0].title == "SQL injection"
    assert client.request is not None
    assert client.request.response_format == {"type": "json_object"}
    assert client.request.temperature == 0.1


@pytest.mark.asyncio
async def test_generate_risks_falls_back_to_empty_without_client() -> None:
    result = await generate_risks(make_context(), client=None)

    assert result.model == "offline"
    assert result.risks == []
