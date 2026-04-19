"""Content processing pipeline.

URL -> extract -> summarize -> keywords -> embed -> save to vault + index in SQLite.
Raw text follows the same flow, skipping the extraction step.
"""
import hashlib
import logging
import time
from datetime import datetime

from src.extractor import clean_url, detect_content_type, extract_content
from src.llm import generate_summary, extract_keywords, generate_embedding, generate_obsidian_markdown
from src.vault import save_json, save_obsidian_note, _title_from_url
from src.storage import Database
from src.models import ProcessResult

logger = logging.getLogger(__name__)


def _process_content(
    url: str, title: str, content: str, content_type: str,
    db: Database, save: bool,
) -> ProcessResult:
    """Shared post-extraction flow: summarize, keywords, embed, save."""
    summary = generate_summary(content, content_type)
    logger.info(f"Summary: {len(summary)} chars")

    keywords = extract_keywords(summary)
    logger.info(f"Keywords: {keywords}")

    embedding = generate_embedding(summary)
    logger.info(f"Embedding: {len(embedding)} dimensions")

    date_str = datetime.now().strftime("%Y-%m-%d")
    obsidian_md = generate_obsidian_markdown(title, summary, keywords, url, date_str, content_type)

    timestamp = int(time.time())
    file_path = None

    if save:
        file_path = save_json(
            url=url, title=title, content_type=content_type,
            content=content, summary=summary, keywords=keywords,
            obsidian_markdown=obsidian_md, embedding=embedding,
        )
        save_obsidian_note(title, obsidian_md)

        content_hash = hashlib.md5(content.encode()).hexdigest()
        try:
            db.store(
                url=url, title=title, content_type=content_type,
                timestamp=timestamp, summary=summary, keywords=keywords,
                embedding=embedding, content_hash=content_hash,
                json_path=file_path,
            )
            logger.info("Indexed in SQLite")
        except Exception as e:
            logger.error(f"SQLite indexing failed (vault save succeeded): {e}")

    return ProcessResult(
        url=url, title=title, content_type=content_type,
        timestamp=timestamp, content=content, summary=summary,
        keywords=keywords, obsidian_markdown=obsidian_md,
        embedding=embedding, file_path=file_path,
    )


def process_url(url: str, db: Database, save: bool = True) -> ProcessResult:
    """Process a URL end-to-end: extract, summarize, embed, save."""
    url = clean_url(url)
    content_type = detect_content_type(url)
    logger.info(f"Processing [{content_type}]: {url}")

    content, title = extract_content(url)
    logger.info(f"Extracted: {title} ({len(content)} chars)")

    return _process_content(url, title, content, content_type, db, save)


def process_text(
    url: str, content: str, db: Database,
    title: str | None = None, content_type: str | None = None,
    save: bool = True,
) -> ProcessResult:
    """Process user-provided text as if it had been scraped from `url`.

    Title and content_type are auto-derived from the URL when omitted.
    """
    url = clean_url(url)
    resolved_type = content_type or detect_content_type(url)
    resolved_title = (title or "").strip() or _title_from_url(url)
    logger.info(f"Processing raw text [{resolved_type}]: {url} ({len(content)} chars)")

    return _process_content(url, resolved_title, content, resolved_type, db, save)
