import pytest

from reviewpilot.review_service import create_offline_review_job, job_store, stable_job_id
from reviewpilot.fetcher.github_api import PullRequestRef


def test_stable_job_id_is_deterministic() -> None:
    ref = PullRequestRef(owner="owner", repo="repo", number=1)

    assert stable_job_id(ref) == stable_job_id(ref)
    assert stable_job_id(ref).startswith("owner-repo-1-")


@pytest.mark.asyncio
async def test_create_offline_review_job_stores_complete_report() -> None:
    job_store.clear()

    job = await create_offline_review_job("https://github.com/owner/repo/pull/1")

    assert job.status == "complete"
    assert job.report is not None
    assert "owner/repo#1" in job.report.summary
    assert job_store.get(job.job_id) == job
