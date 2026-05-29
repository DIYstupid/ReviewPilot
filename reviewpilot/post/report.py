from reviewpilot.analyzer.schemas import ReviewFinding, ReviewReport, Severity
from reviewpilot.post.merge import merge_findings
from reviewpilot.post.sort import sort_findings


def build_review_report(
    summary: str,
    risks: list[ReviewFinding],
    inline_reviews: list[ReviewFinding],
) -> ReviewReport:
    sorted_risks = sort_findings(merge_findings(risks))
    sorted_inline_reviews = sort_findings(merge_findings(inline_reviews))
    return ReviewReport(
        summary=summary,
        risks=sorted_risks,
        inline_reviews=sorted_inline_reviews,
        merge_conclusion=merge_conclusion(sorted_risks + sorted_inline_reviews),
    )


def merge_conclusion(findings: list[ReviewFinding]) -> str:
    if any(finding.severity == Severity.p0 for finding in findings):
        return "Do not merge until P0 findings are resolved."
    if any(finding.severity == Severity.p1 for finding in findings):
        return "Merge is not recommended until P1 bugs are fixed."
    if any(finding.severity == Severity.p2 for finding in findings):
        return "Merge can proceed after reviewing P2 maintainability concerns."
    if any(finding.severity == Severity.p3 for finding in findings):
        return "Merge can proceed; remaining findings are minor."
    return "Merge can proceed; no actionable findings were detected."
