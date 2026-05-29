from pathlib import Path


def test_prompt_templates_exist() -> None:
    prompt_dir = Path("reviewpilot/analyzer/prompts")
    assert (prompt_dir / "summary.j2").exists()
    assert (prompt_dir / "risk.j2").exists()
    assert (prompt_dir / "line_review.j2").exists()
