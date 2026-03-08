from pydantic import BaseModel
from typing import Optional


class ProcessRequest(BaseModel):
    url: str
    save: bool = True


class ProcessResult(BaseModel):
    url: str
    title: str
    content_type: str
    timestamp: int
    content: str
    summary: str
    keywords: list[str]
    obsidian_markdown: str
    embedding: list[float]
    file_path: Optional[str] = None


class Document(BaseModel):
    id: int
    url: str
    title: str
    content_type: str
    timestamp: int
    summary: str
    keywords: list[str]
    similarity: Optional[float] = None


class SearchResult(BaseModel):
    documents: list[Document]
    query: str
    total: int
