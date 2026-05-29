from sqlmodel import SQLModel, create_engine

from reviewpilot.config import get_settings


def get_engine():
    settings = get_settings()
    return create_engine(settings.database_url)


def init_db() -> None:
    SQLModel.metadata.create_all(get_engine())
