from __future__ import annotations

from dataclasses import dataclass

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from pydantic import ValidationError

from reviewpilot.analyzer.llm import ChatMessage, ChatCompletionClient, LLMRequest
from reviewpilot.analyzer.schemas import ReviewFinding, RiskReport
from reviewpilot.config import get_settings
from reviewpilot.context.builder import ReviewContext


PROMPT_ENV = Environment(
    loader=FileSystemLoader("reviewpilot/analyzer/prompts"),
    undefined=StrictUndefined,
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
)


@dataclass(frozen=True)
class RiskAnalysisResult:
    risks: list[ReviewFinding]
    model: str = "offline"
    cached: bool = False


class RiskOutputError(ValueError):
    """Raised when the risk agent returns invalid structured output."""


def rank_risks(findings: list[ReviewFinding]) -> list[ReviewFinding]:
    severity_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    return sorted(findings, key=lambda finding: (severity_order[finding.severity], -finding.confidence))


def render_risk_prompt(context: ReviewContext) -> str:
    template = PROMPT_ENV.get_template("risk.j2")
    return template.render(context=context)


def parse_risk_report(content: str) -> RiskReport:
    try:
        return RiskReport.model_validate_json(content)
    except ValidationError as exc:
        raise RiskOutputError("Risk agent returned invalid JSON schema") from exc


def fallback_risk_analysis(context: ReviewContext) -> RiskAnalysisResult:
    _ = context
    return RiskAnalysisResult(risks=[])


async def generate_risks(
    context: ReviewContext,
    client: ChatCompletionClient | None = None,
) -> RiskAnalysisResult:
    if client is None:
        return fallback_risk_analysis(context)

    settings = get_settings()
    request = LLMRequest(
        model=settings.deepseek_model,
        temperature=0.1,
        response_format={"type": "json_object"},
        messages=[
            ChatMessage(role="system", content="You are ReviewPilot's risk agent."),
            ChatMessage(role="user", content=render_risk_prompt(context)),
        ],
        metadata={"agent": "risk"},
    )
    response = await client.complete(request)
    report = parse_risk_report(response.content)
    return RiskAnalysisResult(
        risks=rank_risks(report.risks),
        model=response.model,
        cached=response.cached,
    )
