from reviewpilot.analyzer.schemas import ReviewFinding, Severity
from reviewpilot.post.confidence import with_static_validation_weight
from reviewpilot.post.merge import merge_findings
from reviewpilot.post.report import build_review_report, merge_conclusion
from reviewpilot.post.sort import sort_findings


def finding(
    severity: Severity,
    title: str,
    confidence: float,
    file_path: str = "app.py",
    line_number: int | None = 1,
) -> ReviewFinding:
    return ReviewFinding(
        severity=severity,
        title=title,
        evidence="evidence",
        confidence=confidence,
        recommendation="fix",
        file_path=file_path,
        line_number=line_number,
    )


def test_merge_findings_keeps_highest_confidence_duplicate() -> None:
    merged = merge_findings(
        [
            finding(Severity.p1, "Bug", 0.4),
            finding(Severity.p1, "Bug", 0.9),
        ]
    )

    assert len(merged) == 1
    assert merged[0].confidence == 0.9


def test_sort_findings_orders_by_severity_confidence_and_location() -> None:
    sorted_findings = sort_findings(
        [
            finding(Severity.p2, "later", 0.9, "b.py", 3),
            finding(Severity.p1, "first", 0.2, "a.py", 2),
            finding(Severity.p1, "high", 0.8, "a.py", 1),
        ]
    )

    assert [item.title for item in sorted_findings] == ["high", "first", "later"]


def test_with_static_validation_weight_returns_updated_copy() -> None:
    original = finding(Severity.p2, "Lint", 0.95)

    updated = with_static_validation_weight(original, validated=True)

    assert original.confidence == 0.95
    assert updated.confidence == 1.0


def test_merge_conclusion_reflects_highest_severity() -> None:
    assert "Do not merge" in merge_conclusion([finding(Severity.p0, "Security", 0.9)])
    assert "not recommended" in merge_conclusion([finding(Severity.p1, "Bug", 0.9)])
    assert "can proceed" in merge_conclusion([])


def test_build_review_report_merges_sorts_and_concludes() -> None:
    report = build_review_report(
        summary="Summary",
        risks=[finding(Severity.p1, "Bug", 0.5), finding(Severity.p1, "Bug", 0.8)],
        inline_reviews=[finding(Severity.p2, "Style", 0.6)],
    )

    assert report.summary == "Summary"
    assert len(report.risks) == 1
    assert report.risks[0].confidence == 0.8
    assert report.inline_reviews[0].title == "Style"
    assert "not recommended" in report.merge_conclusion
