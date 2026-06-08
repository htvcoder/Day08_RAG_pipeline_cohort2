"""Task 9: Complete retrieval pipeline with hybrid search and fallback."""

from __future__ import annotations

import argparse
import hashlib
import math
from typing import Any

from task4_chunking_indexing import configure_stdout
from task5_semantic_search import semantic_search
from task6_lexical_search import lexical_search
from task7_reranking import rerank

DEFAULT_TOP_K = 5
DEFAULT_SCORE_THRESHOLD = 0.3
DEFAULT_QUERY = "nghệ sĩ Việt Nam liên quan ma túy"
DEFAULT_RRF_K = 60


def validate_inputs(query: str, top_k: int, score_threshold: float) -> None:
    if not query or not query.strip():
        raise ValueError("Query must not be empty.")
    if top_k <= 0:
        raise ValueError("top_k must be greater than 0.")
    if score_threshold < 0:
        raise ValueError("score_threshold must be greater than or equal to 0.")


def safe_score(value: object) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0

    if math.isnan(score) or math.isinf(score):
        return 0.0
    return score


def candidate_key(candidate: dict) -> str:
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


def deduplicate_candidates(candidates: list[dict]) -> list[dict]:
    deduped: dict[str, dict[str, Any]] = {}

    for candidate in candidates:
        content = str(candidate.get("content") or "").strip()
        if not content:
            continue

        metadata = dict(candidate.get("metadata") or {})
        score = safe_score(candidate.get("score", 0.0))
        key = candidate_key({"content": content, "metadata": metadata})

        current = {
            "content": content,
            "score": score,
            "metadata": metadata,
        }

        existing = deduped.get(key)
        if existing is None:
            deduped[key] = current
            continue

        existing_content = str(existing.get("content") or "")
        if len(content) > len(existing_content):
            existing["content"] = content

        existing["score"] = max(safe_score(existing.get("score")), score)

        merged_metadata = dict(existing.get("metadata") or {})
        merged_metadata.update(metadata)

        existing_sources = merged_metadata.get("retrieval_sources", [])
        current_sources = metadata.get("retrieval_sources", [])
        merged_sources = list(dict.fromkeys([*existing_sources, *current_sources]))
        if merged_sources:
            merged_metadata["retrieval_sources"] = merged_sources

        for field in ("semantic_score", "lexical_score", "semantic_rank", "lexical_rank", "rrf_score"):
            if field in metadata:
                merged_metadata[field] = metadata[field]

        existing["metadata"] = merged_metadata

    return list(deduped.values())


def run_semantic_search(query: str, candidate_k: int) -> tuple[list[dict], str | None]:
    try:
        return semantic_search(query, top_k=candidate_k), None
    except Exception as exc:
        warning = f"Semantic search failed: {exc}"
        print(f"Warning: {warning}")
        return [], warning


def run_lexical_search(query: str, candidate_k: int) -> tuple[list[dict], str | None]:
    try:
        return lexical_search(query, top_k=candidate_k), None
    except Exception as exc:
        warning = f"Lexical search failed: {exc}"
        print(f"Warning: {warning}")
        return [], warning


def reciprocal_rank_fusion(
    result_lists: list[list[dict]],
    top_k: int,
    rrf_k: int = DEFAULT_RRF_K,
) -> list[dict]:
    fused_map: dict[str, dict[str, Any]] = {}

    source_names = ["semantic", "lexical"]
    for source_name, results in zip(source_names, result_lists):
        for rank, candidate in enumerate(results, start=1):
            content = str(candidate.get("content") or "").strip()
            if not content:
                continue

            metadata = dict(candidate.get("metadata") or {})
            key = candidate_key({"content": content, "metadata": metadata})
            rrf_increment = 1.0 / (rrf_k + rank)
            source_score_key = f"{source_name}_score"
            source_rank_key = f"{source_name}_rank"

            if key not in fused_map:
                fused_map[key] = {
                    "content": content,
                    "score": 0.0,
                    "metadata": {
                        **metadata,
                        "fusion_method": "rrf",
                        "rrf_score": 0.0,
                        "retrieval_sources": [],
                    },
                }

            current = fused_map[key]
            if len(content) > len(str(current.get("content") or "")):
                current["content"] = content

            current["score"] = safe_score(current.get("score")) + rrf_increment
            current_metadata = dict(current.get("metadata") or {})
            current_metadata["rrf_score"] = safe_score(current_metadata.get("rrf_score")) + rrf_increment
            current_metadata["fusion_method"] = "rrf"

            retrieval_sources = list(current_metadata.get("retrieval_sources") or [])
            if source_name not in retrieval_sources:
                retrieval_sources.append(source_name)
            current_metadata["retrieval_sources"] = retrieval_sources
            current_metadata[source_score_key] = safe_score(candidate.get("score"))
            current_metadata[source_rank_key] = rank
            current["metadata"] = current_metadata

    fused_results = list(fused_map.values())
    fused_results.sort(key=lambda item: safe_score(item.get("score")), reverse=True)
    return fused_results[:top_k]


