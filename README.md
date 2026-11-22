# Agent Connector

Turn a batch of incident logs into a severity score, likely cause, and
runbook — then compare how fast that same result arrives over **gRPC** vs
**HTTP/JSON**.

You do not need API keys for the default path.

## Quick start

### 1. Requirements

- Python **3.11+**
- A terminal in this repo folder

### 2. Install (one time)

**Windows PowerShell**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Keep the venv activated for the steps below (`(.venv)` in your prompt).

### 3. Run the demo

```powershell
agent-connector-demo
```

Open **http://127.0.0.1:8090**

Stop the demo with `Ctrl+C` in that terminal.

## How to use the UI

The demo has three pages. Use them in order the first time.

### Paddock (`/`)

Landing page. Pick **Package** or **Delivery**.

### 1 · Package (`/response`) — no servers needed

Builds the agent result in-process (severity + cause + runbook).

1. Leave **planner** on `deterministic` (no API keys).
2. Pick a saved fixture (e.g. `inc-db-001.json`) or generated logs.
3. Run / drop the flag.
4. Watch the observe → decide → act steps, then the result cards.
5. Click **Race delivery →** when you want to time the same work over the wire.

### 2 · Delivery (`/lab`) — starts local agent processes

Times the same workload on gRPC vs HTTP.

1. Click **Arm gRPC** and **Arm HTTP** (starts the six local agent servers).
2. Wait until the garage shows open / ready (not closed).
3. Keep the fixture/payload from the handoff, or set your own.
4. **Drop the flag** to race unary gRPC vs HTTP.
5. Optional: run a stream lap for gRPC streaming time.
6. Scroll for charts and the lap log.

**Kill switch** stops every agent process the panel started.

## What you should see

| After… | Success looks like |
|---|---|
| `agent-connector-demo` | Terminal says the panel is listening; browser loads the paddock |
| Package run | Step feed fills; severity / logs / runbook cards populate |
| Arm on Delivery | Garage status leaves “closed”; agents show on track |
| Drop the flag | Two lane times (gRPC + HTTP), a verdict, and a lap-log row |

## Sample incidents

Fixtures live in `scenarios/fixtures/`:

| File | Scenario |
|---|---|
| `inc-db-001.json` | Database connection failure |
| `inc-retry-001.json` | Payment retry storm |
| `inc-cert-001.json` | Expired TLS certificate |

## Optional: CLI instead of the UI

Same install. Servers are **not** required for the agentic transport:

```powershell
agent-connector --transport agentic --planner deterministic --no-jsonl scenarios/fixtures/inc-db-001.json
```

Live transports need the agent servers running (use **Arm** in the UI, or start them manually — see below).

```powershell
agent-connector --transport grpc-unary scenarios/fixtures/inc-db-001.json --no-jsonl
agent-connector --transport http-unary scenarios/fixtures/inc-db-001.json --no-jsonl
```

## Optional: start agent servers yourself

Only needed if you skip the Delivery **Arm** buttons.

gRPC (three terminals):

```powershell
python -m agent_connector.servers.severity
python -m agent_connector.servers.runbook
python -m agent_connector.servers.log_analysis
```

HTTP (three terminals):

```powershell
python -m agent_connector.servers.http_severity
python -m agent_connector.servers.http_runbook
python -m agent_connector.servers.http_log_analysis
```

| Stack | Severity | Runbook | Log Analysis |
|---|---|---|---|
| gRPC | `127.0.0.1:50051` | `127.0.0.1:50052` | `127.0.0.1:50053` |
| HTTP | `http://127.0.0.1:8001` | `http://127.0.0.1:8002` | `http://127.0.0.1:8003` |

## Optional: LLM features

Default mode is deterministic (offline). For OpenAI log summarizer or planners:

```powershell
python -m pip install -e ".[llm]"
```

| Feature | Env |
|---|---|
| OpenAI log analyzer | `AGENT_CONNECTOR_ANALYZER=openai` + `OPENAI_API_KEY` |
| OpenAI planner | `--planner openai` + `OPENAI_API_KEY` |
| Cloudflare planner | `--planner cloudflare` + `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` |

Set analyzer env vars **before** Arm / starting Log Analysis servers. For timed races, keep the deterministic analyzer.

## Optional: benchmarks and tests

Start all six agents first (UI Arm or manual terminals).

```powershell
agent-connector-benchmark --payload-sizes 100 --concurrency 1 --warmup 0 --trials 2 --summarize
python -m pytest -q
```

## Commands reference

| Command | What it does |
|---|---|
| `agent-connector-demo` | Demo UI at http://127.0.0.1:8090 |
| `agent-connector` | One fixture through a chosen transport |
| `agent-connector-benchmark` | Timed gRPC vs HTTP matrix |
| `agent-connector-severity` / `runbook` / `log-analysis` | gRPC agent servers |
| `agent-connector-http-*` | HTTP agent servers |

## Repo layout

```text
scenarios/fixtures/     sample incident JSON
src/agent_connector/
  agents/               severity, runbook, log analysis
  agentic/              in-process planner loop (Package page)
  servers/              gRPC, HTTP, demo panel
  orchestrator/         CLI
  benchmarks/           timing matrix
  demo/                 UI
report/                 DEMO.md walkthrough, EVALUATION.md
tests/
```

More demo script notes: `report/DEMO.md`.
