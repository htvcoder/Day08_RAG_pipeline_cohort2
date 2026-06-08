"""Task 10: Generation with citation over Task 9 retrieval results."""

from __future__ import annotations

import argparse
import os
import re
from typing import Any

from dotenv import load_dotenv

from task4_chunking_indexing import configure_stdout
from task9_retrieval_pipeline import retrieve

load_dotenv()

# top_k=5: so ket qua cuoi cung nguoi dung thuong can xem/tra loi.
RETRIEVAL_TOP_K = 5
# top_p=8: so context chunks dua vao prompt. Lay nhieu hon top_k mot chut
# de LLM co them bang chung, nhung khong qua nhieu de tranh prompt dai va nhieu.
PROMPT_TOP_P = 8
MAX_CHARS_PER_CHUNK = 1800
MAX_CONTEXT_CHARS = 12000
DEFAULT_QUERY = "nghệ sĩ Việt Nam liên quan ma túy"

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

SYSTEM_PROMPT = """You are a careful RAG answer generator.

Answer the user's question using ONLY the provided context.

Citation rules:
- Every factual claim must include citation(s) immediately after the claim.
- Citations must use the exact source ids provided in context, for example [S1] or [S2].
- If one sentence uses information from multiple sources, cite all relevant sources, for example [S1][S3].
- Do not cite sources that do not support the claim.
- Do not invent citations.
- If the provided context does not contain enough evidence to answer, say exactly:
I cannot verify this information

Language:
- Answer in Vietnamese unless the user asks otherwise.

Style:
- Be concise but complete.
- Do not mention that you are an AI.
- Do not reveal hidden reasoning.
"""


def validate_inputs(query: str, top_k: int, context_k: int, score_threshold: float) -> None:
    if not query or not query.strip():
        raise ValueError("Query must not be empty.")
    if top_k <= 0:
        raise ValueError("top_k must be greater than 0.")
    if context_k <= 0:
        raise ValueError("context_k must be greater than 0.")
    if score_threshold < 0:
        raise ValueError("score_threshold must be greater than or equal to 0.")


def safe_get_metadata(chunk: dict[str, Any]) -> dict[str, Any]:
    metadata = chunk.get("metadata") or {}
    return metadata if isinstance(metadata, dict) else {}


def reorder_for_llm(chunks: list[dict]) -> list[dict]:
    """
    Reorder chunks to reduce lost-in-the-middle effect.

    Important chunks are distributed toward the beginning and the end.
    Example:
    [1, 2, 3, 4, 5] -> [1, 3, 5, 4, 2]
    """
    if len(chunks) <= 2:
        return list(chunks)

    odd_ranked = chunks[::2]
    even_ranked = chunks[1::2]
    return odd_ranked + list(reversed(even_ranked))


def format_context(chunks: list[dict]) -> tuple[str, list[dict]]:
    sources: list[dict[str, Any]] = []
    context_parts: list[str] = []
    total_chars = 0

    for index, chunk in enumerate(chunks, start=1):
        content = str(chunk.get("content") or "").strip()
        if not content:
            continue

        metadata = safe_get_metadata(chunk)
        source_id = f"S{index}"
        truncated_content = content[:MAX_CHARS_PER_CHUNK]
        block = (
            f"[{source_id}]\n"
            f"Title: {metadata.get('title', '')}\n"
            f"Source file: {metadata.get('source_file', '')}\n"
            f"Source type: {metadata.get('source_type', '')}\n"
            f"Chunk index: {metadata.get('chunk_index', '')}\n"
            f"Score: {float(chunk.get('score', 0.0)):.4f}\n"
            f"Content:\n{truncated_content}\n"
        )

        if total_chars + len(block) > MAX_CONTEXT_CHARS:
            remaining_chars = MAX_CONTEXT_CHARS - total_chars
            if remaining_chars <= 0:
                break
            block = block[:remaining_chars]

        total_chars += len(block)
        context_parts.append(block)
        sources.append(
            {
                "source_id": source_id,
                "title": metadata.get("title", ""),
                "source_file": metadata.get("source_file", ""),
                "source_type": metadata.get("source_type", ""),
                "chunk_index": metadata.get("chunk_index", ""),
                "score": float(chunk.get("score", 0.0)),
                "metadata": metadata,
            }
        )

        if total_chars >= MAX_CONTEXT_CHARS:
            break

    return "\n".join(context_parts).strip(), sources


