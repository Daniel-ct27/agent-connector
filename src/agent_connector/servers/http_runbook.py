"""Runbook Agent HTTP process (default 127.0.0.1:8002)."""

from __future__ import annotations

from agent_connector.config import DEFAULT_HTTP_HOST, RUNBOOK_HTTP_PORT
from agent_connector.http_services.runbook import create_runbook_app
from agent_connector.servers.http_runtime import run_http_agent_process


def main() -> None:
    run_http_agent_process(
        create_runbook_app,
        service_name="Runbook Agent (HTTP)",
        host=DEFAULT_HTTP_HOST,
        port=RUNBOOK_HTTP_PORT,
    )


if __name__ == "__main__":
    main()
