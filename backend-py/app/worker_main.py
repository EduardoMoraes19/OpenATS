"""arq worker entrypoint, equivalent to backend/src/worker.ts.

Run with: `python -m app.worker_main` or `arq app.queues.cv_analysis.tasks.WorkerSettings`
(arq's own CLI already handles SIGTERM/SIGINT gracefully; this module exists
so the two are equivalent and Docker's CMD can use either).
"""

from __future__ import annotations

from arq import run_worker

from app.logging import get_logger
from app.queues.cv_analysis.tasks import WorkerSettings
from app.settings import settings  # noqa: F401 - importing triggers eager env validation

logger = get_logger(__name__)


def main() -> None:
    logger.info("openats cv-analysis worker starting")
    run_worker(WorkerSettings)


if __name__ == "__main__":
    main()