def build_generation_prompt(query: str, formatted_context: str) -> tuple[str, str]:
    user_prompt = (
        f"Question:\n{query}\n\n"
        f"Context:\n{formatted_context}\n\n"
        "Now answer the question with citations."
    )
    return SYSTEM_PROMPT, user_prompt


def call_gemini(system_prompt: str, user_prompt: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("Missing GEMINI_API_KEY. Please add it to .env or environment variables.")

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise ImportError(
            "Missing dependency: google-genai. Run: python -m pip install google-genai"
        ) from exc

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=f"{system_prompt}\n\n{user_prompt}",
        config=types.GenerateContentConfig(temperature=0.0),
    )

    text = getattr(response, "text", None)
    if text:
        return text.strip()

    candidates = getattr(response, "candidates", None) or []
    if candidates:
        parts = getattr(candidates[0].content, "parts", []) if getattr(candidates[0], "content", None) else []
        combined = "".join(getattr(part, "text", "") for part in parts if getattr(part, "text", ""))
        return combined.strip()

    return ""


def call_openai_optional(system_prompt: str, user_prompt: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("Missing OPENAI_API_KEY. Please add it to .env or environment variables.")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ImportError("Missing dependency: openai. Run: python -m pip install openai") from exc

    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=OPENAI_MODEL,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return getattr(response, "output_text", "").strip()


def extractive_fallback_answer(query: str, chunks: list[dict], sources: list[dict] | None = None) -> str:
    if not chunks:
        return "I cannot verify this information"

    source_lookup = {source["source_id"]: source for source in (sources or [])}
    lines = ["Không gọi được LLM, dưới đây là các đoạn liên quan nhất từ context:"]
    used = 0
    for chunk in chunks:
        metadata = safe_get_metadata(chunk)
        content = str(chunk.get("content") or "").strip()
        if not content:
            continue

        source_id = None
        for candidate_id, source in source_lookup.items():
            if (
                source.get("source_file") == metadata.get("source_file")
                and source.get("chunk_index") == metadata.get("chunk_index")
            ):
                source_id = candidate_id
                break
        if source_id is None and used < len(source_lookup):
            source_id = list(source_lookup.keys())[used]
        if source_id is None:
            source_id = f"S{used + 1}"

        preview = " ".join(content.split())[:220]
        lines.append(f"- {preview} [{source_id}]")
        used += 1
        if used >= 3:
            break

    if used == 0:
        return "I cannot verify this information"
    return "\n".join(lines)


def validate_citations(answer: str, valid_source_ids: set[str]) -> bool:
    if answer.strip() == "I cannot verify this information":
        return True

    citations = re.findall(r"\[(S\d+)\]", answer)
    if not citations:
        return False
    return all(citation in valid_source_ids for citation in citations)


def generate_with_citation(query: str, context_chunks: list[dict]) -> str:
    """
    Generate answer using provided context chunks.
    The answer must include citations in [S1], [S2] format.
    If the answer cannot be verified from context, return:
    I cannot verify this information
    """
    if not query or not query.strip():
        raise ValueError("Query must not be empty.")
    if not context_chunks:
        return "I cannot verify this information"

    reordered_chunks = reorder_for_llm(context_chunks)
    formatted_context, sources = format_context(reordered_chunks)
    if not formatted_context.strip():
        return "I cannot verify this information"

    system_prompt, user_prompt = build_generation_prompt(query, formatted_context)
    valid_source_ids = {source["source_id"] for source in sources}

    try:
        if LLM_PROVIDER == "gemini":
            answer_text = call_gemini(system_prompt, user_prompt)
        elif LLM_PROVIDER == "openai":
            answer_text = call_openai_optional(system_prompt, user_prompt)
        else:
            raise ValueError(f"Unsupported LLM provider: {LLM_PROVIDER}")
    except Exception:
        return extractive_fallback_answer(query, reordered_chunks, sources)

    cleaned_answer = answer_text.strip() or "I cannot verify this information"
    if not validate_citations(cleaned_answer, valid_source_ids):
        return extractive_fallback_answer(query, reordered_chunks, sources)
    return cleaned_answer


def answer(query: str, top_k: int = 5, top_p: int = 8, score_threshold: float = 0.3) -> str:
    """
    End-to-end Task 10:
    1. Call retrieve() from Task 9 to get context chunks.
    2. Select top_p chunks for prompt.
    3. Reorder chunks for LLM.
    4. Generate answer with citations.
    """
    validate_inputs(query, top_k, top_p, score_threshold)

    try:
        context_chunks = retrieve(query, top_k=max(top_k, top_p), score_threshold=score_threshold)
    except Exception:
        return "I cannot verify this information"

    if not context_chunks:
        return "I cannot verify this information"

    selected_chunks = context_chunks[:top_p]
    return generate_with_citation(query, selected_chunks)


def print_sources(sources: list[dict]) -> None:
    print("Sources:")
    for source in sources:
        print(
            f"[{source['source_id']}] title={source.get('title', '')} "
            f"source_file={source.get('source_file', '')} chunk_index={source.get('chunk_index', '')}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Task 10: Generation with Citation")
    parser.add_argument("query", nargs="?", default=DEFAULT_QUERY, help="Question to answer")
    parser.add_argument("--top-k", type=int, default=RETRIEVAL_TOP_K, dest="top_k", help="Retrieval top_k")
    parser.add_argument(
        "--context-k",
        type=int,
        default=PROMPT_TOP_P,
        dest="context_k",
        help="Number of context chunks sent to the prompt",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.3,
        dest="score_threshold",
        help="Retrieval fallback threshold",
    )
    parser.add_argument("--provider", choices=["gemini", "openai"], default=LLM_PROVIDER, help="LLM provider")
    parser.add_argument("--debug", action="store_true", help="Print extra debugging details")
    parser.add_argument("--show-context", action="store_true", help="Show formatted context preview")
    return parser.parse_args()


def main() -> None:
    global LLM_PROVIDER

    configure_stdout()
    args = parse_args()
    LLM_PROVIDER = args.provider

    validate_inputs(args.query, args.top_k, args.context_k, args.score_threshold)

    try:
        context_chunks = retrieve(args.query, top_k=args.context_k, score_threshold=args.score_threshold)
    except Exception:
        context_chunks = []

    reordered_chunks = reorder_for_llm(context_chunks[: args.context_k]) if context_chunks else []
    formatted_context, sources = format_context(reordered_chunks)
    final_answer = generate_with_citation(args.query, reordered_chunks) if reordered_chunks else "I cannot verify this information"

    print("Task 10: Generation with Citation")
    print(f"Query: {args.query}")
    print(f"Provider: {LLM_PROVIDER}")
    print(f"Retrieval top_k: {args.top_k}")
    print(f"Context chunks: {len(reordered_chunks)}")
    print(f"Reordered: {'yes' if reordered_chunks else 'no'}")
    print()

    if args.debug:
        print(f"Retrieved chunks: {len(context_chunks)}")
        print(f"Formatted context chars: {len(formatted_context)}")
        print()

    if args.show_context:
        preview = formatted_context[:2500]
        print("Context preview:")
        print(preview)
        print()

    print("Answer:")
    print(final_answer)
    print()
    print_sources(sources)


if __name__ == "__main__":
    main()
