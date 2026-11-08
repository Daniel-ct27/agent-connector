# Live CLI Demonstration Script (~8–10 minutes)

Prereqs: Python 3.11+, venv, `pip install -e ".[dev]"`.

## 1. Setup (30s)

```powershell
.\.venv\Scripts\Activate.ps1
$env:AGENT_CONNECTOR_ANALYZER = "deterministic"
```

## 2. Start agents (1 min)

Three gRPC terminals:

```powershell
python -m agent_connector.servers.severity
python -m agent_connector.servers.runbook
python -m agent_connector.servers.log_analysis
```

Three HTTP terminals:

```powershell
python -m agent_connector.servers.http_severity
python -m agent_connector.servers.http_runbook
python -m agent_connector.servers.http_log_analysis
```

## 3. Happy-path stream demo (2 min)

```powershell
agent-connector scenarios/fixtures/inc-db-001.json --no-jsonl
```

Point out: stream events print as they arrive; final combined report; exit 0.

## 4. Unary transport comparison (2 min)

```powershell
agent-connector --transport grpc-unary scenarios/fixtures/inc-db-001.json --no-jsonl
agent-connector --transport http-unary scenarios/fixtures/inc-db-001.json --no-jsonl
```

Point out: same incident, same agent statuses, different transport path.

## 5. Partial failure (2 min)

Stop Log Analysis gRPC (`Ctrl+C` on port 50053), then:

```powershell
agent-connector scenarios/fixtures/inc-db-001.json --no-jsonl
```

Point out: Severity/Runbook still present, Log Analysis `UNAVAILABLE`,
`partial=true`, exit 1. Restart Log Analysis afterward.

## 6. Point to scored evidence (1–2 min)

Open `report/EVALUATION.md` and `report/charts/`:

- Unary latency chart: gRPC vs HTTP
- Stream TTFE chart: early updates on long Log Analysis

Close by restating both research answers and the localhost limitation.
