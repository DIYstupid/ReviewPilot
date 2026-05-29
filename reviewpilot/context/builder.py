from dataclasses import dataclass, field

from reviewpilot.context.ast_graph import SymbolContext
from reviewpilot.context.diff import DiffFile, DiffHunk, flatten_hunks, parse_unified_diff
from reviewpilot.fetcher.github_api import PullRequestSnapshot


@dataclass(frozen=True)
class ReviewContext:
    pr_title: str
    pr_body: str
    commits: list[str] = field(default_factory=list)
    diff_files: list[DiffFile] = field(default_factory=list)
    hunks: list[DiffHunk] = field(default_factory=list)
    changed_files: dict[str, str] = field(default_factory=dict)
    symbols: list[SymbolContext] = field(default_factory=list)


def build_review_context(snapshot: PullRequestSnapshot) -> ReviewContext:
    diff_files = parse_unified_diff(snapshot.diff)
    return ReviewContext(
        pr_title=snapshot.metadata.title,
        pr_body=snapshot.metadata.body,
        commits=snapshot.commits,
        diff_files=diff_files,
        hunks=flatten_hunks(diff_files),
        changed_files={changed_file.filename: changed_file.patch or "" for changed_file in snapshot.files},
    )
