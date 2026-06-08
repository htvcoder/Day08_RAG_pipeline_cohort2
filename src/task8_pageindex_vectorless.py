"""Task 8: PageIndex Vectorless RAG with local hybrid fallback."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from task4_chunking_indexing import configure_stdout, get_project_root
from task7_reranking import rerank

PROJECT_ROOT = get_project_root()
STANDARDIZED_DIR = PROJECT_ROOT / "data" / "standardized"
PAGEINDEX_DIR = PROJECT_ROOT / "data" / "index" / "pageindex"
UPLOAD_CACHE_DIR = PAGEINDEX_DIR / "upload_cache"
MANIFEST_PATH = PAGEINDEX_DIR / "pageindex_manifest.json"
DEFAULT_QUERY = "nghệ sĩ Việt Nam liên quan ma túy"
PROCESSING_TIMEOUT_SECONDS = 600
PROCESSING_POLL_SECONDS = 5


def load_api_key(required: bool = True) -> str:
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("PAGEINDEX_API_KEY", "").strip()
    if required and not api_key:
        raise ValueError("Missing PAGEINDEX_API_KEY. Please add it to .env or environment variables.")
    return api_key


def get_pageindex_client():
    try:
        from pageindex import PageIndexClient
    except ImportError as exc:
        raise ImportError(
            "Missing dependency: pageindex. "
            "Run: python -m pip install -U pageindex python-dotenv reportlab"
        ) from exc

    api_key = load_api_key(required=True)
    return PageIndexClient(api_key=api_key)


def load_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        return {"uploaded_at": None, "documents": []}

    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Invalid PageIndex manifest at data/index/pageindex/pageindex_manifest.json"
        ) from exc

    if not isinstance(data, dict) or "documents" not in data or not isinstance(data["documents"], list):
        raise ValueError(
            "Invalid PageIndex manifest structure at data/index/pageindex/pageindex_manifest.json"
        )

    return data


def save_manifest(manifest: dict[str, Any]) -> None:
    PAGEINDEX_DIR.mkdir(parents=True, exist_ok=True)
    manifest["uploaded_at"] = datetime.now(timezone.utc).isoformat()
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def get_markdown_files() -> list[Path]:
    if not STANDARDIZED_DIR.exists():
        raise FileNotFoundError("data/standardized/ not found.")

    markdown_files = sorted(
        path for path in STANDARDIZED_DIR.rglob("*.md") if path.is_file() and path.name != ".gitkeep"
    )
    if not markdown_files:
        raise FileNotFoundError("No markdown files found in data/standardized/")
    return markdown_files


def extract_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or fallback
    return fallback


def markdown_to_plain_text(content: str) -> str:
    text = re.sub(r"```.*?```", "", content, flags=re.DOTALL)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"[*_>-]", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def markdown_to_pdf(markdown_path: Path, pdf_path: Path) -> None:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ImportError as exc:
        raise ImportError(
            "Missing dependency: reportlab. "
            "Run: python -m pip install -U pageindex python-dotenv reportlab"
        ) from exc

    content = markdown_path.read_text(encoding="utf-8").strip()
    plain_text = markdown_to_plain_text(content)
    if not plain_text:
        raise ValueError(f"Cannot create PDF from empty markdown file: {markdown_path}")

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(pdf_path), pagesize=A4)
    width, height = A4
    text_object = pdf.beginText(40, height - 40)
    text_object.setLeading(14)
    text_object.setFont("Helvetica", 10)

    max_chars = 95
    for paragraph in plain_text.splitlines():
        current = paragraph.strip()
        if not current:
            text_object.textLine("")
            continue

        while len(current) > max_chars:
            split_at = current.rfind(" ", 0, max_chars)
            if split_at <= 0:
                split_at = max_chars
            line = current[:split_at].strip()
            current = current[split_at:].strip()
            text_object.textLine(line)
            if text_object.getY() < 50:
                pdf.drawText(text_object)
                pdf.showPage()
                text_object = pdf.beginText(40, height - 40)
                text_object.setLeading(14)
                text_object.setFont("Helvetica", 10)

        text_object.textLine(current)
        if text_object.getY() < 50:
            pdf.drawText(text_object)
            pdf.showPage()
            text_object = pdf.beginText(40, height - 40)
            text_object.setLeading(14)
            text_object.setFont("Helvetica", 10)

    pdf.drawText(text_object)
    pdf.save()


def find_manifest_entry(manifest: dict[str, Any], local_source: str) -> dict[str, Any] | None:
    for entry in manifest["documents"]:
        if entry.get("local_source") == local_source:
            return entry
    return None


def wait_for_processing(client, doc_id: str, timeout_seconds: int = PROCESSING_TIMEOUT_SECONDS) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_status = "unknown"

    while time.time() < deadline:
        document_info = client.get_document(doc_id)
        status = str(document_info.get("status", "unknown")).lower()
        last_status = status
        print(f"   status={status}")

        if status == "completed":
            return document_info
        if status == "failed":
            raise RuntimeError(f"PageIndex document processing failed for doc_id={doc_id}")

        time.sleep(PROCESSING_POLL_SECONDS)

    raise TimeoutError(
        f"Timed out waiting for PageIndex document {doc_id} to complete. Last status: {last_status}"
    )


def upload_documents(force: bool = False) -> list[dict]:
    client = get_pageindex_client()
    markdown_files = get_markdown_files()
    manifest = load_manifest()

    PAGEINDEX_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    uploaded_entries: list[dict[str, Any]] = []
    for markdown_path in markdown_files:
        content = markdown_path.read_text(encoding="utf-8").strip()
        if not content:
            continue

        relative_source = markdown_path.relative_to(PROJECT_ROOT).as_posix()
        title = extract_title(content, markdown_path.stem)
        pdf_path = UPLOAD_CACHE_DIR / markdown_path.relative_to(STANDARDIZED_DIR).with_suffix(".pdf")
        pdf_relative = pdf_path.relative_to(PROJECT_ROOT).as_posix()

        entry = find_manifest_entry(manifest, relative_source)
        if entry is None:
            entry = {
                "local_source": relative_source,
                "uploaded_pdf": pdf_relative,
                "doc_id": None,
                "status": "pending",
                "title": title,
            }
            manifest["documents"].append(entry)

        entry["title"] = title
        entry["uploaded_pdf"] = pdf_relative

        if entry.get("doc_id") and not force:
            print(f"Skipping already uploaded file: {relative_source}")
            uploaded_entries.append(entry)
            continue

        markdown_to_pdf(markdown_path, pdf_path)
        print(f"Uploading: {relative_source}")
        result = client.submit_document(str(pdf_path))
        doc_id = result.get("doc_id")
        if not doc_id:
            raise RuntimeError(f"PageIndex submit_document did not return doc_id for {relative_source}")

        entry["doc_id"] = doc_id
        entry["status"] = "submitted"
        save_manifest(manifest)

        print(f"   doc_id={doc_id}")
        document_info = wait_for_processing(client, doc_id)
        entry["status"] = str(document_info.get("status", "unknown")).lower()
        save_manifest(manifest)
        uploaded_entries.append(entry)

    save_manifest(manifest)
    return uploaded_entries


def get_completed_doc_ids() -> list[str]:
    manifest = load_manifest()
    completed_doc_ids = [
        str(entry["doc_id"])
        for entry in manifest["documents"]
        if entry.get("doc_id") and str(entry.get("status", "")).lower() == "completed"
    ]
    if not completed_doc_ids:
        raise ValueError(
            "No completed PageIndex documents found. Please run upload first:\n"
            "python src/task8_pageindex_vectorless.py --upload"
        )
    return completed_doc_ids


def parse_pageindex_response(raw_text: str, doc_ids: list[str], top_k: int) -> list[dict[str, Any]]:
    text = raw_text.strip()
    if not text:
        return []

    json_candidate = text
    if text.startswith("```"):
        json_candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.DOTALL).strip()

    try:
        parsed = json.loads(json_candidate)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", json_candidate, flags=re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                parsed = None
        else:
            parsed = None

    if isinstance(parsed, list):
        results: list[dict[str, Any]] = []
        for item in parsed[:top_k]:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            metadata = item.get("metadata") or {}
            if not isinstance(metadata, dict):
                metadata = {"raw_metadata": metadata}
            metadata.update(
                {
                    "source": "pageindex",
                    "method": "pageindex_chat_completions",
                    "doc_ids": doc_ids,
                    "fallback_used": False,
                }
            )
            results.append(
                {
                    "content": content,
                    "score": float(item.get("score", 1.0)),
                    "metadata": metadata,
                }
            )
        return results

    return [
        {
            "content": text,
            "score": 1.0,
            "metadata": {
                "source": "pageindex",
                "method": "pageindex_chat_completions_raw",
                "doc_ids": doc_ids,
                "fallback_used": False,
            },
        }
    ]


def fallback_hybrid_search(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    from task5_semantic_search import semantic_search
    from task6_lexical_search import lexical_search
    from task7_reranking import deduplicate_candidates

    semantic_candidates = semantic_search(query, top_k=top_k * 2)
    lexical_candidates = lexical_search(query, top_k=top_k * 2)
    merged_candidates = deduplicate_candidates(semantic_candidates + lexical_candidates)
    reranked = rerank(query, merged_candidates, top_k=top_k)

    fallback_results: list[dict[str, Any]] = []
    for item in reranked:
        metadata = dict(item.get("metadata") or {})
        metadata["source"] = "local_hybrid_fallback"
        metadata["fallback_used"] = True
        metadata["method"] = "semantic_plus_lexical_then_mmr"
        fallback_results.append(
            {
                "content": item["content"],
                "score": float(item["score"]),
                "metadata": metadata,
            }
        )
    return fallback_results


def run_pageindex_search(query: str, top_k: int = 5, force_fallback: bool = False) -> list[dict]:
    """
    Vectorless retrieval using PageIndex.
    Fallback khi hybrid search không trả về kết quả phù hợp.
    """
    if not query or not query.strip():
        raise ValueError("Query must not be empty.")
    if top_k <= 0:
        raise ValueError("top_k must be greater than 0.")

    if force_fallback:
        return fallback_hybrid_search(query, top_k=top_k)

    try:
        doc_ids = get_completed_doc_ids()
        client = get_pageindex_client()
        prompt = (
            "Bạn là retrieval module cho RAG pipeline.\n\n"
            "Hãy tìm các thông tin liên quan nhất tới truy vấn dưới đây trong các tài liệu đã xử lý bởi PageIndex.\n\n"
            f"Truy vấn: {query}\n\n"
            "Yêu cầu trả về JSON hợp lệ, không markdown, không giải thích thêm:\n"
            "[\n"
            "  {\n"
            '    "content": "đoạn nội dung hoặc câu trả lời liên quan",\n'
            '    "score": 1.0,\n'
            '    "metadata": {\n'
            '      "reason": "vì sao đoạn này liên quan",\n'
            '      "citation": "nếu có",\n'
            '      "title": "nếu có"\n'
            "    }\n"
            "  }\n"
            "]\n\n"
            f"Trả về tối đa {top_k} kết quả."
        )
        response = client.chat_completions(
            messages=[{"role": "user", "content": prompt}],
            doc_id=doc_ids,
            temperature=0.0,
            enable_citations=True,
        )
        raw_text = (
            response.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        parsed_results = parse_pageindex_response(raw_text, doc_ids, top_k)
        if not parsed_results:
            raise ValueError("PageIndex returned no usable results.")
        return parsed_results[:top_k]
    except Exception as exc:
        print(f"PageIndex unavailable, using local hybrid fallback: {exc}")
        return fallback_hybrid_search(query, top_k=top_k)


def pageindex_search(query: str, top_k: int = 5) -> list[dict]:
    """
    Vectorless retrieval using PageIndex.
    Fallback khi hybrid search không trả về kết quả phù hợp.
    """
    return run_pageindex_search(query, top_k=top_k, force_fallback=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Task 8: PageIndex Vectorless RAG")
    parser.add_argument("--upload", action="store_true", help="Upload standardized markdown documents to PageIndex")
    parser.add_argument("--force", action="store_true", help="Force re-upload documents even if manifest already has doc_ids")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="Query text for PageIndex search")
    parser.add_argument("--top-k", type=int, default=5, dest="top_k", help="Number of results to return")
    parser.add_argument(
        "--force-fallback",
        action="store_true",
        help="Skip PageIndex and use the local semantic+lexical+MMR fallback directly",
    )
    return parser.parse_args()


def print_results(results: list[dict[str, Any]]) -> None:
    if not results:
        print("No results found.")
        return

    for rank, item in enumerate(results, start=1):
        metadata = item.get("metadata") or {}
        preview = " ".join(str(item.get("content", "")).split())[:300]
        print(f"{rank}. score={float(item.get('score', 0.0)):.4f}")
        print(f"   source/method: {metadata.get('source', '')} / {metadata.get('method', '')}")
        print(f"   title: {metadata.get('title', '')}")
        print(f"   preview: {preview}")
        print(f"   metadata: {json.dumps(metadata, ensure_ascii=False)}")


def main() -> None:
    configure_stdout()
    args = parse_args()
    manifest = load_manifest()
    completed_doc_ids = [
        entry.get("doc_id")
        for entry in manifest.get("documents", [])
        if str(entry.get("status", "")).lower() == "completed" and entry.get("doc_id")
    ]

    print("Task 8: PageIndex Vectorless RAG")
    print(f"Manifest documents: {len(manifest.get('documents', []))}")
    print(f"Completed doc_ids: {len(completed_doc_ids)}")

    if args.upload:
        uploaded_entries = upload_documents(force=args.force)
        print(f"Uploaded/checked {len(uploaded_entries)} documents")
        return

    print(f"Query: {args.query}")
    print(f"Top k: {args.top_k}")
    print(f"Force fallback: {args.force_fallback}")
    print()

    results = run_pageindex_search(args.query, top_k=args.top_k, force_fallback=args.force_fallback)
    print_results(results)


if __name__ == "__main__":
    main()
