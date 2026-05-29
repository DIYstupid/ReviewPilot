from dataclasses import dataclass, field


@dataclass(frozen=True)
class DiffHunk:
    header: str
    lines: list[str] = field(default_factory=list)
