from fastapi import APIRouter, HTTPException, Query

from src.models import ProcessRequest, ProcessResult, Document, SearchResult
from src.storage import Database
from src.pipeline import process_url
from src.llm import generate_embedding

router = APIRouter()


def get_db() -> Database:
    return Database()


@router.post("/process", response_model=ProcessResult)
def process_content(req: ProcessRequest):
    """Process a URL: extract, summarize, embed, save."""
    db = get_db()
    existing = db.get_by_url(req.url)
    if existing:
        raise HTTPException(status_code=409, detail=f"URL already processed (id={existing['id']})")
    return process_url(req.url, db=db, save=req.save)


@router.get("/documents", response_model=list[Document])
def list_documents(limit: int = Query(20, ge=1, le=100)):
    """List recent documents."""
    db = get_db()
    docs = db.recent(limit=limit)
    return [_to_document(d) for d in docs]


@router.get("/documents/{doc_id}", response_model=Document)
def get_document(doc_id: int):
    """Get a specific document."""
    db = get_db()
    doc = db.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return _to_document(doc)


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int):
    """Delete a document from the index."""
    db = get_db()
    if not db.delete(doc_id):
        raise HTTPException(status_code=404, detail="Document not found")
    return {"deleted": doc_id}


@router.get("/search", response_model=SearchResult)
def search(query: str = Query(..., min_length=1), limit: int = Query(20, ge=1, le=100)):
    """Search documents by text."""
    db = get_db()
    docs = db.search_text(query, limit=limit)
    return SearchResult(
        documents=[_to_document(d) for d in docs],
        query=query,
        total=len(docs),
    )


@router.get("/search/semantic", response_model=SearchResult)
def search_semantic(query: str = Query(..., min_length=1), limit: int = Query(20, ge=1, le=100)):
    """Search documents by semantic similarity."""
    db = get_db()
    query_embedding = generate_embedding(query)
    docs = db.search_semantic(query_embedding, limit=limit)
    return SearchResult(
        documents=[_to_document(d) for d in docs],
        query=query,
        total=len(docs),
    )


@router.get("/documents/{doc_id}/similar", response_model=list[Document])
def find_similar(doc_id: int, limit: int = Query(10, ge=1, le=50)):
    """Find documents similar to a given document."""
    db = get_db()
    if not db.get(doc_id):
        raise HTTPException(status_code=404, detail="Document not found")
    docs = db.find_similar(doc_id, limit=limit)
    return [_to_document(d) for d in docs]


@router.get("/keywords")
def top_keywords(limit: int = Query(50, ge=1, le=200)):
    """Get top keywords by frequency."""
    db = get_db()
    return db.all_keywords(limit=limit)


@router.get("/status")
def status():
    """Health check with stats."""
    db = get_db()
    return {"status": "ok", "document_count": db.count()}


def _to_document(d: dict) -> Document:
    return Document(
        id=d["id"],
        url=d["url"],
        title=d["title"],
        content_type=d["content_type"],
        timestamp=d["timestamp"],
        summary=d.get("summary", ""),
        keywords=d.get("keywords", []),
        similarity=d.get("similarity"),
    )
