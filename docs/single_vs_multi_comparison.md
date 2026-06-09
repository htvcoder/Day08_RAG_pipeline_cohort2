# Single vs Multi Comparison

## Metric 1: Observability / Traceability
The Day 8 baseline makes it harder to separate routing, retrieval, policy logic, and synthesis during debugging. The Day 9 layer writes per-run traces with route choice, MCP calls, sources, confidence, and HITL status.

## Metric 2: Modularity / Debuggability
Day 8 retrieval and generation are reusable but still fairly monolithic. Day 9 separates responsibilities into supervisor, retrieval worker, policy tool worker, synthesis worker, and MCP mock, so isolated testing is easier.

## Metric 3: Latency Tradeoff
Day 9 may add small overhead because the request moves across more steps and records trace details. The tradeoff is improved control and easier debugging.

## Metric 4: Answer Grounding
The Day 9 synthesis worker is intentionally conservative and citation-based. It prefers extractive grounded answers and explicit policy evidence over unsupported generation.
