from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from task10_generation import reorder_for_llm


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_sources(chunks: list[dict]) -> list[dict]:
    sources: list[dict] = []
    for index, chunk in enumerate(chunks, start=1):
        metadata = dict(chunk.get("metadata") or {})
        sources.append(
            {
                "source_id": str(index),
                "title": metadata.get("title", ""),
                "source_file": metadata.get("source_file", ""),
                "source_type": metadata.get("source_type", ""),
                "chunk_index": metadata.get("chunk_index", ""),
                "score": float(chunk.get("score", 0.0)),
                "metadata": metadata,
            }
        )
    return sources


def fallback_answer(chunks: list[dict], hitl_triggered: bool) -> str:
    if hitl_triggered:
        return "Không đủ tín hiệu rõ ràng để tự động xử lý. Cần human review trước khi đưa ra hướng dẫn cuối cùng."
    if not chunks:
        return "Không đủ thông tin trong knowledge base hiện tại để trả lời với độ tin cậy cao."
    lines = []
    for index, chunk in enumerate(chunks[:3], start=1):
        preview = " ".join(str(chunk.get("content", "")).split())[:220]
        lines.append(f"- {preview} [{index}]")
    return "Tóm tắt từ bằng chứng hiện có:\n" + "\n".join(lines)


def synthesize_answer(task: str, chunks: list[dict], policy_result: dict, hitl_triggered: bool) -> str:
    if hitl_triggered:
        return "Yêu cầu này đã được gắn cờ cần human review do tín hiệu không rõ ràng. Vui lòng kiểm tra thủ công trước khi hành động."

    citations = "".join(f"[{i}]" for i in range(1, min(len(chunks), 2) + 1))

    if policy_result:
        parts = [policy_result.get("decision", "").strip()]
        applicable_policy = policy_result.get("applicable_policy", "").strip()
        if applicable_policy:
            parts.append(f"Chính sách áp dụng: {applicable_policy}.{citations}")
        if policy_result.get("exceptions"):
            parts.append("Ngoại lệ cần chú ý: " + "; ".join(policy_result["exceptions"]) + f" {citations}")
        if policy_result.get("requires_approval"):
            parts.append(f"Yêu cầu phê duyệt bổ sung trước khi thực hiện. {citations}")
        return " ".join(part for part in parts if part).strip()

    if chunks:
        top_chunk = chunks[0]
        preview = " ".join(str(top_chunk.get("content", "")).split())
        return f"Dựa trên knowledge base nội bộ, thông tin liên quan nhất là: {preview} [1]"

    return fallback_answer(chunks, hitl_triggered)


def compute_confidence(chunks: list[dict], policy_result: dict, hitl_triggered: bool) -> float:
    if hitl_triggered:
        return 0.2
    if policy_result and chunks:
        return 0.9
    if chunks:
        return 0.75
    return 0.35


def run(state: dict) -> dict:
    task = str(state.get("task", "")).strip()
    chunks = list(state.get("retrieved_chunks", []))
    policy_result = dict(state.get("policy_result", {}) or {})
    hitl_triggered = bool(state.get("hitl_triggered", False))

    ordered_chunks = reorder_for_llm(chunks) if chunks else []
    answer = synthesize_answer(task, ordered_chunks, policy_result, hitl_triggered)
    sources = build_sources(ordered_chunks)
    confidence = compute_confidence(ordered_chunks, policy_result, hitl_triggered)

    state["answer"] = answer
    state["sources"] = sources
    state["confidence"] = confidence
    state.setdefault("workers_called", []).append("synthesis_worker")
    state.setdefault("worker_io_log", []).append(
        {
            "timestamp": now_iso(),
            "worker": "synthesis_worker",
            "input_task": task,
            "used_chunks": len(ordered_chunks),
            "used_policy_result": bool(policy_result),
            "hitl_triggered": hitl_triggered,
            "confidence": confidence,
        }
    )
    return state
