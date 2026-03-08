from fastapi import APIRouter, Query

from src.storage import Database
from src.insights import generate_briefing, save_briefing, detect_trends, get_topic_timeline

router = APIRouter()


def get_db() -> Database:
    return Database()


@router.post("/briefing")
def create_briefing(days: int = Query(14, ge=1, le=90)):
    """Generate and save a briefing from recent content."""
    db = get_db()
    briefing = generate_briefing(db, days=days)
    if briefing["themes"]:
        save_briefing(briefing)
    return briefing


@router.get("/briefing")
def get_latest_briefing():
    """Get the most recent saved briefing."""
    from src.config import VAULT_PATH
    briefings_dir = VAULT_PATH / "_briefings"
    if not briefings_dir.exists():
        return {"themes": [], "message": "No briefings yet. POST /api/insights/briefing to generate one."}

    import json
    json_files = sorted(briefings_dir.glob("briefing-*.json"), reverse=True)
    if not json_files:
        return {"themes": [], "message": "No briefings yet."}

    return json.loads(json_files[0].read_text())


@router.get("/trends")
def trends(recent_days: int = Query(14, ge=1, le=90),
           baseline_days: int = Query(90, ge=14, le=365)):
    """Detect emerging topics by comparing recent vs. baseline keyword frequency."""
    db = get_db()
    return detect_trends(db, recent_days=recent_days, baseline_days=baseline_days)


@router.get("/topic/{keyword}/timeline")
def topic_timeline(keyword: str, months: int = Query(6, ge=1, le=24)):
    """Get weekly document count for a keyword over time."""
    db = get_db()
    return get_topic_timeline(db, keyword, months=months)
