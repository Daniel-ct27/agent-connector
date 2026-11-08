# Agent Connector Evaluation Report

## Research question

For the same concurrent unary incident-analysis workload, how does **gRPC**
compare with **HTTP/JSON** in communication speed, message size, error
handling, and interface clarity, and what practical value does **gRPC server
streaming** add for the longer-running Log Analysis Agent?

## System under test

- One orchestrator calling three independent local agents: Severity, Runbook,
  Log Analysis.
- Same core agent logic on both transports; deterministic Log Analysis analyzer.
- Formal unary path: Severity + Runbook + Log Analysis unary via
  `orchestrate_unary`.
- Stream path (separate): mixed gRPC workflow with Log Analysis server streaming.

## Evidence run

| Field | Value |
|---|---|
| Run id | `25059da3-b692-424e-bb9c-6ebb8b36b950` |
| Machine | Windows 11 (`Daniel-CT27`), Python 3.14.0 |
| Libraries | grpcio 1.84.0, httpx 0.28.1, FastAPI 0.162.0, Uvicorn 0.54.0 |
| Matrix | payloads 100 / 1000 / 5000; concurrency 1 / 5 / 10 |
| Trials | 3 warm-ups + 30 timed trials per cell |
| Timed rows | 810 |
| Partial / failed timed rows | 0 |

Raw artifacts: `benchmarks/results/25059da3-.../{trials.csv,summary.csv,run_meta.json,charts/}`.

Reproduce:

```bash
# start gRPC + HTTP agents with AGENT_CONNECTOR_ANALYZER=deterministic
agent-connector-benchmark --generate-fixtures --summarize
```

## Part A — Unary gRPC vs HTTP/JSON

### Communication speed

Median end-to-end orchestrator latency (client start → full `IncidentReport`),
concurrency = 1:

| Payload | gRPC median (ms) | HTTP median (ms) | Approx. ratio (HTTP/gRPC) |
|---:|---:|---:|---:|
| 100 | 8.9 | 354.7 | ~40× |
| 1000 | 44.0 | 371.0 | ~8× |
| 5000 | 204.0 | 467.7 | ~2.3× |

Observations on this workload:

- gRPC is faster in every unary cell.
- HTTP pays a large fixed per-call overhead on localhost; the gap narrows as
  payload work grows, but HTTP remains slower.
- Under concurrency 10 / payload 1000, median wave latency is ~457 ms (gRPC)
  vs ~3601 ms (HTTP); gRPC throughput stays near ~20–23 req/s while HTTP stays
  near ~2.7–2.8 req/s.

### Message size

Median request / response bytes (concurrency = 1):

| Payload | gRPC req | HTTP req | gRPC resp | HTTP resp |
|---:|---:|---:|---:|---:|
| 100 | 14,569 | 20,699 | 4,001 | 5,412 |
| 1000 | 146,270 | 207,193 | 4,004 | 5,437 |
| 5000 | 738,912 | 1,043,336 | 4,027 | 5,458 |

HTTP/JSON requests are ~1.4× larger than protobuf for the same incident.
Response bodies are also larger on HTTP, though absolute response sizes stay
small relative to large requests.

### Error handling

Timed performance cells: **100% success** on both transports (no timeouts,
unavailable, failed, or invalid outcomes in the scored matrix).

Functional parity (separate automated tests, not timed cells):

- Unavailable agent → siblings retained, `partial=true`, status `UNAVAILABLE`
- Unary timeout → siblings retained, status `TIMEOUT`
- Invalid request → transport-level rejection mapped to `INVALID_ARGUMENT`
- Internal agent failure → `FAILED` with non-leaking message

On this project, error-handling *behavior* is intentionally equivalent; the
benchmarked difference is performance and encoding, not recovery semantics.

### Interface clarity

Qualitative, from implementing and operating both stacks:

| Concern | gRPC | HTTP/JSON |
|---|---|---|
| Contract | Explicit `.proto` + generated stubs | Pydantic models / OpenAPI-ish routes |
| Local tooling | Needs protoc regeneration discipline | Easy to curl / browser-less HTTP clients |
| Streaming | First-class server streaming RPC | Out of scope (no HTTP stream counterpart) |
| Comparison fairness | Binary framing + stubs | Text JSON + httpx |

For a seminar protocol comparison, gRPC’s contract is stricter and better for
streaming; HTTP/JSON is easier to inspect by hand. Neither blocked the other
from sharing the same domain agents.

### Part A answer (scoped)

On this localhost synthetic unary workload, **gRPC was substantially faster and
more compact than HTTP/JSON**, with matching success/error semantics in tests.
HTTP’s main advantages here were operational familiarity and inspectability, not
speed or size.

## Part B — Practical value of gRPC server streaming

Stream cells record time-to-first-event (TTFE) for Log Analysis:

| Payload (conc=1) | Median TTFE (ms) | Median full completion (ms) |
|---:|---:|---:|
| 100 | 5.3 | 9.8 |
| 1000 | 27.1 | 42.0 |
| 5000 | 130.7 | 191.3 |

TTFE arrives at roughly **55–70%** of full stream completion time in these
cells, delivering early `STARTED` / evidence updates before the final summary.

Practical value observed:

1. **Earlier feedback** during longer Log Analysis work (especially 5k logs).
2. **Partial retention** on timeout/cancel paths (events already received stay
   in the report) — validated in integration tests.
3. **Not a substitute for the unary comparison** — stream latency must not be
   treated as equal to unary HTTP/gRPC latency.

### Part B answer (scoped)

For this Log Analysis agent, gRPC server streaming provides **useful progressive
updates and partial-result retention** without changing the core analysis
logic. That is additive capability beyond the unary protocol comparison.

## Limitations

- Localhost only; results do not represent WAN, TLS, proxies, or multi-host
  deployments.
- Synthetic incidents derived from one scenario template.
- Deterministic analyzer only in timed cells (live LLM excluded by design).
- HTTP stack uses FastAPI/Uvicorn/httpx; other HTTP frameworks could differ.
- Single machine / single scored run; no cross-machine replication study.
- Charts and summaries describe this run; they are not production SLOs.

## Conclusion

1. **Unary comparison:** gRPC outperformed HTTP/JSON on latency and message size
   for the same agents and fixtures, with equivalent functional error mapping.
2. **Streaming:** gRPC server streaming adds early progress and partial-result
   value for Log Analysis beyond what the unary comparison measures.

Someone else can reproduce the major numeric claims by starting the six local
agents and re-running `agent-connector-benchmark --generate-fixtures --summarize`.
