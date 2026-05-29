from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel, Session, create_engine, select

from reviewpilot.config import get_settings


class FeedbackRecord(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    job_id: str = Field(index=True)
    vote: str
    finding_key: str | None = Field(default=None, index=True)
    comment: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def get_engine(database_url: str | None = None):
    settings = get_settings()
    return create_engine(database_url or settings.database_url)


def init_db(engine=None) -> None:
    SQLModel.metadata.create_all(engine or get_engine())


def save_feedback(
    *,
    job_id: str,
    vote: str,
    finding_key: str | None = None,
    comment: str = "",
    engine=None,
) -> FeedbackRecord:
    target_engine = engine or get_engine()
    init_db(target_engine)
    record = FeedbackRecord(
        job_id=job_id,
        vote=vote,
        finding_key=finding_key or None,
        comment=comment,
    )
    with Session(target_engine) as session:
        session.add(record)
        session.commit()
        session.refresh(record)
        return record


def list_feedback(*, job_id: str | None = None, engine=None) -> list[FeedbackRecord]:
    target_engine = engine or get_engine()
    init_db(target_engine)
    statement = select(FeedbackRecord)
    if job_id:
        statement = statement.where(FeedbackRecord.job_id == job_id)
    with Session(target_engine) as session:
        return list(session.exec(statement).all())
