"""
Task 6: Lexical Search BM25.

Lexical search / BM25:
- Khong dung embedding.
- Tim theo token/tu khoa xuat hien trong van ban.
- BM25 cham diem dua tren term frequency, inverse document frequency va do dai document.
- Uu diem: tot khi query chua keyword chinh xac nhu ten luat, dieu khoan, ten nguoi, "ma tuy".
- Nhuoc diem: kem hon semantic search khi query dien dat khac tu trong tai lieu.
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path
from typing import Any

from task4_chunking_indexing import COLLECTION_NAME, configure_stdout, get_project_root
from task5_semantic_search import CHROMA_DIR, load_collection

DEFAULT_QUERY = "ma túy nghệ sĩ"

_BM25_INDEX = None
_DOCUMENTS: list[str] | None = None
_METADATAS: list[dict[str, Any]] | None = None


def normalize_text(text: str) -> str:
    lowered = text.lower().strip()
    normalized = unicodedata.normalize("NFD", lowered)
    without_diacritics = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return without_diacritics.replace("đ", "d")


def tokenize(text: str) -> list[str]:
    normalized = normalize_text(text)
    tokens = re.findall(r"[a-z0-9]+", normalized)
    return [token for token in tokens if token]


def load_chunks_from_chroma() -> tuple[list[str], list[dict[str, Any]]]:
    collection = load_collection(CHROMA_DIR, COLLECTION_NAME)
    data = collection.get(include=["documents", "metadatas"])

    documents = data.get("documents") or []
    metadatas = data.get("metadatas") or []

    filtered_documents: list[str] = []
    filtered_metadatas: list[dict[str, Any]] = []

    for document, metadata in zip(documents, metadatas):
        if not document or not str(document).strip():
            continue
        filtered_documents.append(str(document))
        filtered_metadatas.append(metadata or {})

    if not filtered_documents:
        raise ValueError(
            "Chroma collection 'rag_chunks' has no usable documents. "
            "Please run Task 4 first:\npython src/task4_chunking_indexing.py"
        )

    return filtered_documents, filtered_metadatas


def build_bm25_index(documents: list[str]):
    try:
        from rank_bm25 import BM25Okapi
    except ImportError as exc:
        raise ImportError(
            "Missing dependency: rank-bm25. "
            "Run: python -m pip install rank-bm25"
        ) from exc

    tokenized_corpus = [tokenize(document) for document in documents]
    return BM25Okapi(tokenized_corpus), tokenized_corpus


def ensure_bm25_ready():
    global _BM25_INDEX, _DOCUMENTS, _METADATAS

    if _BM25_INDEX is not None and _DOCUMENTS is not None and _METADATAS is not None:
        return _BM25_INDEX, _DOCUMENTS, _METADATAS

    documents, metadatas = load_chunks_from_chroma()
    bm25, _ = build_bm25_index(documents)

    _BM25_INDEX = bm25
    _DOCUMENTS = documents
    _METADATAS = metadatas
    return _BM25_INDEX, _DOCUMENTS, _METADATAS


def lexical_search(query: str, top_k: int = 10) -> list[dict]:
    """
    Returns:
        List of {'content': str, 'score': float, 'metadata': dict}
    """
    if not query or not query.strip():
        raise ValueError("Query must not be empty.")
    if top_k <= 0:
        raise ValueError("top_k must be greater than 0.")

    tokenized_query = tokenize(query)
    if not tokenized_query:
        raise ValueError("Query has no searchable tokens after normalization.")

    bm25, documents, metadatas = ensure_bm25_ready()
    scores = bm25.get_scores(tokenized_query)

    ranked_indices = sorted(range(len(scores)), key=lambda index: float(scores[index]), reverse=True)

    results: list[dict[str, Any]] = []
    for index in ranked_indices[:top_k]:
        score = float(scores[index])
        if score <= 0:
            continue
        results.append(
            {
                "content": documents[index],
                "score": score,
                "metadata": metadatas[index] or {},
            }
        )

    results.sort(key=lambda item: item["score"], reverse=True)
    return results


def print_results(query: str, top_k: int, results: list[dict[str, Any]]) -> None:
    print("Task 6: Lexical Search BM25")
    print(f"Vector/index source: {CHROMA_DIR.relative_to(get_project_root()).as_posix()}")
    print(f"Collection: {COLLECTION_NAME}")
    print(f"Query: {query}")
    print(f"Top k: {top_k}")
    print()

    if not results:
        print("No BM25 results found with positive score.")
        return

    for rank, item in enumerate(results, start=1):
        metadata = item["metadata"]
        preview = " ".join(item["content"].split())[:250]
        print(f"{rank}. score={item['score']:.4f}")
        print(f"   title: {metadata.get('title', '')}")
        print(f"   source_file: {metadata.get('source_file', '')}")
        print(f"   source_type: {metadata.get('source_type', '')}")
        print(f"   chunk_index: {metadata.get('chunk_index', '')}")
        print(f"   preview: {preview}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run BM25 lexical search over the Task 4 Chroma index.")
    parser.add_argument("query", nargs="?", default=DEFAULT_QUERY, help="Query text for lexical search")
    parser.add_argument("--top-k", type=int, default=5, dest="top_k", help="Number of results to return")
    return parser.parse_args()


def main() -> None:
    configure_stdout()
    args = parse_args()
    results = lexical_search(args.query, top_k=args.top_k)
    print_results(args.query, args.top_k, results)


if __name__ == "__main__":
    main()
