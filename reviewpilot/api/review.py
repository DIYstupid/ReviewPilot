from __future__ import annotations

import json
from urllib.parse import parse_qs

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from reviewpilot.analyzer.llm import LLMConfigurationError
from reviewpilot.auth.session import get_github_token_from_request
from reviewpilot.fetcher.github_api import GitHubAPIError
from reviewpilot.markdown import render_markdown
from reviewpilot.render import render_report_markdown
from reviewpilot.review_service import (
    ReviewConfigurationError,
    create_pending_configured_review_job,
    job_store,
    run_configured_review_job,
)

router = APIRouter(tags=["review"])
templates = Jinja2Templates(directory="reviewpilot/templates")
templates.env.filters["markdown"] = render_markdown


def _confidence_level_css(confidence: float) -> str:
    if confidence >= 0.8:
        return "confidence-high"
    if confidence >= 0.5:
        return "confidence-medium"
    return "confidence-low"


templates.env.filters["confidence_level"] = _confidence_level_css


def _line_anchor(file_path: str | None, line_number: int | None) -> str:
    if not file_path or line_number is None:
        return ""
    safe_path = "".join(ch if ch.isalnum() else "-" for ch in file_path).strip("-")
    return f"diff-{safe_path}-R{line_number}"


templates.env.filters["line_anchor"] = _line_anchor


@router.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@router.post("/review")
async def create_review(request: Request, background_tasks: BackgroundTasks):
    form = parse_qs((await request.body()).decode("utf-8"))
    pr_url = (form.get("pr_url") or [""])[0]
    report_language = (form.get("report_language") or ["en"])[0]
    if not pr_url:
        raise HTTPException(status_code=400, detail="Missing pr_url")

    try:
        job = create_pending_configured_review_job(
            pr_url,
            github_token=get_github_token_from_request(request),
            report_language=report_language,
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
    diff_files = _event_payload(job.events, "diff", "diff_files") or []
    stage_timings = _stage_timings(job.events)
    return templates.TemplateResponse(
        request,
        "review.html",
        {
            "job": job,
            "job_id": job_id,
            "diff_files": diff_files,
            "stage_timings": stage_timings,
        },
    )


@router.get("/review/{job_id}/report.md")
async def download_report_markdown(job_id: str):
    job = job_store.get(job_id)
    if job is None or job.report is None:
        raise HTTPException(status_code=404, detail="Review report not found")
    content = render_report_markdown(job.report, report_language=job.report_language)
    return PlainTextResponse(
        content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{job_id}.md"'},
    )


@router.get("/review/{job_id}/report.json")
async def download_report_json(job_id: str):
    job = job_store.get(job_id)
    if job is None or job.report is None:
        raise HTTPException(status_code=404, detail="Review report not found")
    return JSONResponse(
        job.report.model_dump(mode="json"),
        headers={"Content-Disposition": f'attachment; filename="{job_id}.json"'},
    )


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
            await job_store._wait_for_events(job_id)

    return StreamingResponse(events(), media_type="text/event-stream")


def _event_payload(events, event_name: str, key: str):
    for event in events:
        if event.event == event_name:
            return event.data.get(key)
    return None


def _stage_timings(events) -> dict[str, dict]:
    timings = {}
    for event in events:
        if event.event == "stage_timing":
            stage = event.data.get("stage")
            if isinstance(stage, str):
                timings[stage] = event.data
    return timings
