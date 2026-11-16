"""Worker des tâches de fond (T-05). Lancement : `python -m app.worker`."""

import logging
import signal
import time

from sqlalchemy import delete

from app import security
from app.db import get_sessionmaker
from app.deps import purge_rate_limits
from app.models import AuthToken, UserSession
from app.services import accounts, imports, jobs  # noqa: F401 — l'import enregistre les tâches

log = logging.getLogger("worker")
IDLE_SECONDS = 2
HOUSEKEEPING_SECONDS = 3600


def housekeeping() -> None:
    """Durées de conservation (D-04) : sessions et jetons expirés, exports, compteurs de débit."""
    with get_sessionmaker()() as db:
        db.execute(delete(UserSession).where(UserSession.expires_at < security.now()))
        db.execute(delete(AuthToken).where(AuthToken.expires_at < security.now()))
        purge_rate_limits(db)
        accounts.purge_exports(db)
        db.commit()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    running = True

    def stop(*_: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    log.info("worker démarré, tâches connues : %s", ", ".join(sorted(jobs.HANDLERS)))
    last_housekeeping = 0.0
    while running:
        with get_sessionmaker()() as db:
            worked = jobs.run_next(db)
        if time.monotonic() - last_housekeeping > HOUSEKEEPING_SECONDS:
            housekeeping()
            last_housekeeping = time.monotonic()
        if not worked:
            time.sleep(IDLE_SECONDS)
    log.info("worker arrêté")


if __name__ == "__main__":
    main()
