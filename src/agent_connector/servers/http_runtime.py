"""Shared Uvicorn runner for independently launched HTTP agent processes."""

from __future__ import annotations

from collections.abc import Callable
import logging

import uvicorn
from fastapi import FastAPI

from agent_connector.analyzers.base import AnalyzerConfigError
from agent_connector.config import DEFAULT_HTTP_HOST

LOGGER = logging.getLogger(__name__)
AppFactory = Callable[[], FastAPI]


def run_http_agent_process(
    create_app: AppFactory,
    *,
    service_name: str,
    host: str = DEFAULT_HTTP_HOST,
    port: int,
) -> None:
    """Process entry helper used by the three HTTP agent server modules."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        app = create_app()
    except AnalyzerConfigError as error:
        LOGGER.error("%s configuration error: %s", service_name, error)
        raise SystemExit(1) from error

    LOGGER.info("%s listening on http://%s:%s", service_name, host, port)
    try:
        uvicorn.run(app, host=host, port=port, log_level="info")
    except KeyboardInterrupt:
        LOGGER.info("%s shut down", service_name)
        raise SystemExit(0) from None
