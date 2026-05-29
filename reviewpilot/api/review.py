from __future__ import annotations

import asyncio
import json
from urllib.parse import parse_qs

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from reviewpilot.analyzer.llm import LLMConfigurationError
from reviewpilot.auth.session import get_github_token_from_request
from reviewpilot.fetcher.github_api import GitHubAPIError
from reviewpilot.markdown import render_markdown
from reviewpilot.review_service import (
    ReviewConfigurationError,
    create_pending_configured_review_job,
    job_store,
    run_configured_review_job,
)

router = APIRouter(tags=["review"])
templates = Jinja2Templates(directory="reviewpilot/templates")
templates.env.filters["markdown"] = render_markdown


@router.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@router.post("/review")
async def create_review(request: Request, background_tasks: BackgroundTasks):
    form = parse_qs((await request.body()).decode("utf-8"))
    pr_url = (form.get("pr_url") or [""])[0]
    if not pr_url:
        raise HTTPException(status_code=400, detail="Missing pr_url")

    try:
        job = create_pending_configured_review_job(
            pr_url,
            github_token=get_github_token_from_request(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (GitHubAPIError, LLMConfigurationError, ReviewConfigurationError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    background_tasks.add_task(run_configured_review_job, job.job_id)
    return RedirectResponse(url=f"/review/{job.job_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/review/{job_id}")
async def review_page(request: Request, job_id: str):
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Review job not found")
    return templates.TemplateResponse(request, "review.html", {"job": job, "job_id": job_id})


@router.get("/review/{job_id}/stream")
async def stream_review(job_id: str):
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Review job not found")

    async def events():
        sent_events = 0
        while True:
            current_job = job_store.get(job_id)
            if current_job is None:
                payload = json.dumps({"job_id": job_id, "message": "Review job not found"})
                yield f"event: error\ndata: {payload}\n\n"
                return

            for event in current_job.events[sent_events:]:
                payload = json.dumps(event.data, ensure_ascii=False)
                yield f"event: {event.event}\ndata: {payload}\n\n"
            sent_events = len(current_job.events)

            if current_job.status in {"complete", "failed"}:
                return
            await asyncio.sleep(0.2)

    return StreamingResponse(events(), media_type="text/event-stream")
