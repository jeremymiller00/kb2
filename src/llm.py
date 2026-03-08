import logging
import re

import backoff
import openai

from src.config import OPENAI_API_KEY, LLM_MODEL, EMBEDDING_MODEL
from src.prompts import SUMMARY_SYSTEM, SUMMARY_TEMPLATES, KEYWORD_PROMPT

logger = logging.getLogger(__name__)

MAX_INPUT_WORDS = 100_000
MAX_OUTPUT_TOKENS = 1024

client = openai.OpenAI(api_key=OPENAI_API_KEY)


def _truncate(text: str, max_words: int = MAX_INPUT_WORDS) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    logger.info(f"Truncating input from {len(words)} to {max_words} words")
    return " ".join(words[:max_words])


@backoff.on_exception(backoff.expo, openai.RateLimitError, max_tries=3)
def _chat(system: str, user: str) -> str:
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=MAX_OUTPUT_TOKENS,
    )
    return response.choices[0].message.content.strip()


@backoff.on_exception(backoff.expo, openai.RateLimitError, max_tries=3)
def generate_embedding(text: str) -> list[float]:
    text = _truncate(text, max_words=8000)
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
    )
    return response.data[0].embedding


def generate_summary(content: str, content_type: str = "general") -> str:
    template = SUMMARY_TEMPLATES.get(content_type, SUMMARY_TEMPLATES["general"])
    prompt = template.format(content=_truncate(content))
    return _chat(SUMMARY_SYSTEM, prompt)


def extract_keywords(summary: str) -> list[str]:
    prompt = KEYWORD_PROMPT.format(summary=summary)
    raw = _chat(SUMMARY_SYSTEM, prompt)
    keywords = [kw.strip().lower().lstrip("#") for kw in raw.split(",")]
    return [kw for kw in keywords if kw and len(kw) < 50]


def generate_obsidian_markdown(title: str, summary: str, keywords: list[str],
                                url: str, date: str,
                                content_type: str = "general") -> str:
    # Build frontmatter programmatically for consistency
    title_tag = re.sub(r'[^a-z0-9\s-]', '', title.lower())
    title_tag = re.sub(r'\s+', '-', title_tag).strip('-')

    tags = ["literature-note"]
    if title_tag:
        tags.append(title_tag)
    tags.extend(keywords)

    tag_lines = "\n".join(f"  - {tag}" for tag in tags)

    frontmatter = (
        f"---\n"
        f"url: {url}\n"
        f"type: {content_type}\n"
        f"tags:\n"
        f"{tag_lines}\n"
        f"created: {date}T00:00\n"
        f"updated: {date}T00:00\n"
        f"---"
    )

    body = f"# {title}\n\n{summary}"

    return f"{frontmatter}\n\n{body}"
