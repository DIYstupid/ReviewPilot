from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from reviewpilot.analyzer.schemas import ReviewFinding, Severity


class SemgrepRunnerError(RuntimeError):
    """Raised when semgrep fails before producing usable diagnostics."""


def semgrep_target_args(path: Path) -> list[str]:
    return ["semgrep", "scan", "--json", str(path)]


def parse_semgrep_output(content: str, root: Path | None = None) -> list[ReviewFinding]:
    if not content.strip():
        return []

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise SemgrepRunnerError("Semgrep returned invalid JSON") from exc

    if not isinstance(data, dict):
        raise SemgrepRunnerError("Semgrep JSON output must be an object")

    results = data.get("results")
    if not isinstance(results, list):
        return []

    findings: list[ReviewFinding] = []
    for result in results:
        if isinstance(result, dict):
            findings.append(_result_to_finding(result, root=root))
    return findings


def run_semgrep_on_path(path: Path) -> list[ReviewFinding]:
    result = subprocess.run(
        semgrep_target_args(path),
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode not in {0, 1}:
        message = result.stderr.strip() or result.stdout.strip() or "semgrep scan failed"
        raise SemgrepRunnerError(message)
    return parse_semgrep_output(result.stdout, root=path)


def run_semgrep_on_contents(file_contents: dict[str, str]) -> list[ReviewFinding]:
    if not file_contents:
        return []

    with tempfile.TemporaryDirectory(prefix="reviewpilot-semgrep-") as tmp:
        root = Path(tmp)
        for file_path, content in file_contents.items():
            target = _safe_target_path(root, file_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return run_semgrep_on_path(root)


async def run_semgrep_validator(file_contents: dict[str, str]) -> list[ReviewFinding]:
    return run_semgrep_on_contents(file_contents)


def _result_to_finding(result: dict[str, Any], root: Path | None) -> ReviewFinding:
    check_id = str(result.get("check_id") or "semgrep-rule")
    extra = result.get("extra")
    message = _extra_message(extra) if isinstance(extra, dict) else "Semgrep finding"
    filename = _normalize_filename(result.get("path"), root=root)
    start = result.get("start")
    line_number = start.get("line") if isinstance(start, dict) and isinstance(start.get("line"), int) else None
    semgrep_severity = _extra_severity(extra) if isinstance(extra, dict) else "WARNING"

    return ReviewFinding(
        severity=_severity_for_semgrep(semgrep_severity),
        title=f"Semgrep {check_id}: {message}",
        evidence=_evidence(check_id, message, filename, line_number),
        confidence=0.95,
        recommendation=_recommendation(result),
        file_path=filename,
        line_number=line_number,
        source="semgrep",
    )


def _extra_message(extra: dict[str, Any]) -> str:
    msg = extra.get("message")
    return str(msg) if isinstance(msg, str) and msg else "Semgrep finding"


def _extra_severity(extra: dict[str, Any]) -> str:
    sev = extra.get("severity")
    return str(sev) if isinstance(sev, str) else "WARNING"


def _severity_for_semgrep(severity: str) -> Severity:
    sev = severity.upper()
    if sev in {"ERROR"}:
        return Severity.p1
    if sev in {"WARNING"}:
        return Severity.p2
    return Severity.p3


def _evidence(check_id: str, message: str, filename: str | None, line_number: int | None) -> str:
    location = filename or "unknown file"
    if line_number is not None:
        location = f"{location}:{line_number}"
    return f"{location} - {check_id}: {message}"


def _recommendation(result: dict[str, Any]) -> str:
    extra = result.get("extra")
    if isinstance(extra, dict):
        fix = extra.get("fix")
        if isinstance(fix, str) and fix:
            return fix
    return "Address the semgrep finding before merging."


def _normalize_filename(filename: Any, root: Path | None) -> str | None:
    if not isinstance(filename, str) or not filename:
        return None
    path = Path(filename)
    if root is None:
        return path.as_posix()
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _safe_target_path(root: Path, file_path: str) -> Path:
    candidate = root.joinpath(*_safe_parts(file_path)).resolve()
    resolved_root = root.resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise SemgrepRunnerError(f"Refusing to write outside temp directory: {file_path}")
    return candidate


def _safe_parts(file_path: str) -> list[str]:
    parts = [part for part in Path(file_path).parts if part not in {"", ".", ".."}]
    if parts and Path(parts[0]).anchor:
        parts = parts[1:]
    return parts or ["snippet.txt"]
