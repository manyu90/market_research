from __future__ import annotations

import logging
from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx

from src import db
from src.collector.dedup import url_hash, content_hash

logger = logging.getLogger(__name__)


async def fetch_pdf_source(source: dict) -> int:
    """Check a page for new PDF links, download + extract text, insert items."""
    source_id = source["source_id"]
    target = source.get("url")
    if not target:
        return 0

    # Fetch the page listing PDFs (verify=False for Japanese IR sites with cert issues)
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, verify=False) as client:
        try:
            resp = await client.get(target)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Failed to fetch PDF listing %s: %s", target, exc)
            return 0

    # Extract PDF links
    pdf_links = _find_pdf_links(resp.text, target)
    if not pdf_links:
        return 0

    new_count = 0
    for pdf_url in pdf_links[:10]:  # limit per sweep
        uhash = url_hash(pdf_url)
        exists = await db.fetchval("SELECT 1 FROM items WHERE url_hash = $1", uhash)
        if exists:
            continue

        # Download PDF and extract text
        try:
            async with httpx.AsyncClient(timeout=60, follow_redirects=True, verify=False) as client:
                pdf_resp = await client.get(pdf_url)
                pdf_resp.raise_for_status()
        except httpx.HTTPError:
            logger.debug("Could not download PDF %s", pdf_url)
            continue

        raw_text = _extract_pdf_text(pdf_resp.content)
        if not raw_text:
            continue

        chash = content_hash(raw_text)
        dup = await db.fetchval("SELECT 1 FROM items WHERE content_hash = $1", chash)
        if dup:
            continue

        # Use PDF filename as title
        title = pdf_url.rsplit("/", 1)[-1] if "/" in pdf_url else pdf_url

        await db.execute(
            """INSERT INTO items (source_id, url, url_hash, content_hash, title, raw_text,
                                  language, pipeline_status)
               VALUES ($1, $2, $3, $4, $5, $6, $7, 'COLLECTED')
               ON CONFLICT (url_hash) DO NOTHING""",
            source_id, pdf_url, uhash, chash, title, raw_text,
            source.get("language", "en"),
        )
        new_count += 1

    if new_count:
        logger.info("Source %s: collected %d new PDFs", source_id, new_count)
    return new_count


def _find_pdf_links(html: str, base_url: str) -> list[str]:
    """Extract links ending in .pdf from HTML."""
    links: list[str] = []

    class PDFLinkParser(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag == "a":
                href = dict(attrs).get("href", "")
                if href.lower().endswith(".pdf"):
                    full = urljoin(base_url, href)
                    if full not in links:
                        links.append(full)

    PDFLinkParser().feed(html)
    return links


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using PyMuPDF."""
    try:
        import pymupdf
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
        return "\n".join(text_parts).strip()
    except Exception as exc:
        logger.debug("PDF text extraction failed: %s", exc)
        return ""
