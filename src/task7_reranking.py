"""Task 7: Reranking Module using local MMR."""

from __future__ import annotations

import argparse
import hashlib
from typing import Any

from task4_chunking_indexing import (
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    configure_stdout,
    load_embedding_model,
)

MMR_LAMBDA = 0.7
DEFAULT_QUERY = "nghệ sĩ Việt Nam liên quan ma túy"


def get_embedding_model():
    return load_embedding_model()


def validate_inputs(query: str, candidates: list[dict], top_k: int) -> None:
    if not query or not query.strip():
        raise ValueError("Query must not be empty.")
    if top_k <= 0:
        raise ValueError("top_k must be greater than 0.")
    if candidates is None:
        raise ValueError("Candidates must not be None.")


def candidate_key(candidate: dict[str, Any]) -> str:
    metadata = candidate.get("metadata") or {}
    chunk_hash = metadata.get("chunk_hash")
    if chunk_hash:
        return f"chunk_hash::{chunk_hash}"

    source_file = metadata.get("source_file")
    chunk_index = metadata.get("chunk_index")
    if source_file is not None and chunk_index is not None:
        return f"source_chunk::{source_file}::{chunk_index}"

    content = str(candidate.get("content") or "")
    return f"content_hash::{hashlib.sha256(content.encode('utf-8')).hexdigest()}"


def deduplicate_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best_by_key: dict[str, dict[str, Any]] = {}

    for rank, candidate in enumerate(candidates, start=1):
        content = str(candidate.get("content") or "").strip()
        if not content:
            continue

        metadata = dict(candidate.get("metadata") or {})
        enriched = {
            "content": content,
            "score": float(candidate.get("score", 0.0)),
            "metadata": metadata,
        }
        enriched["metadata"]["original_score"] = float(candidate.get("score", 0.0))
        enriched["metadata"]["original_rank"] = rank

        key = candidate_key(enriched)
        existing = best_by_key.get(key)
        if existing is None or enriched["score"] > float(existing.get("score", 0.0)):
            best_by_key[key] = enriched

    deduped = list(best_by_key.values())
    deduped.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
    return deduped


def embed_texts(model, texts: list[str]) -> list[list[float]]:
    embeddings = model.encode(
        texts,
        show_progress_bar=False,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )

    if embeddings.ndim != 2 or embeddings.shape[1] != EMBEDDING_DIMENSION:
        raise ValueError(
            f"Embedding dimension mismatch: expected {EMBEDDING_DIMENSION}, got {embeddings.shape[1]}"
        )

    return embeddings.tolist()


def cosine_similarity_matrix(vectors_a: list[list[float]], vectors_b: list[list[float]]) -> list[list[float]]:
    matrix: list[list[float]] = []
    for vec_a in vectors_a:
        row: list[float] = []
        for vec_b in vectors_b:
            row.append(float(sum(a * b for a, b in zip(vec_a, vec_b))))
        matrix.append(row)
    return matrix


def mmr_select(
    query_embedding: list[float],
    candidate_embeddings: list[list[float]],
    top_k: int,
    lambda_param: float = MMR_LAMBDA,
) -> list[tuple[int, float]]:
    if not candidate_embeddings:
        return []

    query_similarities = [float(sum(q * d for q, d in zip(query_embedding, doc_embedding))) for doc_embedding in candidate_embeddings]
    selected_indices: list[int] = []
    selected_scores: list[float] = []
    remaining_indices = list(range(len(candidate_embeddings)))

    while remaining_indices and len(selected_indices) < min(top_k, len(candidate_embeddings)):
        best_index: int | None = None
        best_score = float("-inf")

        for candidate_index in remaining_indices:
            relevance = query_similarities[candidate_index]
            redundancy = 0.0

            if selected_indices:
                redundancy = max(
                    float(sum(a * b for a, b in zip(candidate_embeddings[candidate_index], candidate_embeddings[selected_index])))
                    for selected_index in selected_indices
                )

            mmr_score = lambda_param * relevance - (1.0 - lambda_param) * redundancy
            if mmr_score > best_score:
                best_score = mmr_score
                best_index = candidate_index

        if best_index is None:
            break

        selected_indices.append(best_index)
        selected_scores.append(float(best_score))
        remaining_indices.remove(best_index)

    return list(zip(selected_indices, selected_scores))


