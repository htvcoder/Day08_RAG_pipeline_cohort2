from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
DOCS_DIR = PROJECT_ROOT / "data" / "docs"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_text(text: str) -> str:
    lowered = text.lower().strip()
    normalized = unicodedata.normalize("NFD", lowered)
    without_diacritics = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return without_diacritics.replace("đ", "d")


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", normalize_text(text))


def load_docs() -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    if not DOCS_DIR.exists():
        return docs
    for path in sorted(DOCS_DIR.glob("*.txt")):
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            continue
        title = content.splitlines()[0].strip().lstrip("#").strip() if content.splitlines() else path.stem
        docs.append(
            {
                "path": path,
                "title": title,
                "content": content,
            }
        )
    return docs


def split_paragraphs(content: str) -> list[str]:
    paragraphs = [block.strip() for block in re.split(r"\n\s*\n", content) if block.strip()]
    return paragraphs or [content.strip()]


class MockMCPServer:
    def search_kb(self, query: str, top_k: int = 3) -> dict:
        query_tokens = tokenize(query)
        results: list[dict[str, Any]] = []

        for doc in load_docs():
            for chunk_index, paragraph in enumerate(split_paragraphs(doc["content"])):
                paragraph_tokens = tokenize(paragraph)
                if not paragraph_tokens:
                    continue
                score = float(sum(paragraph_tokens.count(token) for token in query_tokens))
                if score <= 0:
                    continue
                results.append(
                    {
                        "content": paragraph,
                        "score": score,
                        "metadata": {
                            "source_file": doc["path"].relative_to(PROJECT_ROOT).as_posix(),
                            "source_type": "helpdesk_policy",
                            "title": doc["title"],
                            "chunk_index": chunk_index,
                        },
                    }
                )

        results.sort(key=lambda item: float(item["score"]), reverse=True)
        top_chunks = results[:top_k]
        sources = [item.get("metadata", {}).get("source_file", "") for item in top_chunks]
        return {
            "chunks": top_chunks,
            "sources": list(dict.fromkeys(source for source in sources if source)),
            "tool_call": {
                "tool": "search_kb",
                "input": {"query": query, "top_k": top_k},
                "output": {"num_chunks": len(top_chunks), "sources": sources},
                "timestamp": now_iso(),
            },
        }

    def get_ticket_info(self, ticket_id: str) -> dict:
        ticket_id = (ticket_id or "P1-2026-001").upper()
        mock_tickets = {
            "P1-2026-001": {
                "ticket_id": "P1-2026-001",
                "severity": "P1",
                "created_at": "02:00",
                "on_call": "Primary SRE On-Call",
                "notified": ["Primary SRE On-Call", "Incident Commander", "Support Lead"],
                "escalation_steps": [
                    "Notify primary on-call immediately.",
                    "Escalate to incident commander within 10 minutes.",
                    "Notify support lead and engineering manager within 15 minutes.",
                ],
            },
            "P1-2026-002": {
                "ticket_id": "P1-2026-002",
                "severity": "P1",
                "created_at": "02:15",
                "on_call": "Platform Operations On-Call",
                "notified": ["Platform Operations On-Call", "Security Lead", "Customer Escalation Manager"],
                "escalation_steps": [
                    "Page platform on-call.",
                    "Engage security lead for elevated-access requests.",
                    "Update customer escalation manager every 30 minutes.",
                ],
            },
        }
        payload = mock_tickets.get(
            ticket_id,
            {
                "ticket_id": ticket_id,
                "severity": "P1",
                "created_at": "02:00",
                "on_call": "Primary SRE On-Call",
                "notified": ["Primary SRE On-Call", "Incident Commander", "Support Lead"],
                "escalation_steps": [
                    "Notify primary on-call immediately.",
                    "Escalate to incident commander within 10 minutes.",
                    "Notify support lead and engineering manager within 15 minutes.",
                ],
            },
        )
        payload["tool_call"] = {
            "tool": "get_ticket_info",
            "input": {"ticket_id": ticket_id},
            "output": {
                "severity": payload["severity"],
                "on_call": payload["on_call"],
                "notified": payload["notified"],
            },
            "timestamp": now_iso(),
        }
        return payload


def get_mcp_client() -> MockMCPServer:
    return MockMCPServer()