def run_rerank(query: str, merged_candidates: list[dict], top_k: int) -> tuple[list[dict], str | None]:
    try:
        return rerank(query, merged_candidates, top_k=top_k), None
    except Exception as exc:
        warning = f"Rerank failed: {exc}"
        print(f"Warning: {warning}")
        return [], warning


def fallback_pageindex(query: str, top_k: int) -> tuple[list[dict], str | None]:
    try:
        from task8_pageindex_vectorless import pageindex_search

        results = pageindex_search(query, top_k=top_k)
        if not results:
            return [], "PageIndex returned no results."

        annotated: list[dict[str, Any]] = []
        for item in results:
            metadata = dict(item.get("metadata") or {})
            metadata["pipeline_stage"] = "pageindex_fallback"
            metadata["fallback_used"] = True
            metadata["fallback_reason"] = metadata.get("fallback_reason", "hybrid_results_below_threshold")
            annotated.append(
                {
                    "content": item.get("content", ""),
                    "score": safe_score(item.get("score", 0.0)),
                    "metadata": metadata,
                }
            )
        return annotated, None
    except Exception as exc:
        warning = f"PageIndex fallback failed: {exc}"
        print(f"Warning: {warning}")
        return [], warning


def annotate_pipeline_metadata(
    results: list[dict],
    pipeline_method: str,
    fallback_used: bool,
    fallback_attempted: bool = False,
    fallback_failed: bool = False,
    fallback_error: str | None = None,
) -> list[dict]:
    annotated: list[dict[str, Any]] = []
    for item in results:
        metadata = dict(item.get("metadata") or {})
        metadata["pipeline"] = "task9_retrieval_pipeline"
        metadata["pipeline_method"] = pipeline_method
        metadata["fallback_used"] = fallback_used
        if fallback_attempted:
            metadata["fallback_attempted"] = True
        if fallback_failed:
            metadata["fallback_failed"] = True
        if fallback_error:
            metadata["fallback_error"] = fallback_error

        annotated.append(
            {
                "content": item.get("content", ""),
                "score": safe_score(item.get("score", 0.0)),
                "metadata": metadata,
            }
        )
    annotated.sort(key=lambda item: safe_score(item.get("score")), reverse=True)
    return annotated


def retrieve(query: str, top_k: int = 5, score_threshold: float = 0.3) -> list[dict]:
    """
    Complete retrieval pipeline:
    1. Run semantic_search + lexical_search
    2. Merge results using RRF
    3. Rerank merged candidates
    4. If top result score < threshold, fallback to PageIndex
    5. Return top_k results
    """
    validate_inputs(query, top_k, score_threshold)

    candidate_k = max(top_k * 4, 20)
    semantic_results, _ = run_semantic_search(query, candidate_k)
    lexical_results, _ = run_lexical_search(query, candidate_k)

    if not semantic_results and not lexical_results:
        fallback_results, _ = fallback_pageindex(query, top_k)
        return annotate_pipeline_metadata(
            fallback_results,
            pipeline_method="pageindex_vectorless_fallback",
            fallback_used=True,
        )

    fused_results = reciprocal_rank_fusion([semantic_results, lexical_results], top_k=candidate_k)
    fused_results = deduplicate_candidates(fused_results)
    fused_results.sort(key=lambda item: safe_score(item.get("score")), reverse=True)

    reranked_results, rerank_warning = run_rerank(query, fused_results, top_k)
    if reranked_results:
        hybrid_results = reranked_results[:top_k]
    else:
        hybrid_results = fused_results[:top_k]

    top_result_score = safe_score(hybrid_results[0]["score"]) if hybrid_results else 0.0
    should_fallback = not hybrid_results or top_result_score < score_threshold

    if should_fallback:
        fallback_results, fallback_warning = fallback_pageindex(query, top_k)
        if fallback_results:
            return annotate_pipeline_metadata(
                fallback_results,
                pipeline_method="pageindex_vectorless_fallback",
                fallback_used=True,
                fallback_attempted=True,
            )[:top_k]

        if hybrid_results:
            error_parts = [part for part in [rerank_warning, fallback_warning] if part]
            return annotate_pipeline_metadata(
                hybrid_results[:top_k],
                pipeline_method="semantic+lexical+rrf+rerank",
                fallback_used=False,
                fallback_attempted=True,
                fallback_failed=True,
                fallback_error=" | ".join(error_parts) if error_parts else "PageIndex returned no results.",
            )[:top_k]

        return []

    return annotate_pipeline_metadata(
        hybrid_results[:top_k],
        pipeline_method="semantic+lexical+rrf+rerank",
        fallback_used=False,
    )[:top_k]