def rerank(query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
    """
    Re-score and re-order candidates based on relevance to query.

    Args:
        query: User query.
        candidates: List of retrieval results. Each item should have:
            {
                "content": str,
                "score": float,
                "metadata": dict
            }
        top_k: Number of reranked results to return.

    Returns:
        List of reranked dicts. Each item should have:
            {
                "content": str,
                "score": float,
                "metadata": dict
            }
    """
    validate_inputs(query, candidates, top_k)
    if not candidates:
        return []

    deduped_candidates = deduplicate_candidates(candidates)
    if not deduped_candidates:
        return []

    model = get_embedding_model()
    query_embedding = embed_texts(model, [query.strip()])[0]
    candidate_texts = [candidate["content"] for candidate in deduped_candidates]
    candidate_embeddings = embed_texts(model, candidate_texts)

    selections = mmr_select(query_embedding, candidate_embeddings, top_k=top_k, lambda_param=MMR_LAMBDA)

    reranked: list[dict[str, Any]] = []
    for selected_rank, (candidate_index, mmr_score) in enumerate(selections, start=1):
        candidate = deduped_candidates[candidate_index]
        metadata = dict(candidate.get("metadata") or {})
        metadata["rerank_method"] = "mmr"
        metadata["rerank_score"] = float(mmr_score)
        metadata["rerank_rank"] = selected_rank

        reranked.append(
            {
                "content": candidate["content"],
                "score": float(mmr_score),
                "metadata": metadata,
            }
        )

    reranked.sort(key=lambda item: float(item["score"]), reverse=True)
    return reranked


def load_candidates(query: str, candidate_k: int, source: str) -> list[dict]:
    if source == "semantic":
        from task5_semantic_search import semantic_search

        return semantic_search(query, top_k=candidate_k)
    if source == "lexical":
        from task6_lexical_search import lexical_search

        return lexical_search(query, top_k=candidate_k)
    raise ValueError(f"Unknown source: {source}")


def print_candidate_list(title: str, items: list[dict[str, Any]], reranked: bool = False) -> None:
    print(title)
    if not items:
        print("No results.")
        print()
        return

    for rank, item in enumerate(items, start=1):
        metadata = item.get("metadata") or {}
        preview = " ".join(str(item.get("content", "")).split())[:250]
        print(f"{rank}. score={float(item.get('score', 0.0)):.4f}")
        if reranked:
            print(f"   original_score={float(metadata.get('original_score', 0.0)):.4f}")
        print(f"   title={metadata.get('title', '')}")
        print(f"   source_file={metadata.get('source_file', '')}")
        if reranked:
            print(f"   source_type={metadata.get('source_type', '')}")
            print(f"   chunk_index={metadata.get('chunk_index', '')}")
        print(f"   preview={preview}")
    print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local MMR reranking over retrieval candidates.")
    parser.add_argument("query", nargs="?", default=DEFAULT_QUERY, help="Query text for reranking")
    parser.add_argument("--top-k", type=int, default=5, dest="top_k", help="Number of reranked results to return")
    parser.add_argument(
        "--candidate-k",
        type=int,
        default=10,
        dest="candidate_k",
        help="Number of retrieval candidates to fetch before reranking",
    )
    parser.add_argument(
        "--source",
        choices=["semantic", "lexical"],
        default="semantic",
        help="Candidate source for the CLI demo",
    )
    return parser.parse_args()


def main() -> None:
    configure_stdout()
    args = parse_args()

    print("Task 7: Reranking Module")
    print("Method: MMR")
    print(f"Embedding model: {EMBEDDING_MODEL}")
    print(f"MMR lambda: {MMR_LAMBDA}")
    print(f"Query: {args.query}")
    print(f"Candidate k: {args.candidate_k}")
    print(f"Top k: {args.top_k}")
    print(f"Source: {args.source}")
    print()

    try:
        candidates = load_candidates(args.query, args.candidate_k, args.source)
    except Exception as exc:
        if args.source == "semantic":
            print("Cannot load candidates from semantic search. Please run Task 4 and Task 5 first.")
        else:
            print("Cannot load candidates from lexical search. Please run Task 4 and Task 6 first.")
        raise SystemExit(str(exc))

    reranked = rerank(args.query, candidates, top_k=args.top_k)

    print_candidate_list("Before rerank:", candidates[: args.top_k], reranked=False)
    print_candidate_list("After rerank:", reranked, reranked=True)


if __name__ == "__main__":
    main()
