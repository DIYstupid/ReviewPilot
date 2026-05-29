from enum import StrEnum

from pydantic import BaseModel, Field


class Severity(StrEnum):
    p0 = "P0"
    p1 = "P1"
    p2 = "P2"
    p3 = "P3"


class ReviewFinding(BaseModel):
    severity: Severity
    title: str
    evidence: str
    confidence: float = Field(ge=0, le=1)
    recommendation: str


class ReviewReport(BaseModel):
    summary: str
    risks: list[ReviewFinding] = Field(default_factory=list)
    inline_reviews: list[ReviewFinding] = Field(default_factory=list)
    merge_conclusion: str
