# Group Report

## Objective
Build a Day 9 multi-agent orchestration layer for the CS + IT Helpdesk domain while keeping the Day 8 RAG pipeline intact as a baseline.

## Architecture
The system uses a supervisor-worker pattern with three worker roles: retrieval, policy/tool, and synthesis. A mock MCP layer provides knowledge-base search and ticket lookup without requiring external services.

## How It Runs
`graph.py` demonstrates the routing behavior on representative helpdesk questions. `eval_trace.py` runs the local 15-question suite and stores traces in `artifacts/traces/`.

## Results
The implementation supports routing, local retrieval fallback, MCP tool invocation, deterministic synthesis with citations, trace generation, and local comparison between a single-agent baseline view and the Day 9 multi-agent layer.

## Limitations
- Chroma integration is optional and may be unavailable locally.
- The current MCP server is a mock implementation.
- The synthesis worker is conservative and template-driven by default.
