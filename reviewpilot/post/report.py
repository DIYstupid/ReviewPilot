from __future__ import annotations

from reviewpilot.analyzer.schemas import ReviewFinding, ReviewReport, Severity
from reviewpilot.language import ReportLanguage
from reviewpilot.post.confidence import with_static_validation_weight
from reviewpilot.post.merge import merge_findings
from reviewpilot.post.sort import sort_findings


def build_review_report(
    summary: str,
    risks: list[ReviewFinding],
    inline_reviews: list[ReviewFinding],
    report_language: ReportLanguage = "en",
) -> ReviewReport:
    llm_risks = [f for f in risks if f.source == "llm"]
    static_findings = [f for f in risks if f.source != "llm"]

    weighted_llm_risks = _apply_static_weighting(llm_risks, static_findings)
    all_risks = weighted_llm_risks + static_findings

    sorted_risks = sort_findings(merge_findings(all_risks))
    sorted_inline_reviews = sort_findings(merge_findings(inline_reviews))
    return ReviewReport(
        summary=summary,
        risks=sorted_risks,
        inline_reviews=sorted_inline_reviews,
        merge_conclusion=merge_conclusion(
            sorted_risks + sorted_inline_reviews,
            report_language=report_language,
        ),
    )


def _apply_static_weighting(
    llm_findings: list[ReviewFinding],
    static_findings: list[ReviewFinding],
) -> list[ReviewFinding]:
    result: list[ReviewFinding] = []
    for finding in llm_findings:
        if _has_static_backing(finding, static_findings):
            result.append(with_static_validation_weight(finding, True))
        else:
            lowered = finding.model_copy(update={"confidence": finding.confidence * 0.85})
            result.append(lowered)
    return result


def _has_static_backing(
    finding: ReviewFinding, static_findings: list[ReviewFinding]
) -> bool:
    for static in static_findings:
        if finding.file_path != static.file_path:
            continue
        if finding.line_number is None or static.line_number is None:
            continue
        if abs(finding.line_number - static.line_number) <= 5:
            return True
    return False


def merge_conclusion(
    findings: list[ReviewFinding],
    report_language: ReportLanguage = "en",
) -> str:
    if report_language == "zh":
        if any(finding.severity == Severity.p0 for finding in findings):
            return "在修复 P0 问题前不应合并。"
        if any(finding.severity == Severity.p1 for finding in findings):
            return "不建议合并，直到 P1 缺陷修复完成。"
        if any(finding.severity == Severity.p2 for finding in findings):
            return "可以在复核 P2 可维护性问题后合并。"
        if any(finding.severity == Severity.p3 for finding in findings):
            return "可以合并；剩余问题为轻微项。"
        return "可以合并；未发现需要处理的问题。"

    if any(finding.severity == Severity.p0 for finding in findings):
        return "Do not merge until P0 findings are resolved."
    if any(finding.severity == Severity.p1 for finding in findings):
        return "Merge is not recommended until P1 bugs are fixed."
    if any(finding.severity == Severity.p2 for finding in findings):
        return "Merge can proceed after reviewing P2 maintainability concerns."
    if any(finding.severity == Severity.p3 for finding in findings):
        return "Merge can proceed; remaining findings are minor."
    return "Merge can proceed; no actionable findings were detected."
