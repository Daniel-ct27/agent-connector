# Agent Connector Project Guide

This is the working guide for design, implementation, and evaluation. It is a
recalibration of the approved seminar design in `Junior Seminar Project (2).pdf`
against the repository state on 2026-10-12.

## 1. Project objective

Build a local distributed multi-agent incident-analysis system and use it to
answer this research question:

> For the same concurrent unary incident-analysis workload, how does gRPC
> compare with HTTP/JSON in communication speed, message size, error handling,
> and interface clarity, and what practical value does gRPC server streaming add
> to the longer-running Log Analysis Agent?

The project is successful when it answers that question with reproducible
measurements and a working demonstration. It is not intended to become a
production incident-management platform.

## 2. Experimental boundaries



### Included

- One orchestrator and three independently running local agent processes.
- Severity and Runbook unary operations.
- Log Analysis unary and gRPC server-streaming operations.
- Equivalent unary gRPC and HTTP/JSON paths using the same core logic.
- Concurrent calls, timeouts, cancellation, failures, and partial reports.
- Synthetic incidents at about 100, 1,000, and 5,000 log lines.
- One optional live LLM call after deterministic preprocessing.
- CLI demonstration, automated tests, JSONL runtime logs, CSV benchmark output,
analysis, presentation, and reproducible setup instructions.



### Excluded

- Client or bidirectional streaming.
- An HTTP streaming counterpart.
- Web UI, database, cloud deployment, Kubernetes, service mesh, or auth.
- Model training, large retrieval systems, or autonomous remediation.

Scope additions require evidence that they directly improve the research
question without threatening the required deliverables.

## 3. Architecture

```text
                         +------------------+
                         | CLI / benchmark  |
                         +--------+---------+
                                  |
                         +--------v---------+
                         |   Orchestrator   |
                         +--+-------+------+
                            |       |       |
                      unary | unary | unary or stream
                            |       |       |
                    +-------v+  +---v-----+ +v-------------+
                    |Severity|  |Runbook  | | Log Analysis |
                    | Agent  |  | Agent   | | Agent        |
                    +-------+  +---------+ +--------------+
```

Each network adapter must be thin. Core agent functions remain
protocol-independent so the transport is the principal experimental variable.

The formal comparison is:

```text
same fixture + same core logic + same concurrency + same environment
                gRPC unary  versus  HTTP/JSON unary
```

The server stream is evaluated separately for time to first update, event
ordering, cancellation, and preservation of partial findings.

## 4. Current baseline



### Complete: Stage 1 - design and shared models

- Research question and project boundary are defined.
- `proto/incident.proto` defines the shared request, responses, statuses, and
stream events.
- Pydantic models mirror the protocol contract.
- Database failure, retry storm, and expired certificate fixtures exist with
expected outputs.



### Complete: Stage 2 - core agent logic

- Severity scoring is deterministic and unit tested.
- Runbook matching is deterministic and unit tested.
- Log preprocessing, deterministic summaries, unary results, and stream-event
generation are unit tested.
- Current suite: 36 passing tests.



### Partially complete ahead of schedule: Stage 5

- A deterministic Log Analysis substitute exists.
- A live analyzer provider and real LLM call do not exist yet.



### Current position

The next active milestone is **Stage 3: independent gRPC services**. There are
currently no generated protobuf bindings, network servers/clients, orchestrator,
HTTP services, benchmark runner, CLI, packaging metadata, or runtime logging.

## 5. Recalibrated roadmap

The original eight-stage order remains the governing sequence. Work completed
early is acknowledged, but stages are not skipped unless their exit criteria are
met.

### Stage 1 - Project design and shared data models: complete

Exit evidence: stable contract, loadable sample incidents, expected outputs.

### Stage 2 - Core agent logic: complete

Exit evidence: all three functions pass predictable unit tests.

Before Stage 3 begins, perform a short foundation hardening pass:

- add reproducible packaging and dependency metadata;
- define one supported protobuf generation command;
- clarify the precise semantics of `EvidenceItem`;
- add contract tests where Pydantic/protobuf drift is possible.

This is not a new project stage; it closes implementation hygiene omitted while
the core was being established.

### Stage 3 - Independent gRPC agent services: next

Build:

- generated protobuf Python modules;
- async unary Severity and Runbook services;
- async unary and server-streaming Log Analysis service;
- three independently runnable processes;
- small clients and integration tests for each operation.

