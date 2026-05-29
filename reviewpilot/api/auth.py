from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/github/login")
async def github_login() -> dict[str, str]:
    return {"status": "not_configured"}


@router.get("/github/callback")
async def github_callback() -> dict[str, str]:
    return {"status": "not_configured"}
