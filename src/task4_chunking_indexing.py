"""Task 4: Chunking & Indexing local Markdown data into ChromaDB."""

from __future__ import annotations

import hashlib
import os
import sys
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CHUNKING_STRATEGY = "RecursiveCharacterTextSplitter"
# RecursiveCharacterTextSplitter is a safe default for mixed Markdown content.
# chunk_size=800 keeps enough context for long legal clauses and news passages.
# chunk_overlap=120 reduces information loss when important text crosses chunk boundaries.
CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
MIN_CHUNK_LENGTH = 50

# This multilingual local model avoids API keys and external rate limits while
# remaining lightweight enough for repeated runs on a personal machine.
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIMENSION = 384

VECTOR_STORE = "ChromaDB"
COLLECTION_NAME = "rag_chunks"
SMOKE_TEST_QUERY = "nghệ sĩ Việt Nam liên quan ma túy"


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def get_markdown_files(input_dir: Path) -> list[Path]:
    markdown_files = sorted(
        path
        for path in input_dir.rglob("*.md")
        if path.is_file() and path.name != ".gitkeep"
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


def load_documents(markdown_files: list[Path], project_root: Path) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    standardized_dir = project_root / "data" / "standardized"

    for path in markdown_files:
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            continue

        relative_path = path.relative_to(project_root).as_posix()
        relative_to_standardized = path.relative_to(standardized_dir)
        parts = relative_to_standardized.parts
        source_type = parts[0] if parts else "unknown"
        title = extract_title(content, path.stem)

        documents.append(
            {
                "content": content,
                "metadata": {
                    "source_file": relative_path,
                    "source_type": source_type,
                    "title": title,
                },
            }
        )

    if not documents:
        raise ValueError("No non-empty markdown documents found in data/standardized/")

    return documents


def build_splitter():
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError as exc:
        raise ImportError(
            "Missing dependency: langchain-text-splitters. "
            "Run: python -m pip install langchain-text-splitters sentence-transformers chromadb"
        ) from exc

    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len,
    )


def chunk_documents(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    splitter = build_splitter()
    indexed_at = datetime.now(timezone.utc).isoformat()
    chunks: list[dict[str, Any]] = []

    for document in documents:
        text = document["content"]
        base_metadata = document["metadata"]
        split_texts = splitter.split_text(text)

        for chunk_index, chunk_text in enumerate(split_texts):
            normalized_text = chunk_text.strip()
            if len(normalized_text) < MIN_CHUNK_LENGTH:
                continue

            chunk_hash = hashlib.sha256(
                f"{base_metadata['source_file']}::{chunk_index}::{normalized_text}".encode("utf-8")
            ).hexdigest()

            metadata = {
                **base_metadata,
                "chunk_index": chunk_index,
                "chunk_size": len(normalized_text),
                "chunk_hash": chunk_hash,
                "indexed_at": indexed_at,
            }
            chunks.append(
                {
                    "id": f"chunk-{chunk_hash}",
                    "content": normalized_text,
                    "metadata": metadata,
                }
            )

    if not chunks:
        raise ValueError("Created 0 chunks from markdown documents.")

    return chunks


def load_embedding_model():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise ImportError(
            "Missing dependency: sentence-transformers. "
            "Run: python -m pip install langchain-text-splitters sentence-transformers chromadb"
        ) from exc

    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

    try:
        return SentenceTransformer(EMBEDDING_MODEL, local_files_only=True)
    except Exception:
        return SentenceTransformer(EMBEDDING_MODEL)


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def embed_chunks(chunks: list[dict[str, Any]]) -> list[list[float]]:
    model = load_embedding_model()
    return embed_texts(model, [chunk["content"] for chunk in chunks])


def embed_texts(model, texts: list[str]) -> list[list[float]]:
    embeddings = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=False,
    )

    if embeddings.ndim != 2 or embeddings.shape[1] != EMBEDDING_DIMENSION:
        raise ValueError(
            f"Embedding dimension mismatch: expected {EMBEDDING_DIMENSION}, got {embeddings.shape[1]}"
        )

    return embeddings.tolist()


def reset_chroma_collection(index_dir: Path):
    try:
        import chromadb
    except ImportError as exc:
        raise ImportError(
            "Missing dependency: chromadb. "
            "Run: python -m pip install langchain-text-splitters sentence-transformers chromadb"
        ) from exc

    if index_dir.exists():
        shutil.rmtree(index_dir)
    index_dir.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(index_dir))
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.get_or_create_collection(name=COLLECTION_NAME)
    return client, collection


def index_chunks(index_dir: Path, chunks: list[dict[str, Any]], embeddings: list[list[float]]):
    _, collection = reset_chroma_collection(index_dir)
    collection.add(
        ids=[chunk["id"] for chunk in chunks],
        documents=[chunk["content"] for chunk in chunks],
        metadatas=[chunk["metadata"] for chunk in chunks],
        embeddings=embeddings,
    )
    return collection


def smoke_test_search(collection, model) -> None:
    query_embedding = embed_texts(model, [SMOKE_TEST_QUERY])[0]
    results = collection.query(query_embeddings=[query_embedding], n_results=5)
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]

    print(f"Smoke test query: {SMOKE_TEST_QUERY}")
    print("Top 5 results:")

    for rank, (document, metadata) in enumerate(zip(documents, metadatas), start=1):
        preview = " ".join(document.split())[:250]
        print(f"{rank}. title={metadata.get('title', '')}")
        print(f"   source_file={metadata.get('source_file', '')}")
        print(f"   source_type={metadata.get('source_type', '')}")
        print(f"   chunk_index={metadata.get('chunk_index', '')}")
        print(f"   preview={preview}")


def main() -> None:
    configure_stdout()
    project_root = get_project_root()
    input_dir = project_root / "data" / "standardized"
    index_dir = project_root / "data" / "index" / "chroma"

    print("Task 4: Chunking & Indexing")
    print(f"Chunking strategy: {CHUNKING_STRATEGY}")
    print(f"Chunk size: {CHUNK_SIZE}")
    print(f"Chunk overlap: {CHUNK_OVERLAP}")
    print(f"Embedding model: {EMBEDDING_MODEL}")
    print(f"Embedding dimension: {EMBEDDING_DIMENSION}")
    print(f"Vector store: {VECTOR_STORE}")
    print(f"Index path: {index_dir.relative_to(project_root).as_posix()}/")

    markdown_files = get_markdown_files(input_dir)
    documents = load_documents(markdown_files, project_root)
    print(f"Loaded {len(documents)} markdown documents")

    chunks = chunk_documents(documents)
    print(f"Created {len(chunks)} chunks")

    model = load_embedding_model()
    embeddings = embed_texts(model, [chunk["content"] for chunk in chunks])
    print(f"Embedded {len(embeddings)} chunks")

    collection = index_chunks(index_dir, chunks, embeddings)
    print(f"Indexed {len(chunks)} chunks into ChromaDB")

    smoke_test_search(collection, model)
    print("DONE")


if __name__ == "__main__":
    main()
