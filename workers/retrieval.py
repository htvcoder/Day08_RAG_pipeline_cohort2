from __future__ import annotations

import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

DOCS_DIR = PROJECT_ROOT / "data" / "docs"
CHROMA_DAY09_DIR = PROJECT_ROOT / "data" / "index" / "day09_chroma"
CHROMA_COLLECTION = "day09_docs"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_text(text: str) -> str:
    lowered = text.lower().strip()
    normalized = unicodedata.normalize("NFD", lowered)
    without_diacritics = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return without_diacritics.replace("đ", "d")


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", normalize_text(text))


def chunk_text(content: str, chunk_size: int = 700, overlap: int = 120) -> list[str]:
    chunks: list[str] = []
    start = 0
    content = content.strip()
    while start < len(content):
        end = min(len(content), start + chunk_size)
        chunk = content[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(content):
            break
        start = max(end - overlap, start + 1)
    return chunks


def load_doc_chunks() -> list[dict[str, Any]]:
    if not DOCS_DIR.exists():
        return []

    chunks: list[dict[str, Any]] = []
    for path in sorted(DOCS_DIR.glob("*.txt")):
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            continue
        title = content.splitlines()[0].strip().lstrip("#").strip() if content.splitlines() else path.stem
        for index, chunk in enumerate(chunk_text(content)):
            chunks.append(
                {
                    "content": chunk,
                    "score": 0.0,
                    "metadata": {
                        "source_file": path.relative_to(PROJECT_ROOT).as_posix(),
                        "source_type": "helpdesk_policy",
                        "title": title,
                        "chunk_index": index,
                    },
                }
            )
    return chunks


def keyword_search(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    results: list[dict[str, Any]] = []
    for chunk in load_doc_chunks():
        content_tokens = tokenize(chunk["content"])
        if not content_tokens:
            continue

        token_hits = sum(content_tokens.count(token) for token in query_tokens)
        phrase_bonus = sum(1 for token in query_tokens if token in normalize_text(chunk["content"]))
        score = float(token_hits + phrase_bonus)
        if score <= 0:
            continue

        enriched = {
            "content": chunk["content"],
            "score": score,
            "metadata": dict(chunk["metadata"]),
        }
        results.append(enriched)

    results.sort(key=lambda item: float(item["score"]), reverse=True)
    return results[:top_k]


def chroma_search(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    try:
        import chromadb
    except ImportError:
        return []

    if not CHROMA_DAY09_DIR.exists():
        return []

    try:
        client = chromadb.PersistentClient(path=str(CHROMA_DAY09_DIR))
        collection = client.get_collection(CHROMA_COLLECTION)
        results = collection.query(query_texts=[query], n_results=top_k, include=["documents", "metadatas", "distances"])
    except Exception:
        return []

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]
    formatted: list[dict[str, Any]] = []
    for document, metadata, distance in zip(documents, metadatas, distances):
        formatted.append(
            {
                "content": str(document),
                "score": 1.0 / (1.0 + float(distance)),
                "metadata": metadata or {},
            }
        )
    formatted.sort(key=lambda item: float(item["score"]), reverse=True)
    return formatted[:top_k]


def run(state: dict) -> dict:
    task = str(state.get("task", "")).strip()
    top_k = int(state.get("top_k", 5) or 5)

    retrieved_chunks = chroma_search(task, top_k=top_k)
    retrieval_method = "chroma"
    if not retrieved_chunks:
        retrieved_chunks = keyword_search(task, top_k=top_k)
        retrieval_method = "keyword_fallback"

    state["retrieved_chunks"] = retrieved_chunks
    state.setdefault("workers_called", []).append("retrieval_worker")
    state.setdefault("worker_io_log", []).append(
        {
            "timestamp": now_iso(),
            "worker": "retrieval_worker",
            "input_task": task,
            "retrieval_method": retrieval_method,
            "output_count": len(retrieved_chunks),
            "source_files": [item.get("metadata", {}).get("source_file", "") for item in retrieved_chunks],
        }
    )
    return state
