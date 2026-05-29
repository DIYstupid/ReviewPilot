from fastapi import APIRouter

router = APIRouter(tags=["review"])


@router.post("/review")
async def create_review() -> dict[str, str]:
    return {"job_id": "placeholder"}


@router.get("/review/{job_id}/stream")
async def stream_review(job_id: str) -> dict[str, str]:
    return {"job_id": job_id, "status": "pending"}
