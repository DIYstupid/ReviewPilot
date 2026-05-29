from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Column, Text
from sqlmodel import Field, SQLModel, Session, create_engine, delete, select

from reviewpilot.config import get_settings


class JobRecord(SQLModel, table=True):
    __tablename__ = "job_record"
    job_id: str = Field(primary_key=True)
    pr_url: str
    owner: str
    repo: str
    number: int
    status: str
    error: str | None = Field(default=None)
    report_json: str | None = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EventRecord(SQLModel, table=True):
    __tablename__ = "event_record"
    id: int | None = Field(default=None, primary_key=True)
    job_id: str = Field(foreign_key="job_record.job_id", index=True)
    event: str
    data_json: str = Field(sa_column=Column(Text))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


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


def upsert_job(
    *,
    job_id: str,
    pr_url: str,
    owner: str,
    repo: str,
    number: int,
    status: str,
    error: str | None = None,
    report_json: str | None = None,
    engine=None,
) -> None:
    target_engine = engine or get_engine()
    init_db(target_engine)
    with Session(target_engine) as session:
        existing = session.get(JobRecord, job_id)
        if existing:
            existing.pr_url = pr_url
            existing.owner = owner
            existing.repo = repo
            existing.number = number
            existing.status = status
            existing.error = error
            existing.report_json = report_json
            existing.updated_at = datetime.now(UTC)
        else:
            record = JobRecord(
                job_id=job_id,
                pr_url=pr_url,
                owner=owner,
                repo=repo,
                number=number,
                status=status,
                error=error,
                report_json=report_json,
            )
            session.add(record)
        session.commit()


def get_job_record(job_id: str, engine=None) -> JobRecord | None:
    target_engine = engine or get_engine()
    init_db(target_engine)
    with Session(target_engine) as session:
        return session.get(JobRecord, job_id)


def get_event_records(job_id: str, *, engine=None) -> list[EventRecord]:
    target_engine = engine or get_engine()
    init_db(target_engine)
    with Session(target_engine) as session:
        statement = (
            select(EventRecord)
            .where(EventRecord.job_id == job_id)
            .order_by(EventRecord.created_at)
        )
        return list(session.exec(statement).all())


def insert_event(
    *,
    job_id: str,
    event: str,
    data_json: str,
    created_at: datetime,
    engine=None,
) -> None:
    target_engine = engine or get_engine()
    init_db(target_engine)
    record = EventRecord(
        job_id=job_id,
        event=event,
        data_json=data_json,
        created_at=created_at,
    )
    with Session(target_engine) as session:
        session.add(record)
        session.commit()


def clear_all_jobs(engine=None) -> None:
    target_engine = engine or get_engine()
    init_db(target_engine)
    with Session(target_engine) as session:
        session.exec(delete(EventRecord))
        session.exec(delete(JobRecord))
        session.commit()
