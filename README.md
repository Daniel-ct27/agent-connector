# Agent Connector

Agent Connector is a Python project for analyzing simulated software incidents
with three specialized agents:

- **Severity** calculates an incident score and severity level.
- **Runbook** recommends relevant troubleshooting steps.
- **Log Analysis** extracts repeated error patterns and suggests a likely cause.

The current version includes the tested agent logic, generated gRPC contracts,
three independently runnable local gRPC agent processes, matching unary
HTTP/JSON FastAPI processes, a concurrent mixed-workflow orchestrator with a
CLI (`grpc-stream`, `grpc-unary`, or `http-unary`), a Stage 7 benchmark harness
(synthetic fixtures, timed matrix, summary CSV, charts), and a pluggable Log
Analysis summarizer (deterministic by default, optional OpenAI live mode).

## How it currently works

An incident is represented by an `IncidentRequest` containing an identifier, a
scenario name, and log entries from one or more services.

Each agent receives the same request:

```text
IncidentRequest
      |
      +--> Severity Agent ----> score, level, evidence
      |
      +--> Runbook Agent -----> recommended procedures
      |
      `--> Log Analysis ------> evidence, summary, likely cause
```

The agents are ordinary Python functions under `src/agent_connector/agents/`.
This keeps the analysis independent from gRPC and HTTP so both transports can
reuse the same behavior.

Error evidence is grouped by service and normalized message pattern. For
example, `database timeout attempt 1` and `database timeout attempt 2` become
one `database timeout` pattern with a count of two.

## Setup

Python 3.11 or newer is required. A virtual environment is strongly
recommended so this project's protobuf packages do not affect other Python
projects.

Create the environment:

```bash
python -m venv .venv
```

Activate it in Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Activate it on macOS or Linux:

```bash
source .venv/bin/activate
```

Install the project and development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Optional live LLM support for Log Analysis demos:

```bash
python -m pip install -e ".[llm]"
```

## Log Analysis analyzers

After local evidence extraction, Log Analysis calls a pluggable summarizer:

| Mode | Selection | Notes |
|---|---|---|
| Deterministic (default) | `AGENT_CONNECTOR_ANALYZER=deterministic` | Stable fixture/evidence summaries; used for tests and benchmarks |
| OpenAI live | `AGENT_CONNECTOR_ANALYZER=openai` | One Chat Completions call (`gpt-4o-mini` by default) |

Live mode environment variables:

```text
AGENT_CONNECTOR_ANALYZER=openai
OPENAI_API_KEY=...                 # or AGENT_CONNECTOR_OPENAI_API_KEY
AGENT_CONNECTOR_LLM_MODEL=gpt-4o-mini
AGENT_CONNECTOR_LLM_TIMEOUT_SECONDS=8
```

Set these before starting the Log Analysis process. Unary/stream gRPC shapes are
unchanged; a live failure keeps extracted evidence and returns `FAILED`.

## Run the current agent logic

The following PowerShell example loads the database-failure fixture and runs
all three agents:

```powershell
@'
import json
from pathlib import Path

from agent_connector.agents import analyze_logs, analyze_severity, recommend_actions
from agent_connector.domain.models import IncidentRequest

data = json.loads(Path("scenarios/fixtures/inc-db-001.json").read_text())
incident = IncidentRequest.model_validate(data)

print(analyze_severity(incident).model_dump_json(indent=2))
print(recommend_actions(incident).model_dump_json(indent=2))
print(analyze_logs(incident).model_dump_json(indent=2))
'@ | python -
```

The Log Analysis streaming function can also be exercised locally before the
gRPC server exists:

```python
from agent_connector.agents import analyze_logs_stream

for event in analyze_logs_stream(incident):
    print(event.type.value, event.message)
```

## Run the local gRPC agent processes

Each agent listens on localhost with the locked demo ports:

| Agent | Address |
|---|---|
| Severity | `127.0.0.1:50051` |
| Runbook | `127.0.0.1:50052` |
| Log Analysis | `127.0.0.1:50053` |

In three separate terminals:

```bash
python -m agent_connector.servers.severity
python -m agent_connector.servers.runbook
python -m agent_connector.servers.log_analysis
```

After `pip install -e .`, the same entry points are also available as:

```bash
agent-connector-severity
agent-connector-runbook
agent-connector-log-analysis
```

Stop a process with Ctrl+C.

## Run the local HTTP agent processes

Each unary HTTP agent listens on localhost with the locked demo ports:

| Agent | Address |
|---|---|
| Severity | `http://127.0.0.1:8001` |
| Runbook | `http://127.0.0.1:8002` |
| Log Analysis | `http://127.0.0.1:8003` |

