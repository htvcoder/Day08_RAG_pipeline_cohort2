from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from workers.policy_tool import run as policy_tool_run
from workers.retrieval import run as retrieval_run
from workers.synthesis import run as synthesis_run


class AgentState(TypedDict, total=False):
    task: str
    route_reason: str
    history: list[dict]
    risk_high: bool
    supervisor_route: str
    workers_called: list[str]
    worker_io_log: list[dict]
    mcp_tools_used: list[dict]
    mcp_results: list[dict]
    retrieved_chunks: list[dict]
    policy_result: dict
    answer: str
    sources: list[dict]
    confidence: float
    hitl_triggered: bool


HIGH_RISK_KEYWORDS = (
    "p1",
    "emergency",
    "admin access",
    "contractor",
    "refund dispute",
    "flash sale",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def ensure_state_defaults(state: AgentState) -> AgentState:
    state.setdefault("task", "")
    state.setdefault("route_reason", "")
    state.setdefault("history", [])
    state.setdefault("risk_high", False)
    state.setdefault("supervisor_route", "")
    state.setdefault("workers_called", [])
    state.setdefault("worker_io_log", [])
    state.setdefault("mcp_tools_used", [])
    state.setdefault("mcp_results", [])
    state.setdefault("retrieved_chunks", [])
    state.setdefault("policy_result", {})
    state.setdefault("answer", "")
    state.setdefault("sources", [])
    state.setdefault("confidence", 0.0)
    state.setdefault("hitl_triggered", False)
    return state


def contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    normalized = text.lower()
    return any(keyword in normalized for keyword in keywords)


def route_decision(task: str) -> tuple[str, str, bool]:
    normalized = task.lower().strip()
    risk_high = contains_any(normalized, HIGH_RISK_KEYWORDS)

    if contains_any(
        normalized,
        ("hoàn tiền", "refund", "policy", "flash sale", "digital product"),
    ):
        return (
            "policy_tool_worker",
            "Route to policy_tool_worker because the task references refund or policy handling.",
            risk_high,
        )

    if contains_any(
        normalized,
        ("cấp quyền", "access", "admin", "contractor", "emergency"),
    ):
        return (
            "policy_tool_worker",
            "Route to policy_tool_worker because the task references access control or emergency approval.",
            True,
        )

    if contains_any(normalized, ("mã lỗi không rõ", "unknown error", "unclear")):
        return (
            "human_review",
            "Route to human_review because the task explicitly signals an unclear or unknown error.",
            risk_high,
        )

    if contains_any(normalized, ("p1", "escalation", "ticket", "sla")):
        return (
            "retrieval_worker",
            "Route to retrieval_worker because the task asks for ticket, SLA, or escalation evidence.",
            True if contains_any(normalized, ("p1", "escalation")) else risk_high,
        )

    return (
        "retrieval_worker",
        "Default route to retrieval_worker because the task does not require policy-only handling.",
        risk_high,
    )


def supervisor_node(state: AgentState) -> AgentState:
    state = ensure_state_defaults(state)
    route, route_reason, risk_high = route_decision(state["task"])
    state["supervisor_route"] = route
    state["route_reason"] = route_reason
    state["risk_high"] = risk_high
    state["history"].append(
        {
            "timestamp": now_iso(),
            "node": "supervisor_node",
            "task": state["task"],
            "route": route,
            "route_reason": route_reason,
            "risk_high": risk_high,
        }
    )
    return state


def human_review_node(state: AgentState) -> AgentState:
    state = ensure_state_defaults(state)
    state["hitl_triggered"] = True
    state["retrieved_chunks"] = []
    state["worker_io_log"].append(
        {
            "timestamp": now_iso(),
            "worker": "human_review",
            "input_task": state["task"],
            "output_summary": "Marked for human review because the task was unclear.",
        }
    )
    state["workers_called"].append("human_review")
    state["history"].append(
        {
            "timestamp": now_iso(),
            "node": "human_review_node",
            "status": "triggered",
        }
    )
    return state


class SupervisorGraph:
    def invoke(self, state: AgentState) -> AgentState:
        state = supervisor_node(state)
        route = state["supervisor_route"]

        if route == "human_review":
            state = human_review_node(state)
        elif route == "policy_tool_worker":
            state = policy_tool_run(state)
        else:
            state = retrieval_run(state)

        state = synthesis_run(state)
        return ensure_state_defaults(state)


def build_initial_state(task: str) -> AgentState:
    return ensure_state_defaults(
        {
            "task": task,
            "history": [],
            "workers_called": [],
            "worker_io_log": [],
            "mcp_tools_used": [],
            "mcp_results": [],
            "retrieved_chunks": [],
            "policy_result": {},
            "sources": [],
        }
    )


def print_result(state: AgentState) -> None:
    print(f"task: {state['task']}")
    print(f"route: {state['supervisor_route']}")
    print(f"route_reason: {state['route_reason']}")
    print(f"workers_called: {state['workers_called']}")
    print(f"answer: {state['answer']}")
    print("sources:")
    for source in state.get("sources", []):
        print(
            f"- [{source.get('source_id', '?')}] {source.get('title', '')} "
            f"({source.get('source_file', '')})"
        )
    print(f"confidence: {state.get('confidence', 0.0):.2f}")
    print()


def main() -> None:
    configure_stdout()
    graph = SupervisorGraph()
    demo_queries = [
        "Ticket P1 lúc 2am - escalation xảy ra thế nào và ai nhận thông báo?",
        "Contractor cần Admin Access để sửa P1 khẩn cấp - quy trình tạm thời là gì?",
        "Khách hàng Flash Sale yêu cầu hoàn tiền vì sản phẩm lỗi - policy nào áp dụng?",
    ]

    print("Lab 9 Supervisor Graph Demo")
    print()
    for query in demo_queries:
        result = graph.invoke(build_initial_state(query))
        print_result(result)


if __name__ == "__main__":
    main()
