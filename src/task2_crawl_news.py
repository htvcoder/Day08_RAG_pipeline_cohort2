"""
Task 2 - Crawl news articles about Vietnamese artists/public figures related
to drug cases.

Each crawled article is saved as one JSON file in data/landing/news/ with:
url, title, date_crawled, source, and content_markdown.
"""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

DATA_DIR = Path(__file__).parent.parent / "data" / "landing" / "news"


def setup_directory() -> None:
    """Create data/landing/news/ if it does not exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


ARTICLE_URLS = [
    "https://tuoitre.vn/bat-ca-si-long-nhat-va-ca-si-son-ngoc-minh-vi-lien-quan-ma-tuy-20260520082138943.htm",
    "https://thanhnien.vn/ca-si-long-nhat-bi-bat-showbiz-viet-lien-tiep-chan-dong-vi-ma-tuy-18526052013032001.htm",
    "https://vietnamnet.vn/sao-viet-bi-bat-ngoi-tu-mat-danh-tieng-vi-chat-cam-2513746.html",
    "https://vtv.vn/phap-luat/ca-si-chu-bin-bi-bat-vi-lien-quan-ma-tuy-20240607115007528.htm",
    "https://dantri.com.vn/phap-luat/ca-si-chu-bin-bi-tam-giu-vi-lien-quan-den-ma-tuy-20240606183158183.htm",
    "https://tuoitre.vn/vien-kiem-sat-tp-hcm-nhieu-nghe-si-nguoi-noi-tieng-bi-khoi-to-do-lien-quan-ma-tuy-20251209142132042.htm"     
]


def _source_from_url(url: str) -> str:
    hostname = urlparse(url).netloc.lower()
    return hostname.removeprefix("www.")


def _extract_title_from_markdown(markdown: str, fallback: str = "Unknown") -> str:
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            if title:
                return title
    return fallback


def _html_to_markdownish(html: str) -> str:
    """Small fallback converter when Crawl4AI is unavailable or blocked."""
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
    title = title_match.group(1).strip() if title_match else "Untitled article"

    text = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html)
    text = re.sub(r"(?i)</(p|h1|h2|h3|li|div|br)>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    entities = {
        "&nbsp;": " ",
        "&amp;": "&",
        "&lt;": "<",
        "&gt;": ">",
        "&quot;": '"',
        "&#39;": "'",
    }
    for entity, replacement in entities.items():
        text = text.replace(entity, replacement)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    return f"# {title}\n\n{text}"


def _article_payload(url: str, title: str, content_markdown: str) -> dict:
    return {
        "url": url,
        "title": title,
        "date_crawled": datetime.now().isoformat(),
        "source": _source_from_url(url),
        "content_markdown": content_markdown,
    }


def _fallback_fetch(url: str) -> dict:
    """Fetch article content with requests if Crawl4AI cannot read the page."""
    import requests
    from requests.exceptions import SSLError

    request_kwargs = {
        "timeout": 30,
        "headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0 Safari/537.36"
            )
        },
    }

    try:
        response = requests.get(url, **request_kwargs)
    except SSLError:
        requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]
        response = requests.get(url, verify=False, **request_kwargs)

    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    content_markdown = _html_to_markdownish(response.text)
    title = _extract_title_from_markdown(content_markdown)
    return _article_payload(url, title, content_markdown)


async def crawl_article(url: str) -> dict:
    """
    Crawl one article and return metadata plus markdown content.

    Returns:
        {
            "url": str,
            "title": str,
            "date_crawled": str,
            "source": str,
            "content_markdown": str,
        }
    """
    try:
        from crawl4ai import AsyncWebCrawler

        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url)
            content_markdown = getattr(result, "markdown", "") or ""
            metadata = getattr(result, "metadata", {}) or {}
            title = metadata.get("title") or _extract_title_from_markdown(
                content_markdown
            )

            if not content_markdown.strip():
                raise ValueError("Crawl4AI returned empty content")

            return _article_payload(url, title, content_markdown)
    except Exception as exc:
        print(f"  ! Crawl4AI failed, using requests fallback: {exc}")
        return _fallback_fetch(url)


async def crawl_all() -> None:
    """Crawl all article URLs and save each successful result as JSON."""
    setup_directory()

    for i, url in enumerate(ARTICLE_URLS, 1):
        print(f"[{i}/{len(ARTICLE_URLS)}] Crawling: {url}")
        try:
            article = await crawl_article(url)
            filepath = DATA_DIR / f"article_{i:02d}.json"
            filepath.write_text(
                json.dumps(article, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"  Saved: {filepath}")
        except Exception as exc:
            print(f"  Failed: {url} ({exc})")


if __name__ == "__main__":
    if not ARTICLE_URLS:
        print("Please fill ARTICLE_URLS before running.")
    else:
        asyncio.run(crawl_all())
