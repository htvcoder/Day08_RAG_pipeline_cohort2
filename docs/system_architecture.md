# System Architecture

## Day 8 Baseline
Day 8 used a mostly single-pipeline RAG flow where retrieval, policy interpretation, synthesis, and fallback behavior were coupled in a small number of modules.

## Day 9 Multi-Agent Layer
Day 9 adds a supervisor-worker orchestration layer in the project root while preserving the Day 8 baseline in `src/`.

## Main Components
- `graph.py` handles supervisor routing and graph invocation.
- `workers/retrieval.py` retrieves grounded evidence from helpdesk documents.
- `workers/policy_tool.py` applies policy logic and calls the MCP mock tools.
- `workers/synthesis.py` generates a citation-based answer from retrieved evidence.
- `mcp_server.py` exposes `search_kb` and `get_ticket_info`.
- `eval_trace.py` runs 15 questions, stores trace JSONL, and summarizes behavior.

## Data Flow
1. User task enters `SupervisorGraph.invoke`.
2. Supervisor determines route and risk.
3. Retrieval or policy tool worker gathers evidence.
4. Synthesis worker creates the final grounded answer.
5. Evaluation writes trace entries for observability and debugging.

## Trace and Observability
Each run captures route choice, worker sequence, MCP usage, retrieved sources, confidence, latency, and HITL status.
