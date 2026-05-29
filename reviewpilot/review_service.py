from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha1

from reviewpilot.analyzer.llm import ChatCompletionClient, create_deepseek_client
from reviewpilot.analyzer.line_review import generate_inline_reviews
from reviewpilot.analyzer.risk import generate_risks
from reviewpilot.analyzer.schemas import ReviewReport
from reviewpilot.analyzer.summary import generate_summary
from reviewpilot.config import get_settings
from reviewpilot.context.builder import build_review_context
from reviewpilot.fetcher.github_api import (
    GitHubClient,
    PullRequestMetadata,
    PullRequestRef,
    PullRequestSnapshot,
    parse_pr_url,
)
from reviewpilot.post.report import build_review_report


SnapshotFetcher = Callable[[PullRequestRef], Awaitable[PullRequestSnapshot]]


class ReviewConfigurationError(RuntimeError):
    """Raised when the configured review pipeline cannot be built."""


@dataclass(frozen=True)
class ReviewJob:
    job_id: str
    pr_url: str
    ref: PullRequestRef
    status: str
    report: ReviewReport | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class ReviewJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, ReviewJob] = {}

    def put(self, job: ReviewJob) -> None:
        self._jobs[job.job_id] = job

    def get(self, job_id: str) -> ReviewJob | None:
        return self._jobs.get(job_id)

    def clear(self) -> None:
        self._jobs.clear()


job_store = ReviewJobStore()


@dataclass(frozen=True)
class ReviewPipelineClients:
    summary: ChatCompletionClient | None = None
    risk: ChatCompletionClient | None = None
    line_review: ChatCompletionClient | None = None


async def create_offline_review_job(pr_url: str) -> ReviewJob:
    return await create_review_job(pr_url)


async def create_configured_review_job(pr_url: str) -> ReviewJob:
    settings = get_settings()
    clients = build_review_pipeline_clients(settings.review_llm_provider)
    fetch_mode = _normalize_mode(settings.review_fetch_mode)

    if fetch_mode == "offline":
        return await create_review_job(pr_url, clients=clients)
    if fetch_mode == "github":
        return await create_github_review_job(pr_url, clients=clients)
    raise ReviewConfigurationError(f"Unsupported review_fetch_mode: {settings.review_fetch_mode}")


async def create_github_review_job(
    pr_url: str,
    *,
    clients: ReviewPipelineClients | None = None,
    file_contents: dict[str, str] | None = None,
) -> ReviewJob:
    settings = get_settings()
    github = GitHubClient(token=settings.github_pat)
    return await create_review_job(
        pr_url,
        snapshot_fetcher=github.fetch_pull_request,
        clients=clients,
        file_contents=file_contents,
    )


async def create_deepseek_review_job(
    pr_url: str,
    *,
    snapshot_fetcher: SnapshotFetcher | None = None,
    file_contents: dict[str, str] | None = None,
) -> ReviewJob:
    return await create_review_job(
        pr_url,
        snapshot_fetcher=snapshot_fetcher,
        clients=build_review_pipeline_clients("deepseek"),
        file_contents=file_contents,
    )


async def create_review_job(
    pr_url: str,
    *,
    snapshot_fetcher: SnapshotFetcher | None = None,
    clients: ReviewPipelineClients | None = None,
    file_contents: dict[str, str] | None = None,
) -> ReviewJob:
    ref = parse_pr_url(pr_url)
    job_id = stable_job_id(ref)
    snapshot = await snapshot_fetcher(ref) if snapshot_fetcher else _empty_snapshot(ref, pr_url)
    context = build_review_context(snapshot, file_contents=file_contents)
    pipeline_clients = clients or ReviewPipelineClients()
    summary = await generate_summary(context, client=pipeline_clients.summary)
    risks = await generate_risks(context, client=pipeline_clients.risk)
    inline_reviews = await generate_inline_reviews(context, client=pipeline_clients.line_review)
    report = build_review_report(
        summary=summary.content,
        risks=risks.risks,
        inline_reviews=inline_reviews.inline_reviews,
    )
    job = ReviewJob(job_id=job_id, pr_url=pr_url, ref=ref, status="complete", report=report)
    job_store.put(job)
    return job


def build_review_pipeline_clients(provider: str | None = None) -> ReviewPipelineClients:
    llm_provider = _normalize_mode(provider)
    if llm_provider == "offline":
        return ReviewPipelineClients()
    if llm_provider == "deepseek":
        client = create_deepseek_client()
        return ReviewPipelineClients(summary=client, risk=client, line_review=client)
    raise ReviewConfigurationError(f"Unsupported review_llm_provider: {provider}")


def stable_job_id(ref: PullRequestRef) -> str:
    digest = sha1(f"{ref.owner}/{ref.repo}/{ref.number}".encode("utf-8")).hexdigest()[:10]
    return f"{ref.owner}-{ref.repo}-{ref.number}-{digest}"


def _empty_snapshot(ref: PullRequestRef, pr_url: str) -> PullRequestSnapshot:
    return PullRequestSnapshot(
        ref=ref,
        metadata=PullRequestMetadata(
            title=f"{ref.owner}/{ref.repo}#{ref.number}",
            body="",
            state="unknown",
            draft=False,
            html_url=pr_url,
            base_ref="",
            head_ref="",
            author="",
            changed_files=0,
            additions=0,
            deletions=0,
        ),
    )


def _normalize_mode(value: str | None) -> str:
    return (value or "offline").strip().lower()
