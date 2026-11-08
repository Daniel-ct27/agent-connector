"""Log Analysis Agent HTTP process (default 127.0.0.1:8003)."""

from __future__ import annotations

import logging

from agent_connector.agents.log_analysis import analyze_logs
from agent_connector.analyzers import build_analyzer
from agent_connector.config import DEFAULT_HTTP_HOST, LOG_ANALYSIS_HTTP_PORT
from agent_connector.domain.models import IncidentRequest
from agent_connector.http_services.log_analysis import create_log_analysis_app
from agent_connector.servers.http_runtime import run_http_agent_process

_LOG = logging.getLogger(__name__)


def create_app():
    analyzer = build_analyzer()
    _LOG.info("Log Analysis (HTTP) using analyzer=%s", analyzer.name)

    def unary(request: IncidentRequest):
        return analyze_logs(request, analyzer=analyzer)

    return create_log_analysis_app(unary)


def main() -> None:
    run_http_agent_process(
        create_app,
        service_name="Log Analysis Agent (HTTP)",
        host=DEFAULT_HTTP_HOST,
        port=LOG_ANALYSIS_HTTP_PORT,
    )


if __name__ == "__main__":
    main()
