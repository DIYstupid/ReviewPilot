from pathlib import Path


def semgrep_target_args(path: Path) -> list[str]:
    return ["semgrep", "scan", str(path)]
