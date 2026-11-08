"""Start/stop local agent processes for the demo control panel."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class ServerSpec:
    key: str
    label: str
    module: str
    kind: str  # grpc | http
    port: int


SERVERS: tuple[ServerSpec, ...] = (
    ServerSpec("severity-grpc", "Severity gRPC", "agent_connector.servers.severity", "grpc", 50051),
    ServerSpec("runbook-grpc", "Runbook gRPC", "agent_connector.servers.runbook", "grpc", 50052),
    ServerSpec(
        "log-grpc",
        "Log Analysis gRPC",
        "agent_connector.servers.log_analysis",
        "grpc",
        50053,
    ),
    ServerSpec(
        "severity-http",
        "Severity HTTP",
        "agent_connector.servers.http_severity",
        "http",
        8001,
    ),
    ServerSpec(
        "runbook-http",
        "Runbook HTTP",
        "agent_connector.servers.http_runbook",
        "http",
        8002,
    ),
    ServerSpec(
        "log-http",
        "Log Analysis HTTP",
        "agent_connector.servers.http_log_analysis",
        "http",
        8003,
    ),
)

_SPECS = {item.key: item for item in SERVERS}


class ProcessManager:
    """Track demo agent subprocesses started from the control panel."""

    def __init__(self) -> None:
        self._procs: dict[str, subprocess.Popen[Any]] = {}

    def status(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for spec in SERVERS:
            proc = self._procs.get(spec.key)
            running = proc is not None and proc.poll() is None
            if proc is not None and not running:
                self._procs.pop(spec.key, None)
                proc = None
            rows.append(
                {
                    "key": spec.key,
                    "label": spec.label,
                    "kind": spec.kind,
                    "port": spec.port,
                    "running": running,
                    "pid": None if proc is None else proc.pid,
                }
            )
        return rows

    def start(self, key: str, *, analyzer: str = "deterministic") -> dict[str, Any]:
        spec = _SPECS.get(key)
        if spec is None:
            raise KeyError(f"unknown server: {key}")
        existing = self._procs.get(key)
        if existing is not None and existing.poll() is None:
            return {
                "key": key,
                "running": True,
                "pid": existing.pid,
                "message": "already running",
            }

        env = os.environ.copy()
        env["AGENT_CONNECTOR_ANALYZER"] = analyzer
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        proc = subprocess.Popen(
            [sys.executable, "-m", spec.module],
            cwd=str(REPO_ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        # Brief settle so bind failures surface quickly.
        time.sleep(0.35)
        if proc.poll() is not None:
            raise RuntimeError(
                f"{spec.label} exited immediately (code {proc.returncode}); "
                "is the port already in use?"
            )
        self._procs[key] = proc
        return {"key": key, "running": True, "pid": proc.pid, "message": "started"}

    def stop(self, key: str) -> dict[str, Any]:
        spec = _SPECS.get(key)
        if spec is None:
            raise KeyError(f"unknown server: {key}")
        proc = self._procs.get(key)
        if proc is None or proc.poll() is not None:
            self._procs.pop(key, None)
            return {"key": key, "running": False, "pid": None, "message": "not running"}
        self._terminate(proc)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
        self._procs.pop(key, None)
        return {"key": key, "running": False, "pid": None, "message": "stopped"}

    def start_group(self, kind: str, *, analyzer: str = "deterministic") -> list[dict[str, Any]]:
        started: list[str] = []
        results: list[dict[str, Any]] = []
        try:
            for spec in SERVERS:
                if spec.kind != kind:
                    continue
                result = self.start(spec.key, analyzer=analyzer)
                results.append(result)
                started.append(spec.key)
        except Exception:
            for key in reversed(started):
                self.stop(key)
            raise
        return results

    def stop_group(self, kind: str) -> list[dict[str, Any]]:
        return [self.stop(spec.key) for spec in SERVERS if spec.kind == kind]

    def stop_all(self) -> list[dict[str, Any]]:
        return [self.stop(spec.key) for spec in SERVERS]

    @staticmethod
    def _terminate(proc: subprocess.Popen[Any]) -> None:
        if sys.platform == "win32":
            try:
                proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
                return
            except OSError:
                pass
        proc.terminate()
