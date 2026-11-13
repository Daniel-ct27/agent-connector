"""Demo control panel process (default http://127.0.0.1:8090)."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import uvicorn

from agent_connector.config import (
    CLOUDFLARE_ACCOUNT_ID_ENV_VAR,
    CLOUDFLARE_API_TOKEN_ENV_VAR,
    DEFAULT_HTTP_HOST,
    DEMO_PANEL_PORT,
)
from agent_connector.demo.panel import create_demo_app

_SECRET_KEYS = (CLOUDFLARE_ACCOUNT_ID_ENV_VAR, CLOUDFLARE_API_TOKEN_ENV_VAR)


def _load_local_cloudflare_secrets() -> None:
    """Fill missing Cloudflare env vars from the user-local secrets file."""
    if all(os.getenv(key, "").strip() for key in _SECRET_KEYS):
        return
    local_app = os.getenv("LOCALAPPDATA") or os.getenv("XDG_CONFIG_HOME")
    if not local_app:
        return
    secrets_path = Path(local_app) / "agent-connector" / "secrets" / "cloudflare.env"
    if not secrets_path.is_file():
        return
    try:
        for raw_line in secrets_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key in _SECRET_KEYS and not os.getenv(key, "").strip():
                os.environ[key] = value.strip()
    except OSError:
        logging.getLogger(__name__).warning(
            "Could not read local Cloudflare secrets at %s", secrets_path
        )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _load_local_cloudflare_secrets()
    app = create_demo_app()
    logging.getLogger(__name__).info(
        "Demo panel listening on http://%s:%s",
        DEFAULT_HTTP_HOST,
        DEMO_PANEL_PORT,
    )
    uvicorn.run(app, host=DEFAULT_HTTP_HOST, port=DEMO_PANEL_PORT, log_level="info")



if __name__ == "__main__":
    main()
