from datetime import datetime

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.storage import Database
from src.pipeline import process_url
from src.llm import generate_embedding
from src.insights import generate_briefing, save_briefing, detect_trends
from src.research import ask as research_ask, topic_briefing, revisit_suggestions

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _format_doc(doc: dict) -> dict:
    doc = dict(doc)
    ts = doc.get("timestamp", 0)
    doc["date"] = datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else ""
    return doc


def _base_context(request: Request, active: str) -> dict:
    db = Database()
    return {"request": request, "active": active, "doc_count": db.count()}


def _load_latest_briefing() -> dict | None:
    """Load the most recent saved briefing from the vault."""
    import json
    from src.config import VAULT_PATH
    briefings_dir = VAULT_PATH / "_briefings"
    if not briefings_dir.exists():
        return None
    json_files = sorted(briefings_dir.glob("briefing-*.json"), reverse=True)
    if not json_files:
        return None
    try:
        return json.loads(json_files[0].read_text())
    except Exception:
        return None


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    db = Database()
    ctx = _base_context(request, "home")
    docs = db.recent(limit=10)
    ctx["documents"] = [_format_doc(d) for d in docs]
    ctx["top_keywords"] = db.all_keywords(limit=15)
    ctx["briefing"] = _load_latest_briefing()
    ctx["trends"] = detect_trends(db, recent_days=14, baseline_days=90)[:10]
    return templates.TemplateResponse("home.html", ctx)


@router.post("/generate-briefing", response_class=HTMLResponse)
def generate_briefing_ui(request: Request):
    db = Database()
    briefing = generate_briefing(db, days=14)
    if briefing["themes"]:
        save_briefing(briefing)
    return RedirectResponse(url="/", status_code=303)


@router.get("/search", response_class=HTMLResponse)
def search_page(request: Request, query: str = "", mode: str = ""):
    db = Database()
    ctx = _base_context(request, "search")
    ctx["query"] = query
    ctx["mode"] = mode
    ctx["documents"] = []
    ctx["total"] = 0

    if query:
        if mode == "semantic":
            embedding = generate_embedding(query)
            docs = db.search_semantic(embedding, limit=20)
        else:
            docs = db.search_text(query, limit=20)
        ctx["documents"] = [_format_doc(d) for d in docs]
        ctx["total"] = len(docs)

    return templates.TemplateResponse("search.html", ctx)


@router.get("/add", response_class=HTMLResponse)
def add_page(request: Request):
    ctx = _base_context(request, "add")
    ctx["result"] = None
    ctx["error"] = None
    return templates.TemplateResponse("add.html", ctx)


@router.post("/add", response_class=HTMLResponse)
def add_url(request: Request, url: str = Form(...)):
    db = Database()
    ctx = _base_context(request, "add")
    ctx["result"] = None
    ctx["error"] = None

    existing = db.get_by_url(url)
    if existing:
        ctx["error"] = f"URL already processed (id={existing['id']})"
        return templates.TemplateResponse("add.html", ctx)

    try:
        result = process_url(url, db=db, save=True)
        doc = db.get_by_url(url)
        ctx["result"] = {
            "title": result.title,
            "content_type": result.content_type,
            "summary": result.summary,
            "keywords": result.keywords,
            "doc_id": doc["id"] if doc else None,
        }
    except Exception as e:
        ctx["error"] = str(e)

    return templates.TemplateResponse("add.html", ctx)


@router.get("/doc/{doc_id}", response_class=HTMLResponse)
def document_page(request: Request, doc_id: int):
    db = Database()
    ctx = _base_context(request, "")
    doc = db.get(doc_id)
    if not doc:
        ctx["doc"] = {"title": "Not found", "url": "", "summary": "Document not found.",
                       "keywords": [], "content_type": "", "date": ""}
        ctx["similar"] = []
        return templates.TemplateResponse("document.html", ctx)

    ctx["doc"] = _format_doc(doc)
    similar = db.find_similar(doc_id, limit=5)
    ctx["similar"] = [_format_doc(s) for s in similar]
    return templates.TemplateResponse("document.html", ctx)


@router.get("/ask", response_class=HTMLResponse)
def ask_page(request: Request, question: str = ""):
    db = Database()
    ctx = _base_context(request, "ask")
    ctx["question"] = question
    ctx["answer"] = None
    ctx["revisit"] = revisit_suggestions(db, recent_days=14, limit=5)

    if question:
        ctx["answer"] = research_ask(question, db)

    return templates.TemplateResponse("ask.html", ctx)


@router.get("/topic", response_class=HTMLResponse)
def topic_page(request: Request, topic: str = ""):
    ctx = _base_context(request, "topic")
    ctx["briefing"] = None

    if topic:
        db = Database()
        ctx["briefing"] = topic_briefing(topic, db)

    return templates.TemplateResponse("topic.html", ctx)


@router.get("/topics", response_class=HTMLResponse)
def topics_page(request: Request):
    db = Database()
    ctx = _base_context(request, "topics")
    ctx["keywords"] = db.all_keywords(limit=100)
    return templates.TemplateResponse("topics.html", ctx)
