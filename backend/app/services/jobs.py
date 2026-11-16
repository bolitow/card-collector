"""Tâches de fond (T-05) : une table, un worker, pas d'autre infrastructure."""

import logging
import uuid
from collections.abc import Callable
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Job
from app.security import now

log = logging.getLogger("jobs")

Handler = Callable[[Session, Job], dict | None]
HANDLERS: dict[str, Handler] = {}
MAX_ATTEMPTS = 3


def handler(kind: str) -> Callable[[Handler], Handler]:
    def register(function: Handler) -> Handler:
        HANDLERS[kind] = function
        return function

    return register


def enqueue(db: Session, kind: str, payload: dict | None = None, user_id: uuid.UUID | None = None) -> Job:
    job = Job(id=uuid.uuid4(), kind=kind, payload=payload or {}, user_id=user_id)
    db.add(job)
    db.flush()
    return job


def run_next(db: Session) -> bool:
    """Prend et exécute une tâche. Renvoie False s'il n'y en a pas."""
    job = db.scalar(
        select(Job)
        .where(Job.status == "queued", Job.run_after <= now())
        .order_by(Job.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return False
    job.status, job.attempts = "running", job.attempts + 1
    db.commit()
    try:
        result = HANDLERS[job.kind](db, job)
        job.status, job.progress, job.result = "done", 100, result or job.result
        job.finished_at = now()
        db.commit()
    except Exception as error:  # une tâche en échec ne doit pas arrêter le worker
        db.rollback()
        log.exception("tâche %s (%s) en échec", job.id, job.kind)
        job = db.get(Job, job.id)
        job.error = str(error)[:2000]
        if job.attempts >= MAX_ATTEMPTS:
            job.status, job.finished_at = "failed", now()
        else:
            job.status, job.run_after = "queued", now() + timedelta(seconds=30 * job.attempts)
        db.commit()
    return True


def run_all(db: Session) -> int:
    """Vide la file (tests, scripts)."""
    count = 0
    while run_next(db):
        count += 1
    return count
