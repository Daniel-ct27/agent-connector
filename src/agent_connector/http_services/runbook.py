"""FastAPI adapter for the Runbook Agent."""

from __future__ import annotations

from collections.abc import Callable
import logging

from fastapi import FastAPI

from agent_connector.agents.runbook import recommend_actions
from agent_connector.domain.models import IncidentRequest, RunbookResponse
from agent_connector.http_services.limits import install_http_error_mapping
from agent_connector.http_services.unary import execute_http_unary


LOGGER = logging.getLogger(__name__)
RunbookAnalyzer = Callable[[IncidentRequest], RunbookResponse]


def create_runbook_app(analyzer: RunbookAnalyzer = recommend_actions) -> FastAPI:
    """Build the Runbook unary HTTP app."""
    app = FastAPI(title="Runbook Agent")
    install_http_error_mapping(app)

    @app.post("/v1/runbook/recommend", response_model=RunbookResponse)
    async def recommend(request: IncidentRequest) -> RunbookResponse:
        return await execute_http_unary(
            request,
            agent_name="Runbook Agent",
            analyzer=analyzer,
            logger=LOGGER,
        )

    return app
