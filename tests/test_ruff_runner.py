from pathlib import Path

import pytest

from reviewpilot.analyzer.schemas import Severity
from reviewpilot.validator.ruff_runner import (
    RuffRunnerError,
    parse_ruff_output,
    run_ruff_on_contents,
    run_ruff_validator,
    ruff_target_args,
)


def test_ruff_target_args_uses_json_output() -> None:
    args = ruff_target_args(Path("src"))

    assert args[1:6] == ["-m", "ruff", "check", "--output-format", "json"]
    assert args[-1] == "src"


def test_parse_ruff_output_maps_diagnostic_to_finding(tmp_path: Path) -> None:
    file_path = tmp_path / "app.py"
    content = f"""
[
  {{
    "code": "F821",
    "filename": "{file_path.as_posix()}",
    "location": {{"row": 3, "column": 12}},
    "message": "Undefined name `user`",
    "fix": null
  }}
]
"""

    findings = parse_ruff_output(content, root=tmp_path)

    assert len(findings) == 1
    assert findings[0].severity == Severity.p1
    assert findings[0].title == "Ruff F821: Undefined name `user`"
    assert findings[0].file_path == "app.py"
    assert findings[0].line_number == 3
    assert findings[0].confidence == 1.0


def test_parse_ruff_output_rejects_invalid_json() -> None:
    with pytest.raises(RuffRunnerError):
        parse_ruff_output("not json")


def test_run_ruff_on_contents_returns_findings_for_python_files() -> None:
    findings = run_ruff_on_contents({"app.py": "def get_user():\n    return user\n"})

    assert any(finding.file_path == "app.py" for finding in findings)
    assert any(finding.severity == Severity.p1 for finding in findings)


def test_run_ruff_on_contents_ignores_non_python_files() -> None:
    assert run_ruff_on_contents({"README.md": "# docs\n"}) == []


@pytest.mark.asyncio
async def test_run_ruff_validator_is_pipeline_compatible() -> None:
    findings = await run_ruff_validator({"app.py": "print(user)\n"})

    assert findings[0].file_path == "app.py"
