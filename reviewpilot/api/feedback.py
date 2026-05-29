from fastapi import APIRouter

router = APIRouter(tags=["feedback"])


@router.post("/feedback")
async def create_feedback() -> dict[str, str]:
    return {"status": "accepted"}
