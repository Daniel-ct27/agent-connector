"""Shared HTTP transport limits."""

from __future__ import annotations

import json

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from agent_connector.config import MAX_HTTP_REQUEST_BYTES


class MaxBodySizeMiddleware:
    """Reject requests at or above the project's HTTP byte ceiling.

    When ``Content-Length`` is present and under the ceiling, the request is
    passed through without buffering so fair unary comparisons are not slowed
    by an extra full-body copy. Chunked / missing-length bodies are still
    streamed with a hard cap.
    """

    def __init__(self, app: ASGIApp, max_bytes: int = MAX_HTTP_REQUEST_BYTES) -> None:
        self.app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                size = int(content_length)
            except ValueError:
                await self._send_json(
                    send,
                    status_code=400,
                    detail="invalid Content-Length header",
                )
                return
            if size >= self._max_bytes:
                await self._send_json(
                    send,
                    status_code=400,
                    detail=(
                        f"request must be smaller than {self._max_bytes} bytes"
                    ),
                )
                return
            # Trusted declared size under the ceiling: avoid a full buffer/replay
            # that would unfairly penalize the HTTP path vs gRPC.
            await self.app(scope, receive, send)
            return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            chunk = message.get("body", b"")
            if chunk:
                body.extend(chunk)
                if len(body) >= self._max_bytes:
                    await self._send_json(
                        send,
                        status_code=400,
                        detail=(
                            f"request must be smaller than {self._max_bytes} bytes"
                        ),
                    )
                    return
            if not message.get("more_body", False):
                break

        sealed = bytes(body)
        sent = False

        async def replay_receive() -> Message:
            nonlocal sent
            if not sent:
                sent = True
                return {
                    "type": "http.request",
                    "body": sealed,
                    "more_body": False,
                }
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay_receive, send)

    async def _send_json(self, send: Send, *, status_code: int, detail: str) -> None:
        payload = json.dumps({"detail": detail}).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode("latin-1")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": payload})


def install_request_limits(app: FastAPI) -> None:
    """Attach the shared max-body middleware to an agent app."""
    app.add_middleware(MaxBodySizeMiddleware)


def map_validation_errors_to_400(app: FastAPI) -> None:
    """Map FastAPI/Pydantic request validation failures to HTTP 400."""

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        detail = _first_validation_message(exc)
        return JSONResponse(status_code=400, content={"detail": detail})


def _first_validation_message(exc: RequestValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "invalid request"
    first = errors[0]
    loc = ".".join(str(part) for part in first.get("loc", ()) if part != "body")
    msg = first.get("msg", "invalid request")
    if loc:
        return f"{loc}: {msg}"
    return str(msg)


def install_http_error_mapping(app: FastAPI) -> None:
    """Install shared HTTP error mapping used by all agent apps."""
    install_request_limits(app)
    map_validation_errors_to_400(app)
