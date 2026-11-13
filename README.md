# Agent Connector

Local multi-agent system for analyzing an incident from a batch of logs, then
comparing how fast the same analysis travels over **gRPC** vs **HTTP/JSON**.

Given an incident fixture (JSON with log lines), three agents produce one
combined result:

| Agent | Job | Output |
|---|---|---|
| Severity | Score how bad it looks | Level + score + rationale |
| Log Analysis | Find patterns in the logs | Summary + likely cause |
| Runbook | Match remediation | Ranked troubleshooting steps |

There are two ways those agents get used:

1. **Agentic package** — a planner observes the incident and calls the agent
   tools in-process (`analyze_logs`, `analyze_severity`, `recommend_runbook`,
   `finish`). No network servers required.
2. **Transport delivery** — the same agent work is sent to live gRPC and/or
   HTTP agent processes so you can compare wall-clock delivery time.

The local demo UI walks that sequence: build the package, then race delivery.

## Requirements

- Python 3.11+
- Network only for optional LLM planners / OpenAI log summarizer

## Install

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

macOS / Linux:

```bash
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Optional OpenAI dependency (log analyzer or OpenAI planner):

```bash
python -m pip install -e ".[llm]"
```

After install these commands are available:

| Command | What it runs |
|---|---|
| `agent-connector-demo` | Demo UI on `http://127.0.0.1:8090` |
| `agent-connector` | Orchestrator CLI (one fixture run) |
| `agent-connector-benchmark` | Timed gRPC vs HTTP matrix |
| `agent-connector-severity` | Severity gRPC server |
| `agent-connector-runbook` | Runbook gRPC server |
| `agent-connector-log-analysis` | Log Analysis gRPC server |
| `agent-connector-http-severity` | Severity HTTP server |
| `agent-connector-http-runbook` | Runbook HTTP server |
| `agent-connector-http-log-analysis` | Log Analysis HTTP server |

## Ports

| Stack | Severity | Runbook | Log Analysis |
|---|---|---|---|
| gRPC | `127.0.0.1:50051` | `127.0.0.1:50052` | `127.0.0.1:50053` |
| HTTP | `http://127.0.0.1:8001` | `http://127.0.0.1:8002` | `http://127.0.0.1:8003` |

HTTP routes:

- `POST /v1/severity/analyze`
- `POST /v1/runbook/recommend`
- `POST /v1/log-analysis/analyze`

Demo UI: `http://127.0.0.1:8090`

## Sample fixtures

Under `scenarios/fixtures/`:

| File | Scenario |
|---|---|
| `inc-db-001.json` | Database connection failure |
| `inc-retry-001.json` | Payment retry storm |
| `inc-cert-001.json` | Expired TLS certificate |

## 1. Demo UI (easiest full path)

```bash
agent-connector-demo
```

Open http://127.0.0.1:8090/

| Page | URL | Purpose |
|---|---|---|
| Paddock | `/` | Entry hub |
| Package | `/response` | Agentic loop → severity / cause / runbook |
| Delivery | `/lab` | Same workload timed on gRPC vs HTTP |

### Package page (`/response`)

1. Choose source: generated logs or a saved fixture.
2. Choose planner (`deterministic` needs no API keys).
3. Drop the flag / run.
4. Watch observe → decide → act steps, then the package cards.
5. When ready, use **Race delivery →** to carry source/fixture/payload into the lab.

No agent servers needed for this page.

### Delivery page (`/lab`)

1. Click **Arm gRPC** and **Arm HTTP** (starts all six local agent processes).
2. Confirm garage shows open / warmup (not closed).
3. Set source, fixture or log-line count, concurrency.
4. **Drop the flag** to compare unary gRPC vs HTTP wall time.
5. Optional stream lap for gRPC streaming package time.
6. Charts fill only from laps in this session.

**Kill switch** stops every agent the panel started.

## 2. Agent servers (manual)

Use separate terminals when you are not using the panel buttons.

gRPC:

```bash
python -m agent_connector.servers.severity
python -m agent_connector.servers.runbook
python -m agent_connector.servers.log_analysis
```

HTTP:

```bash
python -m agent_connector.servers.http_severity
python -m agent_connector.servers.http_runbook
python -m agent_connector.servers.http_log_analysis
```

Equivalent console scripts: `agent-connector-severity`, `agent-connector-runbook`,
`agent-connector-log-analysis`, `agent-connector-http-severity`,
`agent-connector-http-runbook`, `agent-connector-http-log-analysis`.

## 3. Orchestrator CLI

Runs one fixture through a chosen transport and prints the combined report.

### Agentic (in-process — servers not required)

```bash
agent-connector --transport agentic scenarios/fixtures/inc-db-001.json
agent-connector --transport agentic --planner deterministic --no-jsonl scenarios/fixtures/inc-db-001.json
```

### Live transports (servers required)

Start the matching gRPC and/or HTTP servers first.

```bash
# Default: mixed gRPC stream demo (Severity + Runbook unary, Log Analysis stream)
agent-connector scenarios/fixtures/inc-db-001.json

agent-connector --transport grpc-stream scenarios/fixtures/inc-db-001.json
agent-connector --transport grpc-unary scenarios/fixtures/inc-db-001.json
agent-connector --transport http-unary scenarios/fixtures/inc-db-001.json
```

