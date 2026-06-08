"""
Task 3 — Convert toàn bộ file trong data/landing/ thành Markdown.

Sử dụng MarkItDown của Microsoft:
    https://github.com/microsoft/markitdown

Cài đặt:
    pip install markitdown

Hướng dẫn:
    1. Scan toàn bộ file trong data/landing/ (PDF, DOCX, JSON)
    2. Convert sang Markdown
    3. Lưu vào data/standardized/ giữ nguyên cấu trúc thư mục
"""

import json
import os
from pathlib import Path

LANDING_DIR = Path(__file__).parent.parent / "data" / "landing"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "standardized"

LEGAL_EXTENSIONS = {".pdf", ".docx", ".doc"}
# TESSERACT_EXE = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
LOCAL_TESSDATA_DIR = Path(__file__).parent.parent / ".ocr_tmp" / "tessdata"


def _get_markitdown():
    try:
        from markitdown import MarkItDown
    except ImportError as exc:
        raise RuntimeError(
            "MarkItDown is required for legal document conversion. "
            "Install it with: python -m pip install markitdown"
        ) from exc
    return MarkItDown()


def _safe_read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def _extract_pdf_text_with_pdfplumber(path: Path) -> str:
    """Fallback PDF text extraction for files MarkItDown cannot read."""
    try:
        import pdfplumber
    except ImportError:
        return ""

    parts: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page_number, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            if text.strip():
                parts.append(f"## Page {page_number}\n\n{text.strip()}")
    return "\n\n".join(parts)

"""
def _extract_pdf_text_with_ocr(path: Path) -> str:
    # OCR a scanned PDF when it has no embedded text layer.
    try:
        import pypdfium2 as pdfium
        import pytesseract
    except ImportError:
        return ""

    tesseract_exe = Path(os.getenv("TESSERACT_EXE", str(TESSERACT_EXE)))
    if not tesseract_exe.exists():
        return ""

    tessdata_dir = Path(os.getenv("TESSDATA_PREFIX", str(LOCAL_TESSDATA_DIR)))
    if not (tessdata_dir / "vie.traineddata").exists():
        return ""

    pytesseract.pytesseract.tesseract_cmd = str(tesseract_exe)
    os.environ["TESSDATA_PREFIX"] = str(tessdata_dir)
    config = "--psm 6"
    document = pdfium.PdfDocument(str(path))
    parts: list[str] = []

    try:
        for page_index in range(len(document)):
            page_number = page_index + 1
            print(f"  OCR page {page_number}/{len(document)}")
            page = document[page_index]
            image = page.render(scale=2).to_pil()
            text = pytesseract.image_to_string(
                image,
                lang="vie+eng",
                config=config,
            ).strip()
            if text:
                parts.append(f"## Page {page_number}\n\n{text}")
            page.close()
    finally:
        document.close()

    return "\n\n".join(parts)
"""

def _legal_fallback_markdown(path: Path) -> str:
    return (
        f"# {path.stem}\n\n"
        f"**Source file:** {path.name}\n"
        f"**Type:** legal\n\n"
        "MarkItDown and PDF text extraction could not extract readable text "
        "from this file. The original PDF is preserved in data/landing/legal/ "
        "for manual review or OCR-based conversion."
    )


def convert_legal_docs() -> list[Path]:
    """Convert PDF/DOCX/DOC files in data/landing/legal/ to markdown."""
    legal_dir = LANDING_DIR / "legal"
    output_dir = OUTPUT_DIR / "legal"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not legal_dir.exists():
        return []

    converter = _get_markitdown()
    converted: list[Path] = []

    for filepath in sorted(legal_dir.iterdir()):
        if not filepath.is_file() or filepath.suffix.lower() not in LEGAL_EXTENSIONS:
            continue

        print(f"Converting legal: {filepath.name}")
        result = converter.convert(str(filepath))
        text_content = getattr(result, "text_content", "") or ""
        if not text_content.strip() and filepath.suffix.lower() == ".pdf":
            text_content = _extract_pdf_text_with_pdfplumber(filepath)
        """
        if not text_content.strip() and filepath.suffix.lower() == ".pdf":
            print("  No text layer found. Starting OCR fallback.")
            text_content = _extract_pdf_text_with_ocr(filepath)
        """
        if not text_content.strip():
            print(f"  Warning: extracted text is empty, writing fallback note.")
            text_content = _legal_fallback_markdown(filepath)

        output_path = output_dir / f"{filepath.stem}.md"
        _write_markdown(output_path, text_content)
        converted.append(output_path)
        print(f"  Saved: {output_path}")

    return converted


def convert_news_articles() -> list[Path]:
    """Convert crawled news JSON files in data/landing/news/ to markdown."""
    news_dir = LANDING_DIR / "news"
    output_dir = OUTPUT_DIR / "news"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not news_dir.exists():
        return []

    converted: list[Path] = []

    for filepath in sorted(news_dir.iterdir()):
        if not filepath.is_file() or filepath.suffix.lower() != ".json":
            continue

        print(f"Converting news: {filepath.name}")
        data = _safe_read_json(filepath)
        title = data.get("title") or "Unknown"
        url = data.get("url") or "N/A"
        source = data.get("source") or "unknown"
        crawled = data.get("date_crawled") or "N/A"
        body = data.get("content_markdown") or data.get("content") or ""

        content = (
            f"# {title}\n\n"
            f"**Source:** {source}\n"
            f"**URL:** {url}\n"
            f"**Crawled:** {crawled}\n\n"
            "---\n\n"
            f"{body}"
        )

        output_path = output_dir / f"{filepath.stem}.md"
        _write_markdown(output_path, content)
        converted.append(output_path)
        print(f"  Saved: {output_path}")

    return converted


def convert_all() -> dict[str, list[Path]]:
    """Convert all supported landing files to markdown."""
    print("=" * 50)
    print("Task 3: Convert to Markdown")
    print("=" * 50)

    legal_outputs = convert_legal_docs()
    news_outputs = convert_news_articles()

    print(f"\nDone. Legal: {len(legal_outputs)} | News: {len(news_outputs)}")
    print("Output:", OUTPUT_DIR)
    return {"legal": legal_outputs, "news": news_outputs}


if __name__ == "__main__":
    convert_all()
