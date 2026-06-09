from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone

from mcp_server import get_mcp_client


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def detect_ticket_id(task: str) -> str | None:
    match = re.search(r"\bP1-\d{4}-\d{3}\b", task, flags=re.IGNORECASE)
    if match:
        return match.group(0).upper()
    if "p1" in task.lower():
        return "P1-2026-001"
    return None


def normalize_text(text: str) -> str:
    lowered = text.lower().strip()
    normalized = unicodedata.normalize("NFD", lowered)
    without_diacritics = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return without_diacritics.replace("đ", "d")


def derive_policy_result(task: str, chunks: list[dict], ticket_info: dict | None) -> dict:
    normalized = task.lower()
    normalized_ascii = normalize_text(task)
    decision = "Use documented policy guidance."
    applicable_policy = "General helpdesk policy"
    exceptions: list[str] = []
    requires_approval = False
    risk_level = "medium"

    if (
        "flash sale" in normalized
        and ("refund" in normalized or "hoan tien" in normalized_ascii)
    ) or ("san pham loi" in normalized_ascii and "hoan tien" in normalized_ascii):
        applicable_policy = "Refund Policy v4"
        decision = (
            "Approve refund review under defective product rules, but Flash Sale requires supervisor approval "
            "before refund execution."
        )
        exceptions.append("Flash Sale exception requires supervisor approval.")
        requires_approval = True
        risk_level = "high"
    elif ("digital product" in normalized or "san pham so" in normalized_ascii) and (
        "refund" in normalized or "hoan tien" in normalized_ascii
    ):
        applicable_policy = "Refund Policy v4"
        decision = "Digital products are normally non-refundable unless there is a verified billing or delivery failure."
        exceptions.append("Digital Product refund exception.")
        requires_approval = True
        risk_level = "high"
    elif any(keyword in normalized for keyword in ("contractor", "admin access", "access", "emergency")):
        applicable_policy = "Access Control SOP"
        decision = (
            "Temporary admin access may be granted only for a P1 emergency with manager and security approval, "
            "time-boxed access, and mandatory audit logging."
        )
        exceptions.append("Temporary elevated access must expire automatically.")
        requires_approval = True
        risk_level = "high"
    elif "p1" in normalized or "ticket" in normalized or "escalation" in normalized:
        applicable_policy = "SLA P1 2026"
        decision = "Follow the documented P1 escalation flow and notify the on-call chain immediately."
        if ticket_info:
            risk_level = "high"
    elif "hr" in normalized or "leave" in normalized:
        applicable_policy = "HR Leave Policy"
        decision = "Question is outside core helpdesk workflow and should use the HR policy reference."
        risk_level = "low"

    evidence_sources = [chunk.get("metadata", {}).get("source_file", "") for chunk in chunks if chunk.get("metadata")]
    if ticket_info:
        evidence_sources.append(f"ticket:{ticket_info.get('ticket_id', 'default')}")

    return {
        "decision": decision,
        "applicable_policy": applicable_policy,
        "exceptions": exceptions,
        "requires_approval": requires_approval,
        "risk_level": risk_level,
        "evidence_sources": list(dict.fromkeys(source for source in evidence_sources if source)),
    }


def run(state: dict) -> dict:
    task = str(state.get("task", "")).strip()
    top_k = int(state.get("top_k", 5) or 5)
    client = get_mcp_client()

    kb_result = client.search_kb(task, top_k=top_k)
    chunks = kb_result.get("chunks", [])
    state["retrieved_chunks"] = chunks

    state.setdefault("mcp_tools_used", []).append(kb_result.get("tool_call", {}))
    state.setdefault("mcp_results", []).append(
        {
            "tool": "search_kb",
            "result_preview": {
                "num_chunks": len(chunks),
                "sources": kb_result.get("sources", []),
            },
        }
    )

    ticket_info = None
    ticket_id = detect_ticket_id(task)
    if ticket_id:
        ticket_info = client.get_ticket_info(ticket_id)
        state["mcp_tools_used"].append(ticket_info.get("tool_call", {}))
        state["mcp_results"].append(
            {
                "tool": "get_ticket_info",
                "result_preview": {
                    "ticket_id": ticket_info.get("ticket_id"),
                    "severity": ticket_info.get("severity"),
                    "notified": ticket_info.get("notified", []),
                },
            }
        )

    policy_result = derive_policy_result(task, chunks, ticket_info)
    state["policy_result"] = policy_result
    state.setdefault("workers_called", []).append("policy_tool_worker")
    state.setdefault("worker_io_log", []).append(
        {
            "timestamp": now_iso(),
            "worker": "policy_tool_worker",
            "input_task": task,
            "mcp_tools_called": [tool.get("tool", "") for tool in state.get("mcp_tools_used", [])],
            "output_decision": policy_result.get("decision", ""),
            "requires_approval": policy_result.get("requires_approval", False),
        }
    )
    return state
