# Agent Connector

Agent Connector is a Python project for analyzing simulated software incidents
with three specialized agents:

- **Severity** calculates an incident score and severity level.
- **Runbook** recommends relevant troubleshooting steps.
- **Log Analysis** extracts repeated error patterns and suggests a likely cause.

The current version includes the tested agent logic, generated gRPC contracts,
and three independently runnable local gRPC agent processes. Orchestration and
HTTP endpoints come in later stages.

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

## Run the tests

```bash
python -m pytest -q
```

The current suite tests the three agents, input validation, sample incidents,
stream event ordering, shared evidence behavior, conversions between Pydantic
and protobuf messages, and the gRPC service adapters.

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
src/agent_connector/domain/         Pydantic request and response models
src/agent_connector/generated/      Generated protobuf and gRPC modules
src/agent_connector/grpc_services/  Thin async gRPC adapters
src/agent_connector/servers/        Independently runnable agent processes
src/agent_connector/protocol/       Domain/protobuf conversion functions
src/agent_connector/runbooks/       Local troubleshooting catalog
tests/unit/                         Unit and contract tests
tests/integration/                  Real-channel gRPC integration tests
```

## Current limitations

This repository does not yet provide an orchestrator, an HTTP API, or an
end-user CLI. Those begin with the next implementation stage.
