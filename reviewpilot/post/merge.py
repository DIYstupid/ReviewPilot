from __future__ import annotations

from reviewpilot.analyzer.schemas import ReviewFinding


def merge_findings(findings: list[ReviewFinding]) -> list[ReviewFinding]:
    merged: dict[tuple[str, int | None, str, str], ReviewFinding] = {}
    for finding in findings:
        key = (
            finding.file_path or "",
            finding.line_number,
            finding.severity,
            finding.title.strip().lower(),
        )
        existing = merged.get(key)
        if existing is None or finding.confidence > existing.confidence:
            merged[key] = finding
    return list(merged.values())
