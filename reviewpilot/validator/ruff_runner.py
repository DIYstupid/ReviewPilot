from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from reviewpilot.analyzer.schemas import ReviewFinding, Severity


PYTHON_SUFFIXES = {".py", ".pyi"}


class RuffRunnerError(RuntimeError):
    """Raised when ruff fails before producing usable diagnostics."""


def ruff_target_args(path: Path) -> list[str]:
    return [sys.executable, "-m", "ruff", "check", "--output-format", "json", str(path)]


def parse_ruff_output(content: str, root: Path | None = None) -> list[ReviewFinding]:
    if not content.strip():
        return []

    try:
        diagnostics = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuffRunnerError("Ruff returned invalid JSON") from exc

    if not isinstance(diagnostics, list):
        raise RuffRunnerError("Ruff JSON output must be a list")

    findings: list[ReviewFinding] = []
    for diagnostic in diagnostics:
        if isinstance(diagnostic, dict):
            findings.append(_diagnostic_to_finding(diagnostic, root=root))
    return findings


def run_ruff_on_path(path: Path) -> list[ReviewFinding]:
    result = subprocess.run(
        ruff_target_args(path),
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode not in {0, 1}:
        message = result.stderr.strip() or result.stdout.strip() or "ruff check failed"
        raise RuffRunnerError(message)
    return parse_ruff_output(result.stdout, root=path)


def run_ruff_on_contents(file_contents: dict[str, str]) -> list[ReviewFinding]:
    python_files = {
        file_path: content
        for file_path, content in file_contents.items()
        if Path(file_path).suffix in PYTHON_SUFFIXES
    }
    if not python_files:
        return []

    with tempfile.TemporaryDirectory(prefix="reviewpilot-ruff-") as tmp:
        root = Path(tmp)
        for file_path, content in python_files.items():
            target = _safe_target_path(root, file_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return run_ruff_on_path(root)


async def run_ruff_validator(file_contents: dict[str, str]) -> list[ReviewFinding]:
    return run_ruff_on_contents(file_contents)


def _diagnostic_to_finding(diagnostic: dict[str, Any], root: Path | None) -> ReviewFinding:
    code = str(diagnostic.get("code") or "RUFF")
    message = str(diagnostic.get("message") or "Ruff diagnostic")
    filename = _normalize_filename(diagnostic.get("filename"), root=root)
    line_number = _line_number(diagnostic.get("location"))

    return ReviewFinding(
        severity=_severity_for_code(code),
        title=f"Ruff {code}: {message}",
        evidence=_evidence(code, message, filename, line_number),
        confidence=1.0,
        recommendation=_recommendation(diagnostic),
        file_path=filename,
        line_number=line_number,
        source="ruff",
    )


def _severity_for_code(code: str) -> Severity:
    if code in {"F821", "F822", "F823"} or code.startswith("E9"):
        return Severity.p1
    if code.startswith(("F", "B", "C90", "SIM")):
        return Severity.p2
    return Severity.p3


def _evidence(code: str, message: str, filename: str | None, line_number: int | None) -> str:
    location = filename or "unknown file"
    if line_number is not None:
        location = f"{location}:{line_number}"
    return f"{location} - {code}: {message}"


def _recommendation(diagnostic: dict[str, Any]) -> str:
    fix = diagnostic.get("fix")
    if isinstance(fix, dict):
        message = fix.get("message")
        if isinstance(message, str) and message:
            return message
    return "Address the ruff diagnostic before merging."


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


def _line_number(location: Any) -> int | None:
    if not isinstance(location, dict):
        return None
    row = location.get("row")
    if isinstance(row, int) and row >= 1:
        return row
    return None


def _safe_target_path(root: Path, file_path: str) -> Path:
    candidate = root.joinpath(*_safe_parts(file_path)).resolve()
    resolved_root = root.resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise RuffRunnerError(f"Refusing to write outside temp directory: {file_path}")
    return candidate


def _safe_parts(file_path: str) -> Sequence[str]:
    parts = [part for part in Path(file_path).parts if part not in {"", ".", ".."}]
    if parts and Path(parts[0]).anchor:
        parts = parts[1:]
    return parts or ["snippet.py"]
