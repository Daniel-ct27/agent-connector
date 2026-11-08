# Live CLI Demonstration Script (~10–12 minutes with optional LLM step)

Prereqs: Python 3.11+, venv, `pip install -e ".[dev]"`.

## 1. Setup (30s)

```powershell
.\.venv\Scripts\Activate.ps1
$env:AGENT_CONNECTOR_ANALYZER = "deterministic"
```

Use deterministic for protocol demos and anything timed. The live LLM step is
optional and separate (section 7).

### Option A — Demo panel (recommended)

```powershell
agent-connector-demo
# open http://127.0.0.1:8090
```

Use the page buttons to start gRPC and/or HTTP agents, pick a fixture/transport,
and run. Charts from the scored run are shown on the same page.

## 2. Start agents manually (1 min) — Option B

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

In the demo panel, scroll to **Scored evidence** — interactive Chart.js
plots (hover for exact values) driven by `report/summary.csv`.
PNG exports under `report/charts/` remain for slides / `EVALUATION.md`.

- Unary latency: gRPC vs HTTP vs payload
- Unary throughput: gRPC vs HTTP vs concurrency
- Stream TTFE: time to first event vs payload

## 7. Optional live LLM step (~2 min)

Shows the PDF-required “one lightweight LLM call” inside Log Analysis.
Do **not** use this mode for benchmarks.

```powershell
pip install -e ".[llm]"
# Stop only the Log Analysis processes (gRPC :50053 and HTTP :8003), then:
$env:AGENT_CONNECTOR_ANALYZER = "openai"
$env:OPENAI_API_KEY = "<your-key>"   # or AGENT_CONNECTOR_OPENAI_API_KEY
python -m agent_connector.servers.log_analysis
# optional matching HTTP process:
python -m agent_connector.servers.http_log_analysis
```

Re-run:

```powershell
agent-connector scenarios/fixtures/inc-db-001.json --no-jsonl
```

Point out: local evidence extraction is unchanged; `summary` / `likely_cause`
now come from the live model. If the call fails, evidence is retained and
Log Analysis status is `FAILED` (no silent fallback).

Switch back before any timed work:

```powershell
$env:AGENT_CONNECTOR_ANALYZER = "deterministic"
# restart Log Analysis processes
```

Close by restating both research answers and the localhost limitation.
