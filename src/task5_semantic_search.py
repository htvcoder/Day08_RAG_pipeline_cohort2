"""Task 5: Semantic Search over the Task 4 ChromaDB index."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from task4_chunking_indexing import (
    COLLECTION_NAME,
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    configure_stdout,
    get_project_root,
    load_embedding_model,
)

CHROMA_DIR = get_project_root() / "data" / "index" / "chroma"
DEFAULT_QUERY = "nghệ sĩ Việt Nam liên quan ma túy"


def load_collection(chroma_dir: Path, collection_name: str):
    try:
        import chromadb
    except ImportError as exc:
        raise ImportError(
            "Missing dependency: chromadb. "
            "Run: python -m pip install chromadb sentence-transformers"
        ) from exc

    if not chroma_dir.exists():
        raise FileNotFoundError(
            "Chroma index directory not found at data/index/chroma/. "
            "Run: python src/task4_chunking_indexing.py"
        )

    client = chromadb.PersistentClient(path=str(chroma_dir))

    try:
        collection = client.get_collection(collection_name)
    except Exception as exc:
        raise ValueError(
            "Chroma collection 'rag_chunks' not found. "
            "Run: python src/task4_chunking_indexing.py"
        ) from exc

    collection_count = collection.count()
    if collection_count <= 0:
        raise ValueError(
            "Chroma collection 'rag_chunks' is empty. "
            "Run: python src/task4_chunking_indexing.py"
        )

    return collection


def encode_query(query: str) -> list[float]:
    model = load_embedding_model()
    embedding = model.encode(
        [query],
        show_progress_bar=False,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )

    if embedding.ndim != 2 or embedding.shape[1] != EMBEDDING_DIMENSION:
        raise ValueError(
            f"Embedding dimension mismatch: expected {EMBEDDING_DIMENSION}, got {embedding.shape[1]}"
        )

    return embedding[0].tolist()


def format_results(results: dict[str, Any]) -> list[dict[str, Any]]:
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    if not documents:
        return []

    formatted: list[dict[str, Any]] = []
    for document, metadata, distance in zip(documents, metadatas, distances):
        safe_metadata = metadata or {}
        score = 1.0 / (1.0 + float(distance))
        formatted.append(
            {
                "content": document,
                "score": float(score),
                "metadata": safe_metadata,
            }
        )

    formatted.sort(key=lambda item: item["score"], reverse=True)
    return formatted


def semantic_search(query: str, top_k: int = 10) -> list[dict]:
    """
    Returns:
        List of {'content': str, 'score': float, 'metadata': dict}
    """
    if not query or not query.strip():
        raise ValueError("Query must not be empty.")
    if top_k <= 0:
        raise ValueError("top_k must be greater than 0.")

    collection = load_collection(CHROMA_DIR, COLLECTION_NAME)
    query_embedding = encode_query(query.strip())
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )
    return format_results(results)


def print_results(query: str, top_k: int, results: list[dict[str, Any]]) -> None:
    print("Task 5: Semantic Search")
    print(f"Embedding model: {EMBEDDING_MODEL}")
    print(f"Vector store: {CHROMA_DIR.relative_to(get_project_root()).as_posix()}")
    print(f"Collection: {COLLECTION_NAME}")
    print(f"Query: {query}")
    print(f"Top k: {top_k}")
    print()

    if not results:
        print("No results found.")
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
    parser = argparse.ArgumentParser(description="Run semantic search over the Task 4 Chroma index.")
    parser.add_argument("query", nargs="?", default=DEFAULT_QUERY, help="Query text for semantic search")
    parser.add_argument("--top-k", type=int, default=5, dest="top_k", help="Number of results to return")
    return parser.parse_args()


def main() -> None:
    configure_stdout()
    args = parse_args()
    results = semantic_search(args.query, top_k=args.top_k)
    print_results(args.query, args.top_k, results)


if __name__ == "__main__":
    main()
