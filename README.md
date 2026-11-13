# Agent Connector

Local multi-agent incident analysis over **gRPC** and **HTTP/JSON**.

Three agents take the same incident request:

- **Severity** — score and level
- **Runbook** — troubleshooting steps
- **Log Analysis** — error patterns and a likely cause (unary or gRPC stream)

## Setup

Python 3.11+.

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS / Linux:

```bash
source .venv/bin/activate
```

```bash
python -m pip install -e ".[dev]"
```

Optional OpenAI summarizer for Log Analysis demos:

```bash
python -m pip install -e ".[llm]"
```

## Demo panel

Starts a local UI to manage agent processes, race gRPC vs HTTP, and view charts:

```bash
agent-connector-demo
```

Open [http://127.0.0.1:8090](http://127.0.0.1:8090).

## Agent processes

### gRPC

| Agent | Address |
|---|---|
| Severity | `127.0.0.1:50051` |
| Runbook | `127.0.0.1:50052` |
| Log Analysis | `127.0.0.1:50053` |

```bash
python -m agent_connector.servers.severity
python -m agent_connector.servers.runbook
python -m agent_connector.servers.log_analysis
```

### HTTP

| Agent | Address | Route |
|---|---|---|
| Severity | `http://127.0.0.1:8001` | `POST /v1/severity/analyze` |
| Runbook | `http://127.0.0.1:8002` | `POST /v1/runbook/recommend` |
| Log Analysis | `http://127.0.0.1:8003` | `POST /v1/log-analysis/analyze` |

```bash
python -m agent_connector.servers.http_severity
python -m agent_connector.servers.http_runbook
python -m agent_connector.servers.http_log_analysis
```

Console scripts (`agent-connector-severity`, `agent-connector-http-severity`, …) are available after install.

## Orchestrator CLI

```bash
agent-connector scenarios/fixtures/inc-db-001.json
agent-connector --transport grpc-unary scenarios/fixtures/inc-db-001.json
agent-connector --transport http-unary scenarios/fixtures/inc-db-001.json
```

Default transport is `grpc-stream`. Call records append to `logs/orchestrator.jsonl` unless you pass `--no-jsonl`. Exit `0` only when every agent returns `OK`.

### Agentic response path (LLM-agnostic)

Planner inspects logs, then chooses tools (`analyze_logs`, `analyze_severity`,
`recommend_runbook`, `finish`). Formal gRPC/HTTP benchmarks stay on fan-out.

```bash
agent-connector --transport agentic scenarios/fixtures/inc-db-001.json
agent-connector --transport agentic --planner openai scenarios/fixtures/inc-db-001.json
agent-connector --transport agentic --planner cloudflare scenarios/fixtures/inc-db-001.json
```

| Planner | Env |
|---|---|
| `deterministic` (default) | none |
| `openai` | `OPENAI_API_KEY`, optional `OPENAI_BASE_URL`, `AGENT_CONNECTOR_PLANNER_MODEL` |
| `cloudflare` | `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, optional model |
| `http` | `AGENT_CONNECTOR_PLANNER_URL`, optional `AGENT_CONNECTOR_PLANNER_TOKEN` |

Optional: `AGENT_CONNECTOR_PLANNER`, `AGENT_CONNECTOR_PLANNER_TIMEOUT_SECONDS`.

Agentic tools run **in-process** (no gRPC/HTTP agent servers required). If a live
planner fails, the run falls back to deterministic rules and marks
`planner_degraded` / `agentic_mode=<provider>+fallback` (exit code `1`).

In the demo panel, use **Run agentic response** for the step timeline. The
timeline renders after the run completes.

### Connect Cloudflare Workers AI locally

In the Cloudflare dashboard, open Workers AI → Use REST API and create a
Workers AI API token. Copy the account ID from the same screen. Set both in
the PowerShell session that will launch Agent Connector:

```powershell
$env:CLOUDFLARE_ACCOUNT_ID = Read-Host 'Cloudflare account ID'
$env:CLOUDFLARE_API_TOKEN = Read-Host 'Workers AI API token' -MaskInput
agent-connector --transport agentic --planner cloudflare --no-jsonl scenarios/fixtures/inc-db-001.json
```

`-MaskInput` requires PowerShell 7.2 or newer. A successful live fixture run
exits `0` without planner degradation. Start `agent-connector-demo` from the
same shell and choose **cloudflare Workers AI** in the planner selector to run
it from the panel. The token stays in the backend process environment.

## Log Analysis mode

Default summarizer is deterministic. For a live OpenAI call, set these **before** starting Log Analysis:

```text
AGENT_CONNECTOR_ANALYZER=openai
OPENAI_API_KEY=...
```

Optional: `AGENT_CONNECTOR_LLM_MODEL` (default `gpt-4o-mini`), `AGENT_CONNECTOR_LLM_TIMEOUT_SECONDS` (default `8`).

Keep the deterministic analyzer for benchmark runs.

## Benchmarks

Start the agent processes first, then:

```bash
agent-connector-benchmark --generate-fixtures --summarize
```

Smoke cell:

```bash
agent-connector-benchmark --payload-sizes 100 --concurrency 1 --warmup 0 --trials 2 --summarize
```

Outputs land under `benchmarks/results/<run_id>/` (`trials.csv`, `summary.csv`, charts).

## Tests

```bash
python -m pytest -q
```

## Protobuf

After editing `proto/incident.proto`:

```bash
python -m grpc_tools.protoc -Iagent_connector/generated=proto --python_out=src --pyi_out=src --grpc_python_out=src proto/incident.proto
```

Or `bash scripts/generate_proto.sh` / `make proto`. Do not hand-edit `src/agent_connector/generated/`.

## Layout

```text
proto/                         Service contracts
scenarios/fixtures/            Sample incidents
src/agent_connector/agents/    Agent logic
src/agent_connector/servers/   gRPC and HTTP processes
src/agent_connector/orchestrator/
src/agent_connector/benchmarks/
src/agent_connector/demo/      Local demo panel
report/                        Evaluation, demo script, presentation, charts
tests/
```

## Report materials

Under `report/`: `EVALUATION.md`, `DEMO.md`, `PRESENTATION.md`, `summary.csv`, and `charts/`.
