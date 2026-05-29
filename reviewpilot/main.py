from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from reviewpilot.api import auth, feedback, review
from reviewpilot.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)
    app.mount("/static", StaticFiles(directory="reviewpilot/static"), name="static")
    app.include_router(auth.router)
    app.include_router(review.router)
    app.include_router(feedback.router)
    return app


app = create_app()
