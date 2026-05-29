from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Severity(StrEnum):
    p0 = "P0"
    p1 = "P1"
    p2 = "P2"
    p3 = "P3"


FindingSource = Literal["llm", "ruff", "semgrep"]


class ReviewFinding(BaseModel):
    severity: Severity
    title: str
    evidence: str
    confidence: float = Field(ge=0, le=1)
    recommendation: str
    file_path: str | None = None
    line_number: int | None = Field(default=None, ge=1)
    source: FindingSource = "llm"


class RiskReport(BaseModel):
    risks: list[ReviewFinding] = Field(default_factory=list)


class InlineReviewReport(BaseModel):
    inline_reviews: list[ReviewFinding] = Field(default_factory=list)


class ReviewReport(BaseModel):
    summary: str
    risks: list[ReviewFinding] = Field(default_factory=list)
    inline_reviews: list[ReviewFinding] = Field(default_factory=list)
    merge_conclusion: str
