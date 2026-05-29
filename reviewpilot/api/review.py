from __future__ import annotations

import json
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from reviewpilot.analyzer.llm import LLMConfigurationError
from reviewpilot.fetcher.github_api import GitHubAPIError
from reviewpilot.review_service import (
    ReviewConfigurationError,
    create_configured_review_job,
    job_store,
)

router = APIRouter(tags=["review"])
templates = Jinja2Templates(directory="reviewpilot/templates")


@router.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@router.post("/review")
async def create_review(request: Request):
    form = parse_qs((await request.body()).decode("utf-8"))
    pr_url = (form.get("pr_url") or [""])[0]
    if not pr_url:
        raise HTTPException(status_code=400, detail="Missing pr_url")

    try:
        job = await create_configured_review_job(pr_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (GitHubAPIError, LLMConfigurationError, ReviewConfigurationError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return RedirectResponse(url=f"/review/{job.job_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/review/{job_id}")
async def review_page(request: Request, job_id: str):
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Review job not found")
    return templates.TemplateResponse("review.html", {"request": request, "job": job, "job_id": job_id})


@router.get("/review/{job_id}/stream")
async def stream_review(job_id: str):
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Review job not found")

    async def events():
        status_payload = json.dumps({"job_id": job_id, "status": job.status})
        yield f"event: status\ndata: {status_payload}\n\n"
        report_payload = json.dumps(
            job.report.model_dump(mode="json") if job.report else {},
            ensure_ascii=False,
        )
        yield f"event: report\ndata: {report_payload}\n\n"
        payload = json.dumps({"job_id": job_id, "status": "done"})
        yield f"event: status\ndata: {payload}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
