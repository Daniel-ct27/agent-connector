"""Demo control panel process (default http://127.0.0.1:8090)."""

from __future__ import annotations

import logging

import uvicorn

from agent_connector.config import DEFAULT_HTTP_HOST, DEMO_PANEL_PORT
from agent_connector.demo.panel import create_demo_app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = create_demo_app()
    logging.getLogger(__name__).info(
        "Demo panel listening on http://%s:%s",
        DEFAULT_HTTP_HOST,
        DEMO_PANEL_PORT,
    )
    uvicorn.run(app, host=DEFAULT_HTTP_HOST, port=DEMO_PANEL_PORT, log_level="info")



if __name__ == "__main__":
    main()
