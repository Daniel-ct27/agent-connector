# Agent Connector

Multi-agent incident analysis over **gRPC** and **HTTP/JSON**.

Agents:

- **Severity** — flag level and score
- **Log Analysis** — error patterns and likely cause
- **Runbook** — troubleshooting steps

The demo panel has two steps: build an agentic incident **package**, then race **delivery** of that same workload over gRPC vs HTTP.

## Setup

Python 3.11+.

```bash
python -m venv .venv
```

Windows:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

macOS / Linux:

```bash
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Optional LLM extras: `python -m pip install -e ".[llm]"`.

## Demo panel

```bash
agent-connector-demo
```

Open http://127.0.0.1:8090/

| Page | URL |
|---|---|
| Paddock | `/` |
| Package | `/response` |
| Delivery | `/lab` |

On Delivery, use **Arm gRPC** / **Arm HTTP** to start the local agent processes, then drop the flag to compare wall times. Package runs are in-process and do not need those servers.

## Agent servers

Needed for CLI fan-out, benchmarks, and the Delivery race (or start them from the panel).

```bash
# gRPC — :50051 :50052 :50053
python -m agent_connector.servers.severity
python -m agent_connector.servers.runbook
python -m agent_connector.servers.log_analysis

# HTTP — :8001 :8002 :8003
python -m agent_connector.servers.http_severity
python -m agent_connector.servers.http_runbook
python -m agent_connector.servers.http_log_analysis
```

## CLI

```bash
agent-connector scenarios/fixtures/inc-db-001.json
agent-connector --transport grpc-unary scenarios/fixtures/inc-db-001.json
agent-connector --transport http-unary scenarios/fixtures/inc-db-001.json
agent-connector --transport agentic scenarios/fixtures/inc-db-001.json
```

Default transport is `grpc-stream`. Use `--no-jsonl` to skip `logs/orchestrator.jsonl`. Exit `0` only when every agent returns `OK`.

### Planners (agentic)

| Planner | Env |
|---|---|
| `deterministic` (default) | none |
| `openai` | `OPENAI_API_KEY` |
| `cloudflare` | `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` |
| `http` | `AGENT_CONNECTOR_PLANNER_URL` |

```bash
agent-connector --transport agentic --planner openai scenarios/fixtures/inc-db-001.json
agent-connector --transport agentic --planner cloudflare scenarios/fixtures/inc-db-001.json
```

Live planner failure falls back to deterministic and sets `planner_degraded` (exit `1`).

### Log Analysis LLM (optional)

```text
AGENT_CONNECTOR_ANALYZER=openai
OPENAI_API_KEY=...
```

Keep deterministic for timed runs.

## Benchmarks

Start agent servers first, then:

```bash
agent-connector-benchmark --generate-fixtures --summarize
agent-connector-benchmark --payload-sizes 100 --concurrency 1 --warmup 0 --trials 2 --summarize
```

Results under `benchmarks/results/<run_id>/`.

## Tests

```bash
python -m pytest -q
```

## Protobuf

```bash
python -m grpc_tools.protoc -Iagent_connector/generated=proto --python_out=src --pyi_out=src --grpc_python_out=src proto/incident.proto
```

Or `make proto`. Do not hand-edit `src/agent_connector/generated/`.

## Layout

```text
proto/                         contracts
scenarios/fixtures/            sample incidents
src/agent_connector/agents/    agent logic
src/agent_connector/agentic/   planner loop
src/agent_connector/servers/   gRPC / HTTP / demo panel
src/agent_connector/orchestrator/
src/agent_connector/benchmarks/
src/agent_connector/demo/      UI
report/                        evaluation + demo notes
tests/
```
