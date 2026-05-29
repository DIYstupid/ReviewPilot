from reviewpilot.analyzer.schemas import ReviewFinding


def with_static_validation_weight(finding: ReviewFinding, validated: bool) -> ReviewFinding:
    if validated:
        return finding.model_copy(update={"confidence": min(1.0, finding.confidence + 0.1)})
    return finding
