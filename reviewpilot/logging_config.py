from __future__ import annotations

import sys

from loguru import logger


def setup_logging() -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{extra[job_id]}</cyan> | "
            "<level>{message}</level>"
        ),
        level="DEBUG",
    )


def job_logger(job_id: str):
    return logger.bind(job_id=job_id)
