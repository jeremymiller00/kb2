from fastapi import APIRouter, Query

from src.storage import Database
from src.research import ask, topic_briefing, suggest_connections, revisit_suggestions

router = APIRouter()


def get_db() -> Database:
    return Database()


@router.get("/ask")
def ask_question(question: str = Query(..., min_length=1),
                 top_k: int = Query(8, ge=1, le=20),
                 full_content: bool = Query(False)):
    """Ask a question answered by your personal corpus (RAG)."""
    db = get_db()
    return ask(question, db, top_k=top_k, use_full_content=full_content)


@router.get("/topic/{topic}")
def get_topic_briefing(topic: str, top_k: int = Query(15, ge=1, le=30)):
    """Generate a structured briefing on a topic from your saved content."""
    db = get_db()
    return topic_briefing(topic, db, top_k=top_k)


@router.get("/connections/{doc_id}")
def get_connections(doc_id: int, limit: int = Query(5, ge=1, le=20)):
    """Get suggested Obsidian note connections for a document."""
    db = get_db()
    return suggest_connections(doc_id, db, limit=limit)


@router.get("/revisit")
def get_revisit_suggestions(recent_days: int = Query(14, ge=1, le=90),
                            limit: int = Query(5, ge=1, le=20)):
    """Surface older notes to revisit based on relevance to recent reading."""
    db = get_db()
    return revisit_suggestions(db, recent_days=recent_days, limit=limit)
