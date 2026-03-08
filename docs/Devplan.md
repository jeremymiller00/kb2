# Knowledge Base Reimagining: From Content Capture to Personal Intelligence Layer

## Context

### The Problem
This project started as a knowledge management system with ambitious infrastructure (PostgreSQL/pgvector, 6+ content extractors, semantic search, recommendations, retro terminal UI). In practice, **only one workflow delivers value**: paste URL → AI summary → Obsidian note. The database is frequently offline. ArXiv, YouTube, and GitHub extractors have never been used. Semantic search and recommendations are dead code.

The project is 90% plumbing and 10% value delivery. This plan flips that ratio.

### The User
A data science product manager who reads extensively about AI/ML, product management, and leadership. Spends 1-2 hours/week in a dedicated review session. Lives in Obsidian for daily thinking and writing.

### The Outcome We're Solving For
**"Help me systematically build expertise in AI/ML by surfacing patterns and connections across everything I consume."**

The capture pipeline works. The gap is the **insight engine** — going from "I saved 1000 articles" to "here's what matters, how it connects, and what I should pay attention to."

### Success Criteria (6-month vision)
The tool acts as a personal intelligence layer:
1. **Proactive briefings** — weekly themes across consumed content with connections to older notes
2. **Smart retrieval** — ask a question, get the most relevant things you've saved with context
3. **Pattern detection** — "you've read 8 articles about AI agents this month, here's what they collectively say"
4. **Research assistant** — topic briefings from personal corpus + live sources

---

## Architecture Decision

**Obsidian = where you read, think, write (daily interface)**
**This tool = intelligence layer that makes your vault smarter (compute engine)**

### Storage: PostgreSQL → SQLite
- SQLite file replaces PostgreSQL server (zero maintenance, no connection issues)
- Embeddings stored in SQLite alongside document metadata
- Vector search via numpy in-memory (sufficient at personal scale) or sqlite-vec
- The Obsidian vault remains source of truth for note content

### Web UI: Article browser → Insight dashboard
- Stop replicating Obsidian's job (browsing/reading articles)
- Start doing what Obsidian can't (briefings, pattern maps, Q&A against corpus)

### Extractors: Simplify
- Keep HTML extractor (covers 90%+ of actual usage)
- Keep the extractor factory pattern but remove unused extractors until demand is proven
- If ArXiv/YouTube/GitHub are needed later, re-add them

---

## Implementation Phases

### Phase 1: Reliable Foundation (weeks 1-2)
**Goal:** The capture pipeline never fails. Every article has searchable embeddings.

1. **Replace PostgreSQL with SQLite**
   - New `storage/sqlite_db.py` implementing same interface as current `database.py`
   - Schema: documents (id, url, type, timestamp, title, summary, content_hash), keywords (id, doc_id, keyword), embeddings (doc_id, vector BLOB)
   - Migration script to import existing JSON files into SQLite
   - Drop pgvector dependency from requirements

2. **Harden the capture pipeline**
   - Ensure URL → extract → summarize → embed → save always completes
   - Obsidian note creation + SQLite save should both succeed independently
   - Better error handling and retry logic for LLM calls

3. **Working semantic search**
   - Load embeddings from SQLite into numpy array
   - Cosine similarity search endpoint that actually works
   - Simple search UI in the web interface

4. **Remove dead code**
   - Unused extractors (ArXiv, YouTube, GitHub, HuggingFace, Jupyter) — archive, don't delete permanently
   - CLI remnants
   - PostgreSQL-specific code

**Key files to modify:**
- `storage/database.py` → replace with SQLite implementation
- `routes/content.py` → simplify, ensure reliability
- `requirements.txt` → remove psycopg2, pgvector; add sqlite-vec if needed
- `scripts/build_db.py` → SQLite initialization + JSON migration

### Phase 2: Insight Engine (weeks 3-5)
**Goal:** The tool tells you things you didn't know about what you've read.

1. **Weekly briefing generation**
   - Cluster recent content (last 7-14 days) by embedding similarity
   - For each cluster: generate a theme label and synthesis using LLM
   - Connect clusters to older content ("this relates to things you read about X in January")
   - Output: structured briefing (JSON + Obsidian note in a `_briefings/` folder)

2. **Pattern detection**
   - Track topic frequency over time using keyword/embedding clusters
   - Detect emerging interests ("you've saved 8 articles about AI agents in 3 weeks")
   - Generate synthesis: "across these articles, the key takeaways are..."

3. **Insight dashboard (web UI)**
   - Replace article browser with:
     - Latest briefing summary
     - Trending topics with article counts
     - Semantic search bar
     - "Explore a topic" entry point

**New files:**
- `core/insight_engine.py` — clustering, theme extraction, briefing generation
- `core/pattern_detector.py` — topic tracking, trend detection
- `routes/insights.py` — API endpoints for briefings and patterns
- Updated `routes/ui.py` — insight-focused dashboard

### Phase 3: Research Assistant (weeks 6-8)
**Goal:** Ask questions, get answers grounded in your personal corpus.

1. **RAG over personal corpus**
   - Question → embed → find top-K relevant chunks → LLM synthesis
   - Return answer with source citations (links to Obsidian notes)

2. **Topic briefing generation**
   - "Get me smart on [topic] for a meeting tomorrow"
   - Pulls from personal corpus + optionally live web search
   - Generates structured briefing with key points, your saved sources, and gaps

3. **Obsidian integration enhancement**
   - Generate suggested links between notes based on semantic similarity
   - Surface "notes you should revisit" based on relevance to current reading patterns

**New files:**
- `core/research_assistant.py` — RAG pipeline, briefing generation
- `routes/research.py` — Q&A and briefing endpoints

---

## What We're Descoping

- **Multi-user support** — this is a personal tool
- **ArXiv/YouTube/GitHub extractors** — re-add when there's actual demand
- **Terminal UI for article browsing** — Obsidian does this better
- **Admin/config endpoints** — simplify to config file
- **PostgreSQL support** — clean break to SQLite

---

## Verification Plan

### Phase 1 verification:
- Process 10 URLs end-to-end: all succeed, all appear in SQLite and Obsidian
- Semantic search returns relevant results for 5 test queries
- Start/stop the app 5 times — no database connection errors
- Import existing JSON archive and verify document count matches

### Phase 2 verification:
- Generate a weekly briefing from the last 2 weeks of content
- Verify briefing contains coherent themes with connections to older content
- Pattern detection correctly identifies a topic you've been reading about frequently
- Dashboard loads and displays insights

### Phase 3 verification:
- Ask 5 questions about topics you've saved articles on — get relevant, sourced answers
- Generate a topic briefing — verify it draws from your actual saved content
- Suggested note links in Obsidian are genuinely useful connections
