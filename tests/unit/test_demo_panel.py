"""Unit tests for the optional demo control panel."""

from __future__ import annotations

from fastapi.testclient import TestClient

from agent_connector.demo.panel import create_demo_app
from agent_connector.demo.process_manager import SERVERS, ProcessManager


def test_process_manager_lists_six_servers() -> None:
    status = ProcessManager().status()
    assert len(status) == 6
    assert {item["key"] for item in status} == {spec.key for spec in SERVERS}
    assert all(item["running"] is False for item in status)


def test_demo_panel_servers_endpoint() -> None:
    client = TestClient(create_demo_app())
    response = client.get("/api/servers")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["servers"]) == 6


def test_demo_panel_index_and_fixtures() -> None:
    client = TestClient(create_demo_app())
    index = client.get("/")
    assert index.status_code == 200
    assert "Agent Connector" in index.text
    assert "chart.js" in index.text.lower()
    assert "Scored evidence" in index.text
    assert "chart-live" in index.text
    assert "after every run" in index.text
    assert "#cfef3a" in index.text
    assert "Agent<br />Connector" in index.text
    fixtures = client.get("/api/fixtures")
    assert fixtures.status_code == 200
    assert "inc-db-001.json" in fixtures.json()["fixtures"]


def test_demo_panel_summary_charts() -> None:
    client = TestClient(create_demo_app())
    response = client.get("/api/summary")
    assert response.status_code == 200
    payload = response.json()
    assert "charts" in payload
    if payload["rows"]:
        charts = payload["charts"]
        assert charts["latency"]["labels"]
        assert len(charts["latency"]["grpc"]) == len(charts["latency"]["labels"])
        assert charts["throughput"]["labels"]
        assert charts["ttfe"]["labels"]
