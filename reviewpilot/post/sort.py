from reviewpilot.analyzer.schemas import ReviewFinding


def sort_findings(findings: list[ReviewFinding]) -> list[ReviewFinding]:
    severity_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    return sorted(
        findings,
        key=lambda finding: (
            severity_order[finding.severity],
            -finding.confidence,
            finding.file_path or "",
            finding.line_number or 0,
        ),
    )
