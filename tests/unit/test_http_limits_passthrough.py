"""HTTP max-body middleware should not buffer declared under-limit bodies."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from agent_connector.http_services.limits import MaxBodySizeMiddleware


def test_content_length_under_limit_is_passed_through() -> None:
    app = FastAPI()
    app.add_middleware(MaxBodySizeMiddleware, max_bytes=1024)

    @app.post("/echo")
    async def echo(request: Request) -> dict:
        body = await request.body()
        return {"n": len(body)}

    client = TestClient(app)
    payload = b'{"ok":true}'
    response = client.post(
        "/echo",
        content=payload,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json() == {"n": len(payload)}
