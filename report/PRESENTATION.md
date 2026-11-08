# Presentation Outline (~12 slides)

Use charts in `report/charts/` and numbers from `report/EVALUATION.md`.

1. **Title** — Agent Connector: gRPC vs HTTP/JSON for multi-agent incident analysis
2. **Research question** — unary comparison + streaming value for Log Analysis
3. **System diagram** — orchestrator → Severity / Runbook / Log Analysis
4. **Fairness design** — same agents, fixtures, deadlines; unary vs stream separated
5. **Method** — sizes 100/1k/5k, concurrency 1/5/10, 30 timed trials, deterministic analyzer
6. **Unary latency** — chart `unary_latency_vs_payload.png` (gRPC much faster)
7. **Unary throughput** — chart `unary_throughput_vs_concurrency.png`
8. **Message size** — protobuf vs JSON request bytes table
9. **Error handling** — equivalent statuses; 0 partials in scored timed cells
10. **Streaming value** — chart `stream_ttfe_vs_payload.png` (early updates)
11. **Limitations** — localhost synthetic workload only
12. **Takeaways + demo** — gRPC wins speed/size here; streaming adds progressive feedback

## Speaker notes (short)

- Do not claim WAN/production generality.
- Emphasize shared core logic so transport is the variable.
- Keep stream TTFE separate from unary latency slides.
