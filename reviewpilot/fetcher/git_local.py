from pathlib import Path


def repo_checkout_dir(base_dir: Path, owner: str, repo: str, pr_number: int) -> Path:
    return base_dir / owner / repo / f"pr-{pr_number}"
