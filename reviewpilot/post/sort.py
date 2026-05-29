from reviewpilot.analyzer.schemas import ReviewFinding


def sort_findings(findings: list[ReviewFinding]) -> list[ReviewFinding]:
    return sorted(findings, key=lambda finding: (finding.severity, -finding.confidence))
