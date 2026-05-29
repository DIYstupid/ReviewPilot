from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from hashlib import sha1
from typing import Any

from reviewpilot.analyzer.llm import ChatCompletionClient, create_deepseek_client
from reviewpilot.analyzer.line_review import LineReviewResult, generate_inline_reviews
from reviewpilot.analyzer.risk import RiskAnalysisResult, generate_risks
from reviewpilot.analyzer.schemas import ReviewFinding, ReviewReport
from reviewpilot.analyzer.summary import SummaryResult, generate_summary
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
from reviewpilot.validator.ruff_runner import run_ruff_validator


SnapshotFetcher = Callable[[PullRequestRef], Awaitable[PullRequestSnapshot]]
StaticValidator = Callable[[dict[str, str]], Awaitable[list[ReviewFinding]]]


class ReviewConfigurationError(RuntimeError):
    """Raised when the configured review pipeline cannot be built."""


@dataclass(frozen=True)
class ReviewEvent:
    event: str
    data: dict[str, Any]
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ReviewJob:
    job_id: str
    pr_url: str
    ref: PullRequestRef
    status: str
    github_token: str | None = None
    report: ReviewReport | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    events: tuple[ReviewEvent, ...] = ()


class ReviewJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, ReviewJob] = {}

    def put(self, job: ReviewJob) -> None:
        self._jobs[job.job_id] = job

    def get(self, job_id: str) -> ReviewJob | None:
        return self._jobs.get(job_id)

    def create_pending(self, pr_url: str, *, github_token: str | None = None) -> ReviewJob:
        ref = parse_pr_url(pr_url)
        job_id = stable_job_id(ref)
        job = ReviewJob(
            job_id=job_id,
            pr_url=pr_url,
            ref=ref,
            status="pending",
            github_token=github_token,
        )
        job = replace(job, events=(_review_event(job_id, "status", {"status": "pending"}),))
        self.put(job)
        return job

    def update_status(self, job_id: str, status: str) -> ReviewJob:
        job = self._require(job_id)
        updated = replace(
            job,
            status=status,
            events=job.events + (_review_event(job_id, "status", {"status": status}),),
        )
        self.put(updated)
        return updated

    def complete(self, job_id: str, report: ReviewReport) -> ReviewJob:
        job = self._require(job_id)
        updated = replace(
            job,
            status="complete",
            github_token=None,
            report=report,
            error=None,
            events=job.events
            + (
                _review_event(job_id, "report", report.model_dump(mode="json")),
                _review_event(job_id, "status", {"status": "complete"}),
            ),
        )
        self.put(updated)
        return updated

    def fail(self, job_id: str, error: str) -> ReviewJob:
        job = self._require(job_id)
        updated = replace(
            job,
            status="failed",
            github_token=None,
            error=error,
            events=job.events
            + (
                _review_event(job_id, "error", {"message": error}),
                _review_event(job_id, "status", {"status": "failed"}),
            ),
        )
        self.put(updated)
        return updated

    def record_stage_error(self, job_id: str, stage: str, message: str) -> ReviewJob:
        job = self._require(job_id)
        updated = replace(
            job,
            events=job.events
            + (_review_event(job_id, "stage_error", {"stage": stage, "message": message}),),
        )
        self.put(updated)
        return updated

    def clear(self) -> None:
        self._jobs.clear()

    def _require(self, job_id: str) -> ReviewJob:
        job = self.get(job_id)
        if job is None:
            raise KeyError(f"Review job not found: {job_id}")
        return job


job_store = ReviewJobStore()


@dataclass(frozen=True)
class ReviewPipelineClients:
    summary: ChatCompletionClient | None = None
    risk: ChatCompletionClient | None = None
    line_review: ChatCompletionClient | None = None


async def create_offline_review_job(pr_url: str) -> ReviewJob:
    return await create_review_job(pr_url)


def create_pending_configured_review_job(pr_url: str, *, github_token: str | None = None) -> ReviewJob:
    validate_review_configuration()
    return job_store.create_pending(pr_url, github_token=github_token)


async def run_configured_review_job(job_id: str) -> ReviewJob:
    job = job_store.get(job_id)
    if job is None:
        raise KeyError(f"Review job not found: {job_id}")

    try:
        return await create_configured_review_job(
            job.pr_url,
            job_id=job.job_id,
            github_token=job.github_token,
            record_events=True,
        )
    except Exception as exc:
        return job_store.fail(job_id, str(exc))


async def create_configured_review_job(
    pr_url: str,
    *,
    job_id: str | None = None,
    github_token: str | None = None,
    record_events: bool = False,
) -> ReviewJob:
    settings = get_settings()
    clients = build_review_pipeline_clients(settings.review_llm_provider)
    static_validator = build_static_validator(getattr(settings, "review_static_validator", "none"))
    fetch_mode = _normalize_mode(settings.review_fetch_mode)

    if fetch_mode == "offline":
        return await create_review_job(
            pr_url,
            clients=clients,
            job_id=job_id,
            record_events=record_events,
            static_validator=static_validator,
        )
    if fetch_mode == "github":
        return await create_github_review_job(
            pr_url,
            clients=clients,
            github_token=github_token,
            job_id=job_id,
            record_events=record_events,
            static_validator=static_validator,
        )
    raise ReviewConfigurationError(f"Unsupported review_fetch_mode: {settings.review_fetch_mode}")


