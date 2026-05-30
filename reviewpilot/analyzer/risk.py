from __future__ import annotations

from dataclasses import dataclass

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from pydantic import ValidationError

from reviewpilot.analyzer.llm import ChatMessage, ChatCompletionClient, LLMRequest
from reviewpilot.analyzer.schemas import ReviewFinding, RiskReport, Severity
from reviewpilot.config import get_settings
from reviewpilot.context.builder import ReviewContext
from reviewpilot.language import ReportLanguage, language_name


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


def render_risk_prompt(context: ReviewContext, report_language: ReportLanguage = "en") -> str:
    template = PROMPT_ENV.get_template("risk.j2")
    return template.render(context=context, report_language=language_name(report_language))


def parse_risk_report(content: str) -> RiskReport:
    try:
        return RiskReport.model_validate_json(content)
    except ValidationError as exc:
        raise RiskOutputError("Risk agent returned invalid JSON schema") from exc


def fallback_risk_analysis(context: ReviewContext) -> RiskAnalysisResult:
    _ = context
    return RiskAnalysisResult(risks=[])


def _apply_self_consistency(
    first: list[ReviewFinding],
    second: list[ReviewFinding],
    third: list[ReviewFinding],
) -> list[ReviewFinding]:
    result: list[ReviewFinding] = []
    for finding in first:
        if finding.severity != Severity.p0:
            result.append(finding)
            continue
        votes = 1
        if any(_findings_match(finding, f) for f in second):
            votes += 1
        if any(_findings_match(finding, f) for f in third):
            votes += 1
        if votes >= 2:
            result.append(finding)
        else:
            result.append(finding.model_copy(update={"confidence": 0.5}))
    return result


def _findings_match(a: ReviewFinding, b: ReviewFinding) -> bool:
    if a.severity != b.severity:
        return False
    return a.title.strip().lower() == b.title.strip().lower()


async def generate_risks(
    context: ReviewContext,
    client: ChatCompletionClient | None = None,
    report_language: ReportLanguage = "en",
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
            ChatMessage(
                role="user",
                content=render_risk_prompt(context, report_language=report_language),
            ),
        ],
        metadata={"agent": "risk", "report_language": report_language},
    )
    response = await client.complete(request)
    report = parse_risk_report(response.content)
    risks = rank_risks(report.risks)
    model = response.model
    cached = response.cached

    p0_findings = [f for f in risks if f.severity == Severity.p0]
    if p0_findings:
        second_response = await client.complete(request)
        third_response = await client.complete(request)
        second_risks = parse_risk_report(second_response.content).risks
        third_risks = parse_risk_report(third_response.content).risks
        risks = _apply_self_consistency(risks, second_risks, third_risks)
        risks = rank_risks(risks)
        cached = cached and second_response.cached and third_response.cached
        model = model or second_response.model or third_response.model

    return RiskAnalysisResult(
        risks=risks,
        model=model,
        cached=cached,
    )
