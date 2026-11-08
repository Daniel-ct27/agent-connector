"""Severity Agent HTTP process (default 127.0.0.1:8001)."""

from __future__ import annotations

from agent_connector.config import DEFAULT_HTTP_HOST, SEVERITY_HTTP_PORT
from agent_connector.http_services.severity import create_severity_app
from agent_connector.servers.http_runtime import run_http_agent_process


def main() -> None:
    run_http_agent_process(
        create_severity_app,
        service_name="Severity Agent (HTTP)",
        host=DEFAULT_HTTP_HOST,
        port=SEVERITY_HTTP_PORT,
    )


if __name__ == "__main__":
    main()
