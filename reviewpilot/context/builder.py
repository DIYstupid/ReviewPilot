from dataclasses import dataclass, field

from reviewpilot.context.ast_graph import SymbolContext
from reviewpilot.context.diff import DiffFile, DiffHunk, flatten_hunks, parse_unified_diff
from reviewpilot.context.files import FileContext, build_file_contexts
from reviewpilot.fetcher.github_api import PullRequestSnapshot


@dataclass(frozen=True)
class ReviewContext:
    pr_title: str
    pr_body: str
    commits: list[str] = field(default_factory=list)
    diff_files: list[DiffFile] = field(default_factory=list)
    hunks: list[DiffHunk] = field(default_factory=list)
    changed_files: dict[str, str] = field(default_factory=dict)
    file_contexts: dict[str, FileContext] = field(default_factory=dict)
    symbols: list[SymbolContext] = field(default_factory=list)


def build_review_context(
    snapshot: PullRequestSnapshot,
    file_contents: dict[str, str] | None = None,
    max_chars_per_file: int = 16_000,
    max_total_file_chars: int = 64_000,
) -> ReviewContext:
    diff_files = parse_unified_diff(snapshot.diff)
    return ReviewContext(
        pr_title=snapshot.metadata.title,
        pr_body=snapshot.metadata.body,
        commits=snapshot.commits,
        diff_files=diff_files,
        hunks=flatten_hunks(diff_files),
        changed_files={changed_file.filename: changed_file.patch or "" for changed_file in snapshot.files},
        file_contexts=build_file_contexts(
            file_contents or {},
            max_chars_per_file=max_chars_per_file,
            max_total_chars=max_total_file_chars,
        ),
    )
