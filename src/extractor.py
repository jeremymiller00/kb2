import logging
import re
from urllib.parse import urlparse, urlencode, parse_qs

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "source", "fbclid", "gclid", "mc_cid", "mc_eid",
}


def clean_url(url: str) -> str:
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    cleaned = {k: v for k, v in params.items() if k.lower() not in TRACKING_PARAMS}
    clean_query = urlencode(cleaned, doseq=True)
    return parsed._replace(query=clean_query, fragment="").geturl()


def detect_content_type(url: str) -> str:
    host = urlparse(url).hostname or ""
    path = urlparse(url).path or ""
    if "arxiv.org" in host:
        return "arxiv"
    if "github.com" in host and path.endswith(".ipynb"):
        return "github_notebook"
    if "github.com" in host:
        return "github"
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    if "huggingface.co" in host:
        return "huggingface"
    return "general"


def extract_content(url: str) -> tuple[str, str]:
    """Extract text content and title from a URL.
    Returns (content, title).
    """
    jina_url = f"https://r.jina.ai/{url}"
    headers = {"Accept": "text/markdown"}

    try:
        resp = requests.get(jina_url, headers=headers, timeout=30)
        resp.raise_for_status()
        text = resp.text

        title = _extract_title_from_markdown(text) or _extract_title_from_url(url)
        return text, title

    except requests.RequestException:
        logger.info("Jina extraction failed, falling back to direct fetch")

    try:
        resp = requests.get(url, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        })
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        title = soup.title.string.strip() if soup.title and soup.title.string else _extract_title_from_url(url)
        text = soup.get_text(separator="\n", strip=True)
        return text, title

    except requests.RequestException as e:
        raise RuntimeError(f"Failed to extract content from {url}: {e}")


def _extract_title_from_markdown(text: str) -> str | None:
    for line in text.split("\n")[:20]:
        line = line.strip()
        if line.startswith("# ") and not line.startswith("##"):
            return line[2:].strip()
        if line.startswith("Title:"):
            return line[6:].strip()
    return None


def _extract_title_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    if path:
        slug = path.split("/")[-1]
        return slug.replace("-", " ").replace("_", " ").title()
    return urlparse(url).hostname or "Untitled"
