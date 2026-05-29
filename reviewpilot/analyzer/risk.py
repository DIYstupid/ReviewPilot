from reviewpilot.analyzer.schemas import ReviewFinding


def rank_risks(findings: list[ReviewFinding]) -> list[ReviewFinding]:
    return sorted(findings, key=lambda finding: finding.severity)
