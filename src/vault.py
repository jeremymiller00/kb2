"""Obsidian vault integration.

The vault is the source of truth, synced across machines via git.
JSON data files (with embeddings) live in date-organized subdirectories.
Obsidian markdown notes go into _new-notes/.

The local SQLite database is a derived index that can be rebuilt from vault data.
"""
import hashlib
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path

from src.config import VAULT_PATH, NOTES_DIR, DATA_DIR

logger = logging.getLogger(__name__)


def _sanitize_filename(title: str, max_len: int = 80) -> str:
    name = re.sub(r'[<>:"/\\|?*]', '', title)
    name = re.sub(r'\s+', ' ', name).strip()
    if len(name) > max_len:
        name = name[:max_len].rsplit(' ', 1)[0]
    return name


def _daily_dir() -> Path:
    d = DATA_DIR / datetime.now().strftime("%Y-%m-%d")
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_json(url: str, title: str, content_type: str, content: str,
              summary: str, keywords: list[str], obsidian_markdown: str,
              embedding: list[float]) -> str:
    """Save processed content as JSON in the vault. Returns the file path."""
    timestamp = int(time.time())
    data = {
        "url": url,
        "title": title,
        "type": content_type,
        "timestamp": timestamp,
        "content": content,
        "summary": summary,
        "keywords": keywords,
        "obsidian_markdown": obsidian_markdown,
        "embedding": embedding,
        "content_hash": hashlib.md5(content.encode()).hexdigest(),
    }

    filename = _sanitize_filename(title) + ".json"
    file_path = _daily_dir() / filename
    file_path.write_text(json.dumps(data, indent=2))
    logger.info(f"Saved JSON: {file_path}")
    return str(file_path)


def save_obsidian_note(title: str, obsidian_markdown: str) -> str:
    """Save an Obsidian markdown note. Returns the file path."""
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    filename = _sanitize_filename(title) + ".md"
    file_path = NOTES_DIR / filename
    file_path.write_text(obsidian_markdown)
    logger.info(f"Saved Obsidian note: {file_path}")
    return str(file_path)


def scan_json_files() -> list[Path]:
    """Find all JSON data files in the vault for index rebuilding."""
    if not DATA_DIR.exists():
        return []
    return sorted(DATA_DIR.rglob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def _title_from_url(url: str) -> str:
    from urllib.parse import urlparse
    path = urlparse(url).path.rstrip("/")
    if path:
        slug = path.split("/")[-1]
        return slug.replace("-", " ").replace("_", " ").title()
    return urlparse(url).hostname or "Untitled"


def _normalize_keywords(keywords: list) -> list[str]:
    """Handle both plain keywords and Obsidian [[keyword]] format."""
    result = []
    for kw in keywords:
        if not isinstance(kw, str):
            continue
        kw = kw.strip().strip("[]").strip()
        kw = re.sub(r'\[\[|\]\]', '', kw).strip()
        if kw:
            result.append(kw.lower())
    return result


def load_json(path: Path) -> dict | None:
    """Load and validate a JSON data file from the vault.
    Handles both old format (embeddings, no title) and new format (embedding, title).
    """
    try:
        data = json.loads(path.read_text())

        required = {"url", "type", "timestamp", "summary", "keywords"}
        if not required.issubset(data.keys()):
            logger.warning(f"Skipping incomplete JSON {path}")
            return None

        # Normalize: old format uses "embeddings", new uses "embedding"
        if "embeddings" in data and "embedding" not in data:
            data["embedding"] = data.pop("embeddings")

        embedding = data.get("embedding")
        if not isinstance(embedding, list) or len(embedding) == 0:
            logger.warning(f"Skipping JSON with invalid embedding {path}")
            return None

        # Derive title if missing
        if "title" not in data or not data["title"]:
            data["title"] = _title_from_url(data["url"])

        # Normalize keywords
        data["keywords"] = _normalize_keywords(data["keywords"])

        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Skipping invalid JSON {path}: {e}")
        return None
