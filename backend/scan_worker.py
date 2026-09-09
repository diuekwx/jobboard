"""Single-slot durable Gmail scan worker.

Run separately from Uvicorn with ``python -m backend.scan_worker``. The queue
is persisted in the application database, so page closes and worker restarts
do not discard committed scan progress.
"""

import logging
import os
import signal
import socket
import threading
import uuid

from backend.db.session import SessionLocal
# A standalone worker does not import FastAPI's application bootstrap. Register
# every mapped table before claiming a ScanJob so SQLAlchemy can resolve foreign
# keys and relationship targets during its first flush.
from backend.models import (  # noqa: F401
    db_application,
    db_applicationsync,
    db_event,
    db_integrationtokens,
    db_processedmessage,
    db_response,
    db_scanjob,
    db_users,
)
from backend.service.scan_job_service import claim_next_scan_job, process_claimed_scan_job


logger = logging.getLogger(__name__)
POLL_SECONDS = max(0.25, float(os.getenv("GMAIL_SCAN_POLL_SECONDS", "1")))


def run_worker(stop: threading.Event | None = None) -> None:
    stop = stop or threading.Event()
    worker_id = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    logger.info("Gmail scan worker %s started", worker_id)

    while not stop.is_set():
        with SessionLocal() as db:
            job = claim_next_scan_job(db, worker_id)
            if job is not None:
                try:
                    process_claimed_scan_job(db, job)
                except Exception:
                    logger.exception("Gmail scan job %s failed", job.id)
                continue
        stop.wait(POLL_SECONDS)


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    stop = threading.Event()

    def request_stop(*_args):
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)
    run_worker(stop)


if __name__ == "__main__":
    main()
