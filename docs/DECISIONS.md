# Decision Log

This log records choices that affect the research design, public contracts, or
the comparability of the gRPC and HTTP/JSON implementations. The governing
project direction is in `docs/PROJECT_GUIDE.md`.

## Locked decisions

### Research comparison

- Compare equivalent concurrent unary gRPC and HTTP/JSON workloads.
- Evaluate gRPC server streaming separately as an additional capability.
- Reuse the same agent logic, incidents, environment, and benchmark procedure.
- Do not build an HTTP streaming counterpart; it is outside the approved scope.

### Message contract

- Proto package: `agent_connector.v1` in `proto/incident.proto`.
- All three agents accept the same `IncidentRequest`.
- HTTP/JSON uses matching Pydantic field names and meanings.
- `IncidentReport` is an orchestrator-local model, not a service RPC message.
- Each `EvidenceItem` represents one normalized message pattern in one service.
  Its `count` is the number of logs matching that exact service-pattern pair.
  Agents may aggregate those items internally but return the shared form.

### Python package and protobuf generation

- The supported Python range begins at 3.11; the current development runtime is
  Python 3.14.
- `pyproject.toml` is the authoritative package and dependency definition.
- Development uses an isolated `.venv` and an editable install with the `dev`
  dependency extra.
- `grpcio-tools` 1.81.x generates the Python message, type-stub, and gRPC files.
- Generated bindings live in `src/agent_connector/generated` and are committed.
- `make proto` is the primary regeneration command. The equivalent Bash helper
  is `scripts/generate_proto.sh`.
- Generated files are never edited manually.

### Services and operations

| Service | Operation | Pattern |
|---|---|---|
| Severity | `AnalyzeSeverity` | Unary |
| Runbook | `RecommendActions` | Unary |
| Log Analysis | `AnalyzeLogs` | Unary comparison path |
| Log Analysis | `AnalyzeLogsStream` | gRPC server streaming |

### Severity policy

- Levels: `LOW`, `MEDIUM`, `HIGH`, and `CRITICAL`.
- Thresholds: 0-24, 25-49, 50-74, and 75-100 respectively.
- Score four independent error-like signals on a 0.0-1.0 scale:
  - frequency, logarithmic saturation at 100 events: 50%
  - affected services, linear saturation at five services: 25%
  - duration, linear saturation at 300 seconds: 15%
  - fatal events, linear saturation at two events: 10%
- Only `ERROR` and `FATAL` entries determine affected services and duration.
- Blank `incident_id` or empty `logs` returns `INVALID_ARGUMENT`.

### Runbook matching policy

- A scenario, failing service, or error-like message can establish a match.
- Metadata may support an established match but cannot create one alone.
- `INFO` and `WARN` messages cannot create recommendations.
- The `confidence` field is a deterministic rule-match score used for ranking;
  it is not an empirically calibrated probability.

### Log Analysis events

Happy-path order:

1. `STARTED`
2. one or more `EVIDENCE_FOUND` events when evidence exists
3. `COMPLETED` with the final `LogAnalysisResult`

Invalid input emits one `ERROR` event. Protobuf enum value 3 is reserved because
it formerly represented a duplicate `LLM_SUMMARY` event and must not be reused.
The unary result must equal the stream's completed result.

The protobuf wire symbol for the domain event `ERROR` is
`LOG_ANALYSIS_ERROR = 5`. Protobuf enum values use package-level symbol scope,
so this prefix prevents a collision with `LogLevel.ERROR` while preserving the
wire number and the simpler domain-model value.

### Partial reports and deadlines

- Unary Severity and Runbook deadline: 2 seconds.
- Log Analysis stream deadline: 10 seconds.
- On timeout, cancellation, unavailability, or early stream termination, retain:
  - completed unary responses;
  - Log Analysis events already received;
  - a status and error message for every agent;
  - `partial = true` whenever any operation is incomplete.

### Benchmark controls

- Incident payload sizes: approximately 100, 1,000, and 5,000 log lines.
- Concurrent incidents per run: 1, 5, and 10.
- Required metrics: median latency, p95 latency, throughput, request and response
  bytes, success/timeout/failure rates, and time to first stream update.
- Use deterministic Log Analysis output for protocol benchmarks.
- Run the live LLM only for functional evaluation and demonstration.

### LLM policy

- One lightweight call occurs inside Log Analysis after local preprocessing.
- The deterministic analyzer remains available through the same interface.
- Provider, model, timeout, and development spending limit remain open.

## Open decisions

These must be resolved at the stage where they first become necessary:

- Stage 3: process configuration, ports, and exact gRPC error mapping.
- Stage 4: structured JSONL event schema and cancellation ownership.
- Stage 5: analyzer-provider interface, LLM provider/model, and spending limit.
- Stage 6: HTTP route names and HTTP status mapping equivalent to gRPC failures.
- Stage 7: repetitions, warm-up policy, machine-state controls, and CSV schema.

## Change rule

A decision that changes workload equivalence, public message meaning, benchmark
methodology, or approved scope must be recorded here before implementation.
Ordinary internal refactors that preserve those properties do not require an
entry.
