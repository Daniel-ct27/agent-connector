"""FastAPI adapter for the Log Analysis Agent."""

from __future__ import annotations

from collections.abc import Callable
import logging

from fastapi import FastAPI

from agent_connector.agents.log_analysis import analyze_logs
from agent_connector.domain.models import IncidentRequest, LogAnalysisResult
from agent_connector.http_services.limits import install_http_error_mapping
from agent_connector.http_services.unary import execute_http_unary


LOGGER = logging.getLogger(__name__)
LogAnalyzer = Callable[[IncidentRequest], LogAnalysisResult]


def create_log_analysis_app(analyzer: LogAnalyzer = analyze_logs) -> FastAPI:
    """Build the Log Analysis unary HTTP app."""
    app = FastAPI(title="Log Analysis Agent")
    install_http_error_mapping(app)

    @app.post("/v1/log-analysis/analyze", response_model=LogAnalysisResult)
    async def analyze(request: IncidentRequest) -> LogAnalysisResult:
        return await execute_http_unary(
            request,
            agent_name="Log Analysis Agent",
            analyzer=analyzer,
            logger=LOGGER,
        )

    return app