Exit criterion: each service runs independently and the Log Analysis stream
emits ordered, meaningful evidence and completion events.

### Stage 4 - Concurrent gRPC orchestration

Build:

- concurrent startup of all three calls;
- two-second unary and ten-second streaming deadlines;
- cancellation and error mapping;
- partial-result assembly;
- structured JSONL call and event logs;
- CLI command that prints stream updates and a combined report.

Exit criterion: one command runs the complete mixed gRPC workflow, including
useful reports under planned failure conditions.

### Stage 5 - Limited LLM integration

Refactor the current deterministic summarizer behind an analyzer interface, then
add one live provider implementation. Both modes must produce the same response
shape. Benchmark mode always uses the deterministic implementation.

Exit criterion: live and deterministic modes work through the same Log Analysis
service interface without changing transport behavior.

### Stage 6 - Equivalent unary HTTP/JSON implementation

Build FastAPI endpoints and an HTTP orchestrator path for all three unary final
results. Reuse the core functions and match concurrency, deadlines, failures,
and final-report semantics used by the unary gRPC path.

Exit criterion: cross-implementation tests demonstrate semantically equivalent
gRPC and HTTP/JSON results for the same incidents.

### Stage 7 - Failure and performance evaluation

Test unavailable agents, timeouts, invalid requests, internal errors, early
stream termination, and cancellation. Benchmark all combinations of the three
payload sizes and concurrency levels using repeated controlled trials.

Exit criterion: checked CSV results and charts cover median, p95, throughput,
bytes, outcome rates, time to first stream update, and partial-result behavior.

### Stage 8 - Analysis and demonstration

Interpret results without generalizing beyond the local synthetic workload.
Finish the written report, limitations, presentation, setup guide, and live CLI
demonstration.

Exit criterion: another person can reproduce the major results and the final
submission answers both parts of the research question.

## 6. Decision framework

Use these tests whenever an implementation choice is proposed:

1. **Research relevance:** Does it help answer the unary comparison or streaming
  value question?
2. **Experimental fairness:** Does it keep agent logic, input, concurrency,
  environment, and measured boundaries equivalent across transports?
3. **Contract stability:** Does it preserve public field meanings, statuses, and
  partial-result behavior?
4. **Determinism:** Can tests and benchmarks run without network/model variance?
5. **Failure visibility:** Will callers receive a clear status and retain useful
  completed or partial work?
6. **Reproducibility:** Can a fresh checkout execute the same workflow through
  documented commands?
7. **Scope control:** Is the choice required, or is it an attractive diversion?

When two options both work, prefer the simpler option that produces clearer
measurements and less transport-specific business logic.

## 7. Measurement rules

- Establish semantic equivalence before comparing performance.
- Measure unary Log Analysis in the formal protocol comparison; do not compare
a streaming response directly against a unary response as if they were equal.
- Define whether serialization and client processing are inside each measured
boundary and apply that definition to both transports.
- Warm both implementations consistently and use the same trial order policy.
- Save raw trial data, not only aggregates.
- Report median and p95 alongside sample counts and failure rates.
- Keep live LLM latency out of transport benchmarks.
- Record machine, Python, library, payload, concurrency, and configuration data
with benchmark results.



## 8. Completion checklist

- [x] Shared contracts and domain models
- [x] Three sample incident scenarios
- [x] Three deterministic core agents
- [x] Unit tests for current core behavior
- [x] Reproducible package and protobuf generation
- [ ] Three independent gRPC services
- [ ] Concurrent mixed gRPC orchestrator and CLI
- [ ] Deadlines, cancellation, failures, and partial reports
- [ ] Deterministic/live analyzer interface and one live LLM call
- [ ] Equivalent unary HTTP/JSON implementation
- [ ] Cross-transport equivalence tests
- [ ] Multi-size synthetic datasets
- [ ] Reproducible benchmark and saved raw results
- [ ] Charts, written evaluation, setup guide, presentation, and demonstration



## 9. Immediate decision gate

Before implementing the gRPC services in Stage 3, lock the remaining items in
`docs/DECISIONS.md`:

1. Async gRPC server/client process layout and local ports.
2. gRPC status mapping for invalid input, internal failure, timeout, and
   unavailability.

Once those are settled, Stage 3 can proceed without changing the approved
research design.
