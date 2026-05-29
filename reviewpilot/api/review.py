from __future__ import annotations

import json
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from reviewpilot.fetcher.github_api import parse_pr_url

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
        ref = parse_pr_url(pr_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job_id = f"{ref.owner}-{ref.repo}-{ref.number}"
    return RedirectResponse(url=f"/review/{job_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/review/{job_id}")
async def review_page(request: Request, job_id: str):
    return templates.TemplateResponse("review.html", {"request": request, "job_id": job_id})


@router.get("/review/{job_id}/stream")
async def stream_review(job_id: str):
    async def events():
        payload = json.dumps({"job_id": job_id, "status": "pending"})
        yield f"event: status\ndata: {payload}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
