from __future__ import annotations

from reviewpilot.analyzer.schemas import ReviewFinding


def merge_findings(findings: list[ReviewFinding]) -> list[ReviewFinding]:
    key_order: list[tuple[str, int | None, str]] = []
    merged: dict[tuple[str, int | None, str], ReviewFinding] = {}
    for finding in findings:
        key = (
            finding.file_path or "",
            finding.line_number,
            finding.severity,
        )
        existing = merged.get(key)
        if existing is None:
            key_order.append(key)
            merged[key] = finding
        else:
            if finding.confidence > existing.confidence:
                merged[key] = finding
            elif finding.evidence and finding.evidence not in existing.evidence:
                merged[key] = existing.model_copy(
                    update={"evidence": f"{existing.evidence}; {finding.evidence}"}
                )
    return [merged[k] for k in key_order]
