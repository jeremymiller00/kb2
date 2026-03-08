"""Research assistant: RAG over personal corpus, topic briefings, note suggestions.

Answers questions grounded in your saved content, generates topic briefings
for meetings, and suggests Obsidian note connections.
"""
import json
import logging
from datetime import datetime
from pathlib import Path

from src.config import VAULT_PATH
from src.llm import generate_embedding, _chat
from src.storage import Database
from src.vault import load_json

logger = logging.getLogger(__name__)


def _load_full_content(doc: dict) -> str:
    """Load full content from the vault JSON file for a document."""
    json_path = doc.get("json_path")
    if not json_path:
        return doc.get("summary", "")
    path = Path(json_path)
    if not path.exists():
        return doc.get("summary", "")
    data = load_json(path)
    if data and data.get("content"):
        # Truncate very long content to keep LLM context manageable
        content = data["content"]
        words = content.split()
        if len(words) > 2000:
            content = " ".join(words[:2000]) + "..."
        return content
    return doc.get("summary", "")


def ask(question: str, db: Database, top_k: int = 8,
        use_full_content: bool = False) -> dict:
    """Answer a question using RAG over the personal corpus.

    1. Embed the question
    2. Find top-K similar documents
    3. Build context from their summaries (or full content)
    4. Ask the LLM to answer grounded in sources
    """
    query_embedding = generate_embedding(question)
    results = db.search_semantic(query_embedding, limit=top_k)

    if not results:
        return {
            "answer": "I don't have enough saved content to answer this question.",
            "sources": [],
            "query": question,
        }

    # Build context from sources
    context_parts = []
    sources = []
    for i, doc in enumerate(results, 1):
        if use_full_content:
            text = _load_full_content(doc)
        else:
            text = doc.get("summary", "")

        context_parts.append(
            f"[Source {i}] {doc['title']}\n"
            f"URL: {doc['url']}\n"
            f"Content: {text}\n"
        )
        sources.append({
            "id": doc["id"],
            "title": doc["title"],
            "url": doc["url"],
            "similarity": doc.get("similarity", 0),
            "keywords": doc.get("keywords", []),
        })

    context = "\n---\n".join(context_parts)

    prompt = (
        f"You are a research assistant with access to the user's personal knowledge base. "
        f"Answer the following question using ONLY the provided sources. "
        f"Cite sources by number [1], [2], etc. "
        f"If the sources don't fully answer the question, say what they do cover "
        f"and what gaps remain.\n\n"
        f"Question: {question}\n\n"
        f"Sources:\n{context}"
    )

    answer = _chat(
        "You are a helpful research assistant. Be concise and cite your sources.",
        prompt
    )

    return {
        "answer": answer,
        "sources": sources,
        "query": question,
    }


def topic_briefing(topic: str, db: Database, top_k: int = 15) -> dict:
    """Generate a structured briefing on a topic from the personal corpus.

    Use case: "Get me smart on [topic] for a meeting tomorrow."
    """
    query_embedding = generate_embedding(topic)
    results = db.search_semantic(query_embedding, limit=top_k)

    if not results:
        return {
            "topic": topic,
            "briefing": f"No saved content found related to '{topic}'.",
            "sources": [],
            "gaps": [f"Consider searching for articles about {topic}."],
        }

    # Build context
    summaries = "\n---\n".join(
        f"[{i}] {doc['title']}\n"
        f"Keywords: {', '.join(doc.get('keywords', [])[:5])}\n"
        f"Summary: {doc.get('summary', '')}"
        for i, doc in enumerate(results, 1)
    )

    prompt = (
        f"You are preparing a briefing document on the topic: \"{topic}\"\n\n"
        f"Using the following sources from the user's personal knowledge base, "
        f"generate a JSON response with:\n"
        f'- "overview": 2-3 sentence overview of what the user knows about this topic\n'
        f'- "key_points": list of 3-5 key points, each with "point" and "source_nums" fields\n'
        f'- "perspectives": any contrasting or complementary viewpoints across sources\n'
        f'- "gaps": areas where the user\'s saved content is thin and they might want to read more\n'
        f'- "talking_points": 3-4 bullet points they could use in a meeting\n\n'
        f"Sources:\n{summaries}"
    )

    try:
        raw = _chat(
            "You are a research analyst. Return valid JSON only.",
            prompt
        )
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3]
        briefing_data = json.loads(raw)
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"Failed to parse topic briefing JSON: {e}")
        briefing_data = {
            "overview": f"Found {len(results)} relevant articles about {topic}.",
            "key_points": [],
            "perspectives": "",
            "gaps": [],
            "talking_points": [],
        }

    sources = [
        {
            "id": doc["id"],
            "title": doc["title"],
            "url": doc["url"],
            "similarity": doc.get("similarity", 0),
        }
        for doc in results
    ]

    return {
        "topic": topic,
        "overview": briefing_data.get("overview", ""),
        "key_points": briefing_data.get("key_points", []),
        "perspectives": briefing_data.get("perspectives", ""),
        "gaps": briefing_data.get("gaps", []),
        "talking_points": briefing_data.get("talking_points", []),
        "sources": sources,
        "source_count": len(sources),
    }


def suggest_connections(doc_id: int, db: Database, limit: int = 5) -> list[dict]:
    """Suggest Obsidian note connections for a document based on semantic similarity."""
    similar = db.find_similar(doc_id, limit=limit)
    return [
        {
            "id": d["id"],
            "title": d["title"],
            "url": d["url"],
            "similarity": d.get("similarity", 0),
            "shared_keywords": list(
                set(d.get("keywords", [])) &
                set(db.get(doc_id).get("keywords", []))
            ) if db.get(doc_id) else [],
        }
        for d in similar
    ]


def revisit_suggestions(db: Database, recent_days: int = 14, limit: int = 5) -> list[dict]:
    """Surface older notes the user should revisit based on relevance to recent reading.

    Finds the centroid of recent reading, then searches for older documents
    that are semantically similar but haven't been read recently.
    """
    import time
    import numpy as np
    from src.storage import _deserialize_embedding

    now = int(time.time())
    recent_cutoff = now - (recent_days * 86400)
    older_cutoff = now - (90 * 86400)  # At least 90 days old

    # Get recent document embeddings
    with db._get_conn() as conn:
        recent_ids = conn.execute(
            "SELECT id FROM documents WHERE timestamp >= ?", (recent_cutoff,)
        ).fetchall()
        recent_ids = [r["id"] for r in recent_ids]

    if not recent_ids:
        return []

    # Compute centroid of recent reading
    with db._get_conn() as conn:
        rows = conn.execute(
            f"SELECT vector FROM embeddings WHERE document_id IN ({','.join('?' * len(recent_ids))})",
            recent_ids
        ).fetchall()

    if not rows:
        return []

    vectors = [np.array(_deserialize_embedding(r["vector"]), dtype=np.float32) for r in rows]
    centroid = np.mean(vectors, axis=0).tolist()

    # Search for older documents similar to the centroid
    all_similar = db.search_semantic(centroid, limit=limit + len(recent_ids))

    # Filter to only older documents
    revisit = [
        d for d in all_similar
        if d["timestamp"] < older_cutoff and d["id"] not in recent_ids
    ][:limit]

    return [
        {
            "id": d["id"],
            "title": d["title"],
            "url": d["url"],
            "similarity": d.get("similarity", 0),
            "keywords": d.get("keywords", [])[:5],
            "date": datetime.fromtimestamp(d["timestamp"]).strftime("%Y-%m-%d"),
        }
        for d in revisit
    ]
