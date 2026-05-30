from __future__ import annotations

from typing import Literal


ReportLanguage = Literal["en", "zh"]

LANGUAGE_LABELS: dict[ReportLanguage, str] = {
    "en": "English",
    "zh": "中文",
}


def normalize_report_language(value: str | None) -> ReportLanguage:
    language = (value or "en").strip().lower()
    if language in {"zh", "zh-cn", "cn", "chinese", "中文"}:
        return "zh"
    return "en"


def language_name(language: ReportLanguage) -> str:
    return LANGUAGE_LABELS.get(language, LANGUAGE_LABELS["en"])
