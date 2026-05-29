from dataclasses import dataclass, field

from reviewpilot.context.ast_graph import SymbolContext
from reviewpilot.context.diff import DiffHunk


@dataclass(frozen=True)
class ReviewContext:
    pr_title: str
    pr_body: str
    commits: list[str] = field(default_factory=list)
    hunks: list[DiffHunk] = field(default_factory=list)
    changed_files: dict[str, str] = field(default_factory=dict)
    symbols: list[SymbolContext] = field(default_factory=list)