Useful flags:

```bash
agent-connector --no-jsonl scenarios/fixtures/inc-db-001.json
agent-connector --jsonl logs/my-run.jsonl scenarios/fixtures/inc-db-001.json
agent-connector --unary-deadline 2 --stream-deadline 10 scenarios/fixtures/inc-db-001.json
agent-connector --severity-target 127.0.0.1:50051 --runbook-target 127.0.0.1:50052 --log-analysis-target 127.0.0.1:50053 scenarios/fixtures/inc-db-001.json
```

For HTTP targets pass base URLs, e.g. `http://127.0.0.1:8001`.

Behavior:

- Default JSONL log path: `logs/orchestrator.jsonl`
- Exit `0` only when every agent returns `OK`
- Partial failure (one agent down) → report marks `partial`, exit `1`

### Planners (`--transport agentic`)

| `--planner` | Required env |
|---|---|
| `deterministic` | none (default) |
| `openai` | `OPENAI_API_KEY` or `AGENT_CONNECTOR_OPENAI_API_KEY` |
| `cloudflare` | `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` |
| `http` | `AGENT_CONNECTOR_PLANNER_URL` (optional `AGENT_CONNECTOR_PLANNER_TOKEN`) |

Optional:

| Env | Role |
|---|---|
| `AGENT_CONNECTOR_PLANNER` | Default planner name |
| `AGENT_CONNECTOR_PLANNER_MODEL` | Model override |
| `AGENT_CONNECTOR_PLANNER_TIMEOUT_SECONDS` | Planner timeout (default 8) |
| `OPENAI_BASE_URL` | OpenAI-compatible base URL |

If a live planner fails, the run falls back to deterministic rules and sets
`planner_degraded` (exit `1`).

Cloudflare example (PowerShell):

```powershell
$env:CLOUDFLARE_ACCOUNT_ID = Read-Host 'Cloudflare account ID'
$env:CLOUDFLARE_API_TOKEN = Read-Host 'Workers AI API token' -MaskInput
agent-connector --transport agentic --planner cloudflare --no-jsonl scenarios/fixtures/inc-db-001.json
```

Start `agent-connector-demo` from the same shell if you want the Package page
planner dropdown to see those env vars.

## 4. Log Analysis summarizer

Affects the Log Analysis agent (CLI/servers/Delivery), not the agentic planner.

| Mode | Env |
|---|---|
| Deterministic (default) | none — use this for timed races |
| OpenAI | `AGENT_CONNECTOR_ANALYZER=openai` plus `OPENAI_API_KEY` |

Optional: `AGENT_CONNECTOR_LLM_MODEL` (default `gpt-4o-mini`),
`AGENT_CONNECTOR_LLM_TIMEOUT_SECONDS` (default `8`).

Set these **before** starting Log Analysis processes (or before Arm in the lab).

## 5. Benchmarks

Measures gRPC unary, HTTP unary, and gRPC stream against already-running local
agents. Start all six servers first (panel Arm buttons or manual terminals).

Full matrix:

```bash
agent-connector-benchmark --generate-fixtures --summarize
```

Defaults: payload sizes `100 1000 5000`, concurrency `1 5 10`, warmup `3`,
timed trials `30`.

Smoke run:

```bash
agent-connector-benchmark --payload-sizes 100 --concurrency 1 --warmup 0 --trials 2 --summarize
```

Skip cells:

```bash
agent-connector-benchmark --skip-grpc-stream --summarize
agent-connector-benchmark --skip-http-unary --skip-grpc-unary --summarize
```

Aggregate an existing file only:

```bash
agent-connector-benchmark --summary-only benchmarks/results/<run_id>/trials.csv
```

Outputs under `benchmarks/results/<run_id>/`:

- `trials.csv`
- `summary.csv` (with `--summarize`)
- charts (with `--summarize`)

`--generate-fixtures` also writes generated payloads under `scenarios/generated/`.

## 6. Tests

```bash
python -m pytest -q
```

Or `make test`.

Unit tests cover agents, CLI, analyzers, demo panel helpers. Integration tests
spin local servers where needed.

## 7. Regenerate protobuf

After editing `proto/incident.proto`:

```bash
python -m grpc_tools.protoc -Iagent_connector/generated=proto --python_out=src --pyi_out=src --grpc_python_out=src proto/incident.proto
```

Or `make proto` / `bash scripts/generate_proto.sh`.

Do not hand-edit `src/agent_connector/generated/`.

## Repo layout

```text
proto/                              gRPC / protobuf contracts
scenarios/fixtures/                 checked-in incident JSON
scenarios/generated/                benchmark-generated payloads (optional)
src/agent_connector/
  agents/                           severity, runbook, log analysis logic
  agentic/                          planner loop + tools (package path)
  analyzers/                        deterministic / OpenAI log summarizers
  servers/                          gRPC, HTTP, and demo panel processes
  orchestrator/                     CLI fan-out over live agents
  benchmarks/                       timed matrix runner
  demo/                             UI static files + process manager
  domain/                           shared models
  generated/                        protobuf stubs (generated)
report/                             evaluation notes, demo script, slides data
tests/                              unit + integration
```

Extra walkthrough notes live in `report/DEMO.md`. Evaluation write-up:
`report/EVALUATION.md`.
