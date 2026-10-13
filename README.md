# Agent Connector

Agent Connector is a Python project for analyzing simulated software incidents
with three specialized agents:

- **Severity** calculates an incident score and severity level.
- **Runbook** recommends relevant troubleshooting steps.
- **Log Analysis** extracts repeated error patterns and suggests a likely cause.

The current version contains the tested agent logic and generated gRPC
contracts. Network servers, orchestration, and HTTP endpoints will be added in
later stages.

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

## Run the tests

```bash
python -m pytest -q
```

The current suite tests the three agents, input validation, sample incidents,
stream event ordering, shared evidence behavior, and conversions between
Pydantic and protobuf messages.

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
src/agent_connector/protocol/       Domain/protobuf conversion functions
src/agent_connector/runbooks/       Local troubleshooting catalog
tests/unit/                         Unit and contract tests
```

## Current limitations

This repository does not yet provide runnable gRPC servers, an orchestrator, an
HTTP API, or an end-user CLI. Those begin with the next implementation stage.