async def create_github_review_job(
    pr_url: str,
    *,
    clients: ReviewPipelineClients | None = None,
    file_contents: dict[str, str] | None = None,
    github_token: str | None = None,
    job_id: str | None = None,
    record_events: bool = False,
    static_validator: StaticValidator | None = None,
) -> ReviewJob:
    settings = get_settings()
    github = GitHubClient(token=github_token or settings.github_pat)
    ref = parse_pr_url(pr_url)
    review_job_id = job_id or stable_job_id(ref)
    if record_events and job_store.get(review_job_id) is None:
        job_store.create_pending(pr_url)

    _record_status(review_job_id, "fetching", record_events)
    snapshot = await github.fetch_pull_request(ref)
    if file_contents is None:
        _record_status(review_job_id, "fetching_files", record_events)
        file_contents = await github.fetch_changed_file_contents(snapshot)

    return await _create_review_job_from_snapshot(
        pr_url=pr_url,
        ref=ref,
        snapshot=snapshot,
        clients=clients,
        file_contents=file_contents,
        job_id=review_job_id,
        record_events=record_events,
        static_validator=static_validator,
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
    job_id: str | None = None,
    record_events: bool = False,
    static_validator: StaticValidator | None = None,
) -> ReviewJob:
    ref = parse_pr_url(pr_url)
    review_job_id = job_id or stable_job_id(ref)
    if record_events and job_store.get(review_job_id) is None:
        job_store.create_pending(pr_url)

    _record_status(review_job_id, "fetching", record_events)
    snapshot = await snapshot_fetcher(ref) if snapshot_fetcher else _empty_snapshot(ref, pr_url)
    return await _create_review_job_from_snapshot(
        pr_url=pr_url,
        ref=ref,
        snapshot=snapshot,
        clients=clients,
        file_contents=file_contents,
        job_id=review_job_id,
        record_events=record_events,
        static_validator=static_validator,
    )


async def _create_review_job_from_snapshot(
    *,
    pr_url: str,
    ref: PullRequestRef,
    snapshot: PullRequestSnapshot,
    clients: ReviewPipelineClients | None,
    file_contents: dict[str, str] | None,
    job_id: str,
    record_events: bool,
    static_validator: StaticValidator | None,
) -> ReviewJob:
    _record_status(job_id, "building_context", record_events)
    try:
        context = build_review_context(snapshot, file_contents=file_contents)
    except Exception as exc:
        _record_error(job_id, "building_context", str(exc), record_events)
        context = build_review_context(snapshot, file_contents={})

    pipeline_clients = clients or ReviewPipelineClients()

    _record_status(job_id, "analyzing_summary", record_events)
    try:
        summary = await generate_summary(context, client=pipeline_clients.summary)
    except Exception as exc:
        _record_error(job_id, "summary", str(exc), record_events)
        summary = SummaryResult(content="Summary generation failed.")

    _record_status(job_id, "analyzing_risks", record_events)
    try:
        risks = await generate_risks(context, client=pipeline_clients.risk)
    except Exception as exc:
        _record_error(job_id, "risks", str(exc), record_events)
        risks = RiskAnalysisResult(risks=[])

    _record_status(job_id, "analyzing_lines", record_events)
    try:
        inline_reviews = await generate_inline_reviews(context, client=pipeline_clients.line_review)
    except Exception as exc:
        _record_error(job_id, "inline_reviews", str(exc), record_events)
        inline_reviews = LineReviewResult(inline_reviews=[])

    _record_status(job_id, "validating_static", record_events)
    try:
        static_findings = await static_validator(file_contents or {}) if static_validator else []
    except Exception as exc:
        _record_error(job_id, "static_validation", str(exc), record_events)
        static_findings = []

    _record_status(job_id, "postprocessing", record_events)
    report = build_review_report(
        summary=summary.content,
        risks=risks.risks + static_findings,
        inline_reviews=inline_reviews.inline_reviews,
    )
    if record_events:
        return job_store.complete(job_id, report)

    job = ReviewJob(job_id=job_id, pr_url=pr_url, ref=ref, status="complete", report=report)
    job_store.put(job)
    return job


def validate_review_configuration() -> None:
    settings = get_settings()
    fetch_mode = _normalize_mode(settings.review_fetch_mode)
    if fetch_mode not in {"offline", "github"}:
        raise ReviewConfigurationError(f"Unsupported review_fetch_mode: {settings.review_fetch_mode}")
    build_review_pipeline_clients(settings.review_llm_provider)
    build_static_validator(getattr(settings, "review_static_validator", "none"))


def build_review_pipeline_clients(provider: str | None = None) -> ReviewPipelineClients:
    llm_provider = _normalize_mode(provider)
    if llm_provider == "offline":
        return ReviewPipelineClients()
    if llm_provider == "deepseek":
        client = create_deepseek_client()
        return ReviewPipelineClients(summary=client, risk=client, line_review=client)
    raise ReviewConfigurationError(f"Unsupported review_llm_provider: {provider}")


def build_static_validator(provider: str | None = None) -> StaticValidator | None:
    static_provider = _normalize_mode(provider)
    if static_provider in {"none", "offline"}:
        return None
    if static_provider == "ruff":
        return run_ruff_validator
    raise ReviewConfigurationError(f"Unsupported review_static_validator: {provider}")


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


def _record_status(job_id: str, status: str, enabled: bool) -> None:
    if enabled:
        job_store.update_status(job_id, status)


def _record_error(job_id: str, stage: str, message: str, enabled: bool) -> None:
    if enabled:
        job_store.record_stage_error(job_id, stage, message)


def _review_event(job_id: str, event: str, data: dict[str, Any]) -> ReviewEvent:
    return ReviewEvent(event=event, data={"job_id": job_id, **data})
