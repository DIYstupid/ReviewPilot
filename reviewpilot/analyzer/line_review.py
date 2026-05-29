from __future__ import annotations

import asyncio
from dataclasses import dataclass

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from pydantic import ValidationError

from reviewpilot.analyzer.llm import ChatMessage, ChatCompletionClient, LLMRequest
from reviewpilot.analyzer.schemas import InlineReviewReport, ReviewFinding
from reviewpilot.config import get_settings
from reviewpilot.context.builder import ReviewContext
from reviewpilot.context.diff import DiffHunk


def collect_inline_reviews(findings: list[ReviewFinding]) -> list[ReviewFinding]:
    return sorted(
        findings,
        key=lambda finding: (finding.file_path or "", finding.line_number or 0, finding.severity),
    )


PROMPT_ENV = Environment(
    loader=FileSystemLoader("reviewpilot/analyzer/prompts"),
    undefined=StrictUndefined,
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
)


@dataclass(frozen=True)
class LineReviewResult:
    inline_reviews: list[ReviewFinding]
    model: str = "offline"
    cached: bool = False


class LineReviewOutputError(ValueError):
    """Raised when the line review agent returns invalid structured output."""


def render_line_review_prompt(context: ReviewContext, hunk: DiffHunk) -> str:
    template = PROMPT_ENV.get_template("line_review.j2")
    nearby_symbols = [
        symbol
        for symbol in context.symbols
        if symbol.file_path == hunk.file_path
        and symbol.start_line is not None
        and symbol.end_line is not None
        and hunk.new_start is not None
        and symbol.start_line <= hunk.new_start <= symbol.end_line
    ]
    return template.render(context=context, hunk=hunk, symbols=nearby_symbols)


def parse_inline_review_report(content: str) -> InlineReviewReport:
    try:
        return InlineReviewReport.model_validate_json(content)
    except ValidationError as exc:
        raise LineReviewOutputError("Line review agent returned invalid JSON schema") from exc


async def generate_inline_reviews(
    context: ReviewContext,
    client: ChatCompletionClient | None = None,
    max_hunks: int = 20,
    concurrency: int = 4,
) -> LineReviewResult:
    if client is None:
        return LineReviewResult(inline_reviews=[])

    settings = get_settings()
    hunks = context.hunks[:max_hunks]
    sem = asyncio.Semaphore(concurrency)

    async def review_one(hunk: DiffHunk) -> tuple[list[ReviewFinding], str, bool]:
        async with sem:
            request = LLMRequest(
                model=settings.deepseek_model,
                temperature=0.2,
                response_format={"type": "json_object"},
                messages=[
                    ChatMessage(role="system", content="You are ReviewPilot's line review agent."),
                    ChatMessage(role="user", content=render_line_review_prompt(context, hunk)),
                ],
                metadata={"agent": "line_review", "file_path": hunk.file_path, "hunk": hunk.header},
            )
            try:
                response = await client.complete(request)
                report = parse_inline_review_report(response.content)
                return report.inline_reviews, response.model, response.cached
            except LineReviewOutputError:
                return [], settings.deepseek_model, False

    results = await asyncio.gather(*[review_one(h) for h in hunks])

    findings: list[ReviewFinding] = []
    cached = False
    model = settings.deepseek_model
    for inline_reviews, resp_model, resp_cached in results:
        findings.extend(inline_reviews)
        cached = cached or resp_cached
        if resp_model and resp_model != settings.deepseek_model:
            model = resp_model

    return LineReviewResult(
        inline_reviews=collect_inline_reviews(findings),
        model=model,
        cached=cached,
    )