def print_results(
    results: list[dict],
    query: str,
    top_k: int,
    score_threshold: float,
    candidate_k: int,
    debug: bool,
    stats: dict[str, Any],
) -> None:
    print("Task 9: Complete Retrieval Pipeline")
    print(f"Query: {query}")
    print(f"Top k: {top_k}")
    print(f"Score threshold: {score_threshold}")
    print(f"Candidate k: {candidate_k}")
    print(f"Fallback enabled: {not stats.get('no_fallback', False)}")
    print()

    if debug:
        print("Pipeline stats:")
        print(f"- semantic results: {stats.get('semantic_count', 0)}")
        print(f"- lexical results: {stats.get('lexical_count', 0)}")
        print(f"- fused results: {stats.get('fused_count', 0)}")
        print(f"- reranked results: {stats.get('reranked_count', 0)}")
        print(f"- top score: {stats.get('top_score', 0.0):.4f}")
        print(f"- fallback used: {stats.get('fallback_used', False)}")
        print(f"- fallback reason: {stats.get('fallback_reason', '')}")
        print()

    print("Final results:")
    if not results:
        print("No results found.")
        return

    for rank, item in enumerate(results, start=1):
        metadata = item.get("metadata") or {}
        preview = " ".join(str(item.get("content", "")).split())[:250]
        print(f"{rank}. score={safe_score(item.get('score')):.4f}")
        print(f"   pipeline_method={metadata.get('pipeline_method', '')}")
        print(f"   title={metadata.get('title', '')}")
        print(f"   source_file={metadata.get('source_file', '')}")
        print(f"   source_type={metadata.get('source_type', '')}")
        print(f"   chunk_index={metadata.get('chunk_index', '')}")
        print(f"   retrieval_sources={metadata.get('retrieval_sources', [])}")
        print(f"   preview={preview}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Task 9: Complete retrieval pipeline")
    parser.add_argument("query", nargs="?", default=DEFAULT_QUERY, help="Query text for retrieval")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, dest="top_k", help="Number of final results")
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_SCORE_THRESHOLD,
        dest="score_threshold",
        help="Fallback threshold for hybrid top score",
    )
    parser.add_argument("--no-fallback", action="store_true", help="Disable PageIndex fallback")
    parser.add_argument("--debug", action="store_true", help="Print pipeline debug stats")
    return parser.parse_args()


def main() -> None:
    configure_stdout()
    args = parse_args()

    validate_inputs(args.query, args.top_k, args.score_threshold)
    candidate_k = max(args.top_k * 4, 20)

    semantic_results, semantic_warning = run_semantic_search(args.query, candidate_k)
    lexical_results, lexical_warning = run_lexical_search(args.query, candidate_k)

    fused_results = reciprocal_rank_fusion([semantic_results, lexical_results], top_k=candidate_k)
    fused_results = deduplicate_candidates(fused_results)
    fused_results.sort(key=lambda item: safe_score(item.get("score")), reverse=True)

    reranked_results, rerank_warning = run_rerank(args.query, fused_results, args.top_k)
    hybrid_results = reranked_results[: args.top_k] if reranked_results else fused_results[: args.top_k]
    top_score = safe_score(hybrid_results[0]["score"]) if hybrid_results else 0.0

    fallback_used = False
    fallback_reason = ""
    final_results: list[dict] = []

    if not semantic_results and not lexical_results:
        fallback_reason = "semantic_and_lexical_empty_or_failed"
    elif not hybrid_results:
        fallback_reason = "hybrid_results_empty"
    elif top_score < args.score_threshold:
        fallback_reason = "top_score_below_threshold"

    if args.no_fallback:
        final_results = annotate_pipeline_metadata(
            hybrid_results,
            pipeline_method="semantic+lexical+rrf+rerank",
            fallback_used=False,
        )[: args.top_k]
    else:
        if fallback_reason:
            fallback_results, fallback_warning = fallback_pageindex(args.query, args.top_k)
            if fallback_results:
                fallback_used = True
                final_results = annotate_pipeline_metadata(
                    fallback_results,
                    pipeline_method="pageindex_vectorless_fallback",
                    fallback_used=True,
                    fallback_attempted=True,
                )[: args.top_k]
            else:
                error_parts = [
                    part
                    for part in [
                        semantic_warning,
                        lexical_warning,
                        rerank_warning,
                        fallback_warning,
                    ]
                    if part
                ]
                final_results = annotate_pipeline_metadata(
                    hybrid_results,
                    pipeline_method="semantic+lexical+rrf+rerank",
                    fallback_used=False,
                    fallback_attempted=True,
                    fallback_failed=True,
                    fallback_error=" | ".join(error_parts) if error_parts else fallback_reason,
                )[: args.top_k]
        else:
            final_results = annotate_pipeline_metadata(
                hybrid_results,
                pipeline_method="semantic+lexical+rrf+rerank",
                fallback_used=False,
            )[: args.top_k]

    stats = {
        "semantic_count": len(semantic_results),
        "lexical_count": len(lexical_results),
        "fused_count": len(fused_results),
        "reranked_count": len(reranked_results) if reranked_results else len(hybrid_results),
        "top_score": top_score,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "no_fallback": args.no_fallback,
    }
    print_results(final_results, args.query, args.top_k, args.score_threshold, candidate_k, args.debug, stats)


if __name__ == "__main__":
    main()
