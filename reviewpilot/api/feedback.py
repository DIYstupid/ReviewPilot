from typing import Any
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request

from reviewpilot.db import save_feedback

router = APIRouter(tags=["feedback"])


@router.post("/feedback")
async def create_feedback(request: Request) -> dict[str, Any]:
    payload = await _read_payload(request)
    job_id = _field(payload, "job_id")
    vote = _field(payload, "vote").lower()
    finding_key = _field(payload, "finding_key") or None
    comment = _field(payload, "comment")

    if not job_id:
        raise HTTPException(status_code=400, detail="Missing job_id")
    if vote not in {"up", "down"}:
        raise HTTPException(status_code=400, detail="Invalid vote")

    record = save_feedback(
        job_id=job_id,
        vote=vote,
        finding_key=finding_key,
        comment=comment,
    )
    return {"status": "accepted", "id": record.id}


async def _read_payload(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        data = await request.json()
        return data if isinstance(data, dict) else {}

    form = parse_qs((await request.body()).decode("utf-8"))
    return {key: values[0] for key, values in form.items() if values}


def _field(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value or "").strip()
