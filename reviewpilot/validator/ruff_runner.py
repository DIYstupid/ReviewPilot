from pathlib import Path


def ruff_target_args(path: Path) -> list[str]:
    return ["ruff", "check", str(path)]