Routes:

| Agent | Method | Path |
|---|---|---|
| Severity | `POST` | `/v1/severity/analyze` |
| Runbook | `POST` | `/v1/runbook/recommend` |
| Log Analysis | `POST` | `/v1/log-analysis/analyze` |

In three separate terminals:

```bash
python -m agent_connector.servers.http_severity
python -m agent_connector.servers.http_runbook
python -m agent_connector.servers.http_log_analysis
```

After `pip install -e .`, the same entry points are also available as:

```bash
agent-connector-http-severity
agent-connector-http-runbook
agent-connector-http-log-analysis
```

## Run the orchestrator CLI

Default mixed gRPC stream workflow (gRPC agents on `50051`–`50053`):

```bash
agent-connector scenarios/fixtures/inc-db-001.json
```

Unary comparison paths:

```bash
agent-connector --transport grpc-unary scenarios/fixtures/inc-db-001.json
agent-connector --transport http-unary scenarios/fixtures/inc-db-001.json
```

Or without the console script:

```bash
python -m agent_connector.orchestrator.cli scenarios/fixtures/inc-db-001.json
```

For `grpc-stream`, the CLI prints Log Analysis stream updates as they arrive,
then a combined incident report. Structured call/event records append to
`logs/orchestrator.jsonl` by default (`--no-jsonl` disables logging).

Exit status is `0` when every agent completes with `OK`, otherwise `1`.

## Run Stage 7 benchmarks

Start the gRPC and/or HTTP agent processes first (deterministic analyzer).
Then run the locked matrix (payload sizes 100/1000/5000, concurrency 1/5/10,
3 warm-ups + 30 timed trials per cell by default):

```bash
agent-connector-benchmark --generate-fixtures --summarize
```

Useful flags:

```bash
# Smoke cell only
agent-connector-benchmark --payload-sizes 100 --concurrency 1 --warmup 0 --trials 2 --summarize

# Aggregate an existing run
agent-connector-benchmark --summary-only benchmarks/results/<run_id>/trials.csv
```

Each run writes `benchmarks/results/<run_id>/trials.csv`, `run_meta.json`,
and with `--summarize` also `summary.csv` plus charts under `charts/`.

## Run the tests

```bash
python -m pytest -q
```

The current suite tests the three agents, input validation, sample incidents,
stream event ordering, shared evidence behavior, conversions between Pydantic
and protobuf messages, the gRPC and HTTP service adapters, concurrent
orchestration (stream and unary), and cross-transport equivalence including
timeout and unavailable-agent partial reports.

## Regenerate protobuf files

After changing `proto/incident.proto`, regenerate the committed Python bindings:

```bash
python -m grpc_tools.protoc -Iagent_connector/generated=proto --python_out=src --pyi_out=src --grpc_python_out=src proto/incident.proto
```

If Bash is available, the helper script runs the same command:

```bash
bash scripts/generate_proto.sh
```

Do not edit files under `src/agent_connector/generated/` manually.

## Make commands

With the virtual environment active and Make installed:

```bash
make install  # Install the project and development dependencies
make proto    # Regenerate protobuf and gRPC modules
make test     # Run the tests
```

Make and Bash are conveniences only. The direct Python commands above work
without them.

## Repository layout

```text
proto/                              Protobuf messages and service definitions
scenarios/fixtures/                 Sample incidents and expected results
scripts/generate_proto.sh           Protobuf generation helper
src/agent_connector/agents/         Severity, Runbook, and Log Analysis logic
src/agent_connector/analyzers/      Deterministic and live summarizer providers
src/agent_connector/domain/         Pydantic request and response models
src/agent_connector/generated/      Generated protobuf and gRPC modules
src/agent_connector/grpc_services/  Thin async gRPC adapters
src/agent_connector/http_services/  Thin FastAPI unary adapters
src/agent_connector/servers/        Independently runnable agent processes
src/agent_connector/orchestrator/   Concurrent stream/unary workflows and CLI
src/agent_connector/benchmarks/     Synthetic fixtures, timed runner, summary/charts
src/agent_connector/protocol/       Domain/protobuf conversion functions
src/agent_connector/runbooks/       Local troubleshooting catalog
tests/unit/                         Unit and contract tests
tests/integration/                  Real-channel gRPC/HTTP integration tests
benchmarks/results/                 Timed run outputs (gitignored per run id)
```

## Current limitations

Written evaluation, presentation, and demo script polish belong to Stage 8.
Keep live LLM mode out of transport benchmark runs.
