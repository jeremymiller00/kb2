import json
import sqlite3
import struct
import logging
from pathlib import Path
from typing import Optional

import numpy as np

from src.config import DB_PATH, EMBEDDING_DIMENSIONS

logger = logging.getLogger(__name__)


def _serialize_embedding(embedding: list[float]) -> bytes:
    return struct.pack(f"{len(embedding)}f", *embedding)


def _deserialize_embedding(data: bytes) -> list[float]:
    n = len(data) // 4
    return list(struct.unpack(f"{n}f", data))


class Database:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE,
                    title TEXT,
                    content_type TEXT,
                    timestamp INTEGER,
                    summary TEXT,
                    content_hash TEXT,
                    json_path TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS keywords (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
                    keyword TEXT
                );
                CREATE TABLE IF NOT EXISTS embeddings (
                    document_id INTEGER PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
                    vector BLOB
                );
                CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(content_type);
                CREATE INDEX IF NOT EXISTS idx_documents_timestamp ON documents(timestamp);
                CREATE INDEX IF NOT EXISTS idx_keywords_keyword ON keywords(keyword);
                CREATE INDEX IF NOT EXISTS idx_keywords_doc ON keywords(document_id);
            """)

    def store(self, url: str, title: str, content_type: str, timestamp: int,
              summary: str, keywords: list[str], embedding: list[float],
              content_hash: str, json_path: str) -> int:
        with self._get_conn() as conn:
            cursor = conn.execute(
                """INSERT INTO documents (url, title, content_type, timestamp, summary, content_hash, json_path)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(url) DO UPDATE SET
                     title=excluded.title, summary=excluded.summary,
                     content_hash=excluded.content_hash, json_path=excluded.json_path,
                     timestamp=excluded.timestamp
                   RETURNING id""",
                (url, title, content_type, timestamp, summary, content_hash, json_path)
            )
            doc_id = cursor.fetchone()[0]

            conn.execute("DELETE FROM keywords WHERE document_id = ?", (doc_id,))
            conn.executemany(
                "INSERT INTO keywords (document_id, keyword) VALUES (?, ?)",
                [(doc_id, kw) for kw in keywords]
            )

            conn.execute(
                """INSERT INTO embeddings (document_id, vector) VALUES (?, ?)
                   ON CONFLICT(document_id) DO UPDATE SET vector=excluded.vector""",
                (doc_id, _serialize_embedding(embedding))
            )
            return doc_id

    def get(self, doc_id: int) -> Optional[dict]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
            if not row:
                return None
            doc = dict(row)
            doc["keywords"] = self._get_keywords(conn, doc_id)
            return doc

    def get_by_url(self, url: str) -> Optional[dict]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM documents WHERE url = ?", (url,)).fetchone()
            if not row:
                return None
            doc = dict(row)
            doc["keywords"] = self._get_keywords(conn, doc["id"])
            return doc

    def _get_keywords(self, conn, doc_id: int) -> list[str]:
        rows = conn.execute(
            "SELECT keyword FROM keywords WHERE document_id = ?", (doc_id,)
        ).fetchall()
        return [r["keyword"] for r in rows]

    def search_text(self, query: str, limit: int = 20) -> list[dict]:
        terms = query.lower().split()
        if not terms:
            return []
        where_clauses = []
        params = []
        for term in terms:
            where_clauses.append("(LOWER(d.title) LIKE ? OR LOWER(d.summary) LIKE ?)")
            params.extend([f"%{term}%", f"%{term}%"])

        sql = f"""
            SELECT d.* FROM documents d
            WHERE {' AND '.join(where_clauses)}
            ORDER BY d.timestamp DESC
            LIMIT ?
        """
        params.append(limit)

        with self._get_conn() as conn:
            rows = conn.execute(sql, params).fetchall()
            results = []
            for row in rows:
                doc = dict(row)
                doc["keywords"] = self._get_keywords(conn, doc["id"])
                results.append(doc)
            return results

    def search_semantic(self, query_embedding: list[float], limit: int = 20,
                        exclude_id: Optional[int] = None) -> list[dict]:
        query_vec = np.array(query_embedding, dtype=np.float32)
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            return []
        query_vec = query_vec / query_norm

        with self._get_conn() as conn:
            rows = conn.execute("SELECT document_id, vector FROM embeddings").fetchall()

        scored = []
        for row in rows:
            doc_id = row["document_id"]
            if exclude_id and doc_id == exclude_id:
                continue
            vec = np.array(_deserialize_embedding(row["vector"]), dtype=np.float32)
            norm = np.linalg.norm(vec)
            if norm == 0:
                continue
            similarity = float(np.dot(query_vec, vec / norm))
            scored.append((doc_id, similarity))

        scored.sort(key=lambda x: x[1], reverse=True)
        top_ids = scored[:limit]

        with self._get_conn() as conn:
            results = []
            for doc_id, sim in top_ids:
                row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
                if row:
                    doc = dict(row)
                    doc["keywords"] = self._get_keywords(conn, doc_id)
                    doc["similarity"] = round(sim, 4)
                    results.append(doc)
            return results

    def find_similar(self, doc_id: int, limit: int = 10) -> list[dict]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT vector FROM embeddings WHERE document_id = ?", (doc_id,)
            ).fetchone()
            if not row:
                return []
            embedding = _deserialize_embedding(row["vector"])
        return self.search_semantic(embedding, limit=limit, exclude_id=doc_id)

    def recent(self, limit: int = 20) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM documents ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
            results = []
            for row in rows:
                doc = dict(row)
                doc["keywords"] = self._get_keywords(conn, doc["id"])
                results.append(doc)
            return results

    def count(self) -> int:
        with self._get_conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]

    def all_keywords(self, limit: int = 50) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT keyword, COUNT(*) as count
                   FROM keywords GROUP BY LOWER(keyword)
                   ORDER BY count DESC LIMIT ?""",
                (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def delete(self, doc_id: int) -> bool:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM embeddings WHERE document_id = ?", (doc_id,))
            conn.execute("DELETE FROM keywords WHERE document_id = ?", (doc_id,))
            cursor = conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            return cursor.rowcount > 0

    def clear(self):
        with self._get_conn() as conn:
            conn.executescript("""
                DELETE FROM embeddings;
                DELETE FROM keywords;
                DELETE FROM documents;
            """)
