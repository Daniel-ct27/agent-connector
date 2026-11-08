"""FastAPI adapter for the Severity Agent."""

from __future__ import annotations

from collections.abc import Callable
import logging

from fastapi import FastAPI

from agent_connector.agents.severity import analyze_severity
from agent_connector.domain.models import IncidentRequest, SeverityResponse
from agent_connector.http_services.limits import install_http_error_mapping
from agent_connector.http_services.unary import execute_http_unary


LOGGER = logging.getLogger(__name__)
SeverityAnalyzer = Callable[[IncidentRequest], SeverityResponse]


def create_severity_app(analyzer: SeverityAnalyzer = analyze_severity) -> FastAPI:
    """Build the Severity unary HTTP app."""
    app = FastAPI(title="Severity Agent")
    install_http_error_mapping(app)

    @app.post("/v1/severity/analyze", response_model=SeverityResponse)
    async def analyze(request: IncidentRequest) -> SeverityResponse:
        return await execute_http_unary(
            request,
            agent_name="Severity Agent",
            analyzer=analyzer,
            logger=LOGGER,
        )

    return app
