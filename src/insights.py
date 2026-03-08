"""Insight engine: clustering, theme extraction, briefing generation, pattern detection.

Turns a collection of saved articles into actionable intelligence:
- Clusters recent content into themes
- Detects emerging topics over time
- Generates synthesized briefings via LLM
"""
import json
import logging
import struct
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage

from src.config import VAULT_PATH
from src.storage import Database, _deserialize_embedding

logger = logging.getLogger(__name__)

BRIEFINGS_DIR = VAULT_PATH / "_briefings"


def _get_embeddings_for_docs(db: Database, doc_ids: list[int]) -> dict[int, np.ndarray]:
    """Load embeddings for a set of document IDs."""
    with db._get_conn() as conn:
        placeholders = ",".join("?" * len(doc_ids))
        rows = conn.execute(
            f"SELECT document_id, vector FROM embeddings WHERE document_id IN ({placeholders})",
            doc_ids
        ).fetchall()
    return {
        row["document_id"]: np.array(_deserialize_embedding(row["vector"]), dtype=np.float32)
        for row in rows
    }


def _cosine_similarity_matrix(vectors: np.ndarray) -> np.ndarray:
    """Compute pairwise cosine similarity matrix."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    normalized = vectors / norms
    return normalized @ normalized.T


def cluster_documents(docs: list[dict], embeddings: dict[int, np.ndarray],
                      distance_threshold: float = 0.6) -> list[list[dict]]:
    """Cluster documents by embedding similarity using hierarchical clustering.
    Returns list of clusters, each cluster is a list of docs.
    """
    if len(docs) < 2:
        return [docs] if docs else []

    doc_ids = [d["id"] for d in docs]
    vectors = []
    valid_docs = []
    for doc in docs:
        if doc["id"] in embeddings:
            vectors.append(embeddings[doc["id"]])
            valid_docs.append(doc)

    if len(valid_docs) < 2:
        return [valid_docs] if valid_docs else []

    matrix = np.array(vectors)
    sim_matrix = _cosine_similarity_matrix(matrix)
    # Convert similarity to distance (1 - similarity)
    dist_matrix = 1 - sim_matrix
    np.fill_diagonal(dist_matrix, 0)
    dist_matrix = np.clip(dist_matrix, 0, None)

    # Condensed distance matrix for scipy
    from scipy.spatial.distance import squareform
    condensed = squareform(dist_matrix)

    Z = linkage(condensed, method="average")
    labels = fcluster(Z, t=distance_threshold, criterion="distance")

    clusters: dict[int, list[dict]] = {}
    for doc, label in zip(valid_docs, labels):
        clusters.setdefault(int(label), []).append(doc)

    # Sort clusters by size (largest first)
    return sorted(clusters.values(), key=len, reverse=True)


def generate_briefing(db: Database, days: int = 14,
                      min_cluster_size: int = 2) -> dict:
    """Generate a briefing from recent content.

    Clusters recent articles, generates theme summaries, and finds
    connections to older content.
    """
    from src.llm import _chat, generate_embedding

    cutoff = int((datetime.now() - timedelta(days=days)).timestamp())
    with db._get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM documents WHERE timestamp >= ? ORDER BY timestamp DESC",
            (cutoff,)
        ).fetchall()

    docs = []
    for row in rows:
        doc = dict(row)
        doc["keywords"] = db._get_keywords(conn, doc["id"])
        docs.append(doc)

    if not docs:
        return {"themes": [], "period": f"last {days} days", "document_count": 0}

    embeddings = _get_embeddings_for_docs(db, [d["id"] for d in docs])
    clusters = cluster_documents(docs, embeddings)

    themes = []
    for cluster in clusters:
        if len(cluster) < min_cluster_size:
            continue

        summaries = "\n---\n".join(
            f"Title: {d['title']}\nSummary: {d['summary']}"
            for d in cluster[:10]  # cap at 10 per cluster for LLM context
        )

        theme_prompt = (
            f"You are analyzing a cluster of {len(cluster)} related articles. "
            "Generate a JSON response with these fields:\n"
            '- "theme": a concise theme label (3-6 words)\n'
            '- "synthesis": a 2-3 sentence synthesis of what these articles collectively say\n'
            '- "key_insight": the single most important takeaway\n'
            '- "questions": 1-2 questions this raises for further exploration\n\n'
            f"Articles:\n{summaries}"
        )

        try:
            raw = _chat("You are a research analyst. Return valid JSON only.", theme_prompt)
            # Strip markdown code fences if present
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1]
                if raw.endswith("```"):
                    raw = raw[:-3]
            theme_data = json.loads(raw)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Failed to parse theme JSON: {e}")
            all_keywords = []
            for d in cluster:
                all_keywords.extend(d.get("keywords", []))
            top_kw = Counter(all_keywords).most_common(3)
            theme_data = {
                "theme": " / ".join(k for k, _ in top_kw) or "Mixed Topics",
                "synthesis": f"A cluster of {len(cluster)} related articles.",
                "key_insight": cluster[0].get("summary", "")[:100],
                "questions": [],
            }

        # Find connections to older content
        cluster_embedding = np.mean(
            [embeddings[d["id"]] for d in cluster if d["id"] in embeddings],
            axis=0
        ).tolist()
        older = db.search_semantic(cluster_embedding, limit=3)
        older_docs = [d for d in older if d["timestamp"] < cutoff]

        themes.append({
            "theme": theme_data.get("theme", ""),
            "synthesis": theme_data.get("synthesis", ""),
            "key_insight": theme_data.get("key_insight", ""),
            "questions": theme_data.get("questions", []),
            "article_count": len(cluster),
            "articles": [
                {"id": d["id"], "title": d["title"], "url": d["url"]}
                for d in cluster
            ],
            "connections": [
                {"id": d["id"], "title": d["title"], "similarity": d.get("similarity", 0)}
                for d in older_docs[:3]
            ],
        })

    briefing = {
        "generated_at": datetime.now().isoformat(),
        "period": f"last {days} days",
        "document_count": len(docs),
        "theme_count": len(themes),
        "themes": themes,
    }

    return briefing


def save_briefing(briefing: dict) -> str:
    """Save briefing as JSON and Obsidian note in the vault."""
    BRIEFINGS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")

    # Save JSON
    json_path = BRIEFINGS_DIR / f"briefing-{date_str}.json"
    json_path.write_text(json.dumps(briefing, indent=2))

    # Save Obsidian markdown
    md_lines = [
        "---",
        f"date: {date_str}",
        f"type: briefing",
        f"documents: {briefing['document_count']}",
        f"themes: {briefing['theme_count']}",
        "---",
        "",
        f"# Weekly Briefing - {date_str}",
        "",
        f"*{briefing['document_count']} documents analyzed across {briefing['period']}*",
        "",
    ]

    for i, theme in enumerate(briefing["themes"], 1):
        md_lines.extend([
            f"## {i}. {theme['theme']}",
            "",
            f"**{theme['article_count']} articles**",
            "",
            theme["synthesis"],
            "",
            f"> **Key insight:** {theme['key_insight']}",
            "",
        ])

        if theme.get("questions"):
            questions = theme["questions"]
            if isinstance(questions, list):
                for q in questions:
                    md_lines.append(f"- {q}")
            else:
                md_lines.append(f"- {questions}")
            md_lines.append("")

        if theme.get("articles"):
            md_lines.append("**Articles:**")
            for a in theme["articles"]:
                md_lines.append(f"- [{a['title']}]({a['url']})")
            md_lines.append("")

        if theme.get("connections"):
            md_lines.append("**Connections to earlier reading:**")
            for c in theme["connections"]:
                sim_pct = f"{c['similarity'] * 100:.0f}%" if c.get("similarity") else ""
                md_lines.append(f"- {c['title']} ({sim_pct})")
            md_lines.append("")

    md_path = BRIEFINGS_DIR / f"briefing-{date_str}.md"
    md_path.write_text("\n".join(md_lines))

    logger.info(f"Saved briefing: {json_path}")
    return str(json_path)


def detect_trends(db: Database, recent_days: int = 14,
                  baseline_days: int = 90) -> list[dict]:
    """Detect emerging topics by comparing recent keyword frequency to baseline."""
    now = int(time.time())
    recent_cutoff = now - (recent_days * 86400)
    baseline_cutoff = now - (baseline_days * 86400)

    with db._get_conn() as conn:
        # Recent keyword counts
        recent_rows = conn.execute(
            """SELECT k.keyword, COUNT(*) as count
               FROM keywords k JOIN documents d ON k.document_id = d.id
               WHERE d.timestamp >= ?
               GROUP BY LOWER(k.keyword) ORDER BY count DESC""",
            (recent_cutoff,)
        ).fetchall()

        # Baseline keyword counts
        baseline_rows = conn.execute(
            """SELECT k.keyword, COUNT(*) as count
               FROM keywords k JOIN documents d ON k.document_id = d.id
               WHERE d.timestamp >= ? AND d.timestamp < ?
               GROUP BY LOWER(k.keyword) ORDER BY count DESC""",
            (baseline_cutoff, recent_cutoff)
        ).fetchall()

    recent = {r["keyword"]: r["count"] for r in recent_rows}
    baseline = {r["keyword"]: r["count"] for r in baseline_rows}
    baseline_days_actual = max(baseline_days - recent_days, 1)

    trends = []
    for keyword, recent_count in recent.items():
        baseline_count = baseline.get(keyword, 0)
        # Normalize to per-week rate
        recent_rate = recent_count / max(recent_days / 7, 1)
        baseline_rate = baseline_count / max(baseline_days_actual / 7, 1)

        if recent_rate > baseline_rate and recent_count >= 2:
            acceleration = recent_rate / max(baseline_rate, 0.1)
            trends.append({
                "keyword": keyword,
                "recent_count": recent_count,
                "baseline_count": baseline_count,
                "acceleration": round(acceleration, 1),
                "status": "emerging" if baseline_count == 0 else "accelerating",
            })

    trends.sort(key=lambda t: t["acceleration"], reverse=True)
    return trends[:20]


def get_topic_timeline(db: Database, keyword: str, months: int = 6) -> list[dict]:
    """Get document count per week for a given keyword over time."""
    cutoff = int((datetime.now() - timedelta(days=months * 30)).timestamp())

    with db._get_conn() as conn:
        rows = conn.execute(
            """SELECT d.timestamp FROM documents d
               JOIN keywords k ON k.document_id = d.id
               WHERE LOWER(k.keyword) = LOWER(?) AND d.timestamp >= ?
               ORDER BY d.timestamp""",
            (keyword, cutoff)
        ).fetchall()

    # Group by week
    weeks: dict[str, int] = {}
    for row in rows:
        dt = datetime.fromtimestamp(row["timestamp"])
        week_start = dt - timedelta(days=dt.weekday())
        week_key = week_start.strftime("%Y-%m-%d")
        weeks[week_key] = weeks.get(week_key, 0) + 1

    return [{"week": k, "count": v} for k, v in sorted(weeks.items())]
