# Agent Connector

Agent Connector is a local incident triage demo and protocol benchmark. It
takes a batch of service logs and produces a report with a severity score,
likely cause, and recommended runbook. It also measures how long the same
incident workload takes over **gRPC** and **HTTP/JSON**.

## Highlights

- **Package** builds the incident report in one process and shows which tools
  the planner called and what evidence they found.
- **Delivery** runs the same workload through local gRPC and HTTP services and
  displays side-by-side timings. A separate gRPC streaming run shows how soon
  the first result arrives.
- **Sample workloads** cover a database connection failure, a payment retry
  storm, and an expired TLS certificate. You can also generate logs at
  different sizes to explore how payload size affects timing.

## Deterministic mode and optional AI

The demo starts in **deterministic mode**, which uses built-in rules and
requires no model or API keys. The planner decides which tools to call, and
the tools score severity from signals such as error counts and affected
services, match log patterns to known causes, and recommend an existing
runbook. The same logs and settings produce the same findings. Measured
timings can vary.

[Cloudflare Workers AI](#optional-use-cloudflare-workers-ai) can take over
the planning step on the Package page. The local tools still build the report.

## Quick start

### 1. Get the code

Install Git and Python **3.11+**. You’ll need internet access to clone the
repository and install dependencies. Run these commands in a terminal:

```text
git clone https://github.com/Daniel-ct27/agent-connector.git
cd agent-connector
```

### 2. Install (one time)

**Windows PowerShell**

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

**macOS / Linux**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

### 3. Run the demo

**Windows PowerShell**

```powershell
.\.venv\Scripts\agent-connector-demo.exe
```

**macOS / Linux**

```bash
.venv/bin/agent-connector-demo
```

Open **http://127.0.0.1:8090** in your browser. On **Package**, set
**Strategist** to **deterministic (offline)**, select `inc-db-001.json` under
**Fixture**, and click **Drop the flag**. Expect **MEDIUM (37/100)**, a database
connection failure on `orders-db`, and a database runbook.

Stop the demo with `Ctrl+C` in that terminal.

For the optional terminal commands below, activate the virtual environment
with `.\.venv\Scripts\Activate.ps1` in PowerShell or `source .venv/bin/activate`
in Bash or Zsh. If PowerShell blocks activation, run the command by its full
path in `.venv\Scripts`, as shown above.

## How to use the UI

The demo has three pages. Use them in order the first time.

### Paddock (`/`)

Landing page. Pick **Package** or **Delivery**.

### 1 · Package (`/response`) — no servers needed

Builds the agent result in-process (severity + cause + runbook).

1. Leave **Strategist** on **deterministic (offline)**.
2. Pick a saved fixture (e.g. `inc-db-001.json`) or generated logs.
3. Run / drop the flag.
4. Watch the observe → decide → act steps, then the result cards.
5. Click **Race delivery →** when you want to time the same work over the wire.

### 2 · Delivery (`/lab`) — starts local agent processes

Times the same workload on gRPC vs HTTP. The page loads its chart library
from a CDN.

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

## Optional: use Cloudflare Workers AI

Cloudflare Workers AI can choose which local tools to call on the **Package**
page. The tools still use built-in rules to analyze logs, score severity, and
match runbooks. Delivery uses the deterministic analyzer by default.

After completing the quick start, stop the running demo with `Ctrl+C`. Have
your Cloudflare account ID and an API token authorized to run Workers AI on
that account ready. Enter them in the terminal that starts the demo. The base
installation includes the dependencies for the Cloudflare planner.

**Windows PowerShell**

```powershell
$env:CLOUDFLARE_ACCOUNT_ID = Read-Host "Cloudflare account ID"
$token = Read-Host "Cloudflare API token" -AsSecureString
$env:CLOUDFLARE_API_TOKEN = [System.Net.NetworkCredential]::new('', $token).Password
.\.venv\Scripts\agent-connector-demo.exe
```

**macOS / Linux**

```bash
read -r -p 'Cloudflare account ID: ' CLOUDFLARE_ACCOUNT_ID
read -rs -p 'Cloudflare API token: ' CLOUDFLARE_API_TOKEN
printf '\n'
export CLOUDFLARE_ACCOUNT_ID CLOUDFLARE_API_TOKEN
.venv/bin/agent-connector-demo
```

Open **Package**, set **Strategist** to **cloudflare Workers AI**, select
`inc-db-001.json`, and click **Drop the flag**. If the run shows **degraded**,
check the step feed for the provider error and the deterministic fallback.

To try the same planner in the CLI, use a terminal with the virtual
environment active and both Cloudflare variables set:

```text
agent-connector --transport agentic --planner cloudflare --no-jsonl scenarios/fixtures/inc-db-001.json
```

## Optional: benchmarks and tests

Install the development dependencies with `python -m pip install -e ".[dev]"`
in the active virtual environment.

For the benchmark, start all six agents first with the Delivery **Arm** buttons
or the manual commands above.

```powershell
agent-connector-benchmark --payload-sizes 100 --concurrency 1 --warmup 0 --trials 2 --summarize
```

Run the tests separately. The integration tests start their own services.

```powershell
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
