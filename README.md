# kb

A personal intelligence layer for your reading. Captures web content, generates AI summaries, and surfaces patterns, connections, and insights across everything you consume.

Built for use with an Obsidian vault synced via git. Works across multiple machines.

## How it works

```
You find an article
  → kb extracts, summarizes, and embeds it
  → Saved to your Obsidian vault (JSON + markdown note)
  → Indexed in local SQLite for search

Later:
  → "What do I know about AI evaluation?" → RAG-powered answer with sources
  → "Brief me on product management" → structured briefing with talking points
  → Dashboard shows emerging topics and weekly theme synthesis
```

**Obsidian vault = source of truth** (synced via git, contains embeddings)
**SQLite = local search index** (rebuilt from vault on each machine, ~1s for 1000+ docs)

## Setup

```bash
# Clone the repo
git clone <repo-url> kb2
cd kb2

# Create virtual environment
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your API key and vault path

# Start
./start.sh
# → Rebuilds index if needed, starts server on :8000
```

## Environment variables

```
OPENAI_API_KEY=sk-...                  # Required
DSV_KB_PATH=/path/to/obsidian/vault    # Path to your Obsidian vault, or knowledge base folder within your obsidian vault
LLM_MODEL=gpt-4.1-mini                # Model for summaries/analysis
EMBEDDING_MODEL=text-embedding-3-small # Model for embeddings
API_PORT=8000                          # Server port (optional)
```

## Usage

### Web UI (http://localhost:8000)

| Page | What it does |
|------|-------------|
| **home** | Dashboard: emerging topics, latest briefing, recent articles |
| **search** | Text and semantic search across all documents |
| **ask** | Ask questions answered by your corpus (RAG with source citations) |
| **brief me** | Generate a structured topic briefing with talking points and gaps |
| **add** | Process a new URL |
| **topics** | Browse all keywords by frequency |

### API

**Content**
- `POST /api/process` — process a URL (extract, summarize, embed, save)
- `GET /api/documents` — list recent documents
- `GET /api/search?query=...` — text search
- `GET /api/search/semantic?query=...` — semantic search
- `GET /api/documents/{id}/similar` — find similar documents

**Insights**
- `POST /api/insights/briefing` — generate a weekly briefing (clusters + LLM synthesis)
- `GET /api/insights/briefing` — get latest saved briefing
- `GET /api/insights/trends` — emerging and accelerating topics

**Research**
- `GET /api/research/ask?question=...` — RAG Q&A over your corpus
- `GET /api/research/topic/{topic}` — structured topic briefing
- `GET /api/research/revisit` — older notes worth revisiting
- `GET /api/research/connections/{id}` — suggested note links

### Multi-machine

The Obsidian vault (with JSON data files and embeddings) syncs via git. On a new machine:

```bash
# Your vault is already cloned via git
# Just set DSV_KB_PATH in .env and run:
./start.sh
# SQLite index rebuilds automatically from vault data
```

To manually rebuild the index:
```bash
python -m scripts.rebuild_index          # incremental
python -m scripts.rebuild_index --clear  # full rebuild
```

## Project structure

```
kb2/
├── src/
│   ├── app.py          # FastAPI application
│   ├── config.py       # Environment configuration
│   ├── models.py       # Pydantic models
│   ├── storage.py      # SQLite database (local index)
│   ├── extractor.py    # URL content extraction (Jina + BeautifulSoup)
│   ├── llm.py          # OpenAI integration (summary, keywords, embeddings)
│   ├── prompts.py      # Prompt templates
│   ├── pipeline.py     # URL → extract → summarize → embed → save
│   ├── vault.py        # Obsidian vault integration
│   ├── insights.py     # Clustering, briefings, trend detection
│   ├── research.py     # RAG Q&A, topic briefings, revisit suggestions
│   └── routes/
│       ├── api.py      # Content CRUD and search endpoints
│       ├── insights.py # Briefing and trend endpoints
│       ├── research.py # RAG and topic briefing endpoints
│       └── ui.py       # Web UI pages
├── scripts/
│   └── rebuild_index.py
├── templates/          # Jinja2 HTML templates
├── static/             # CSS
├── data/               # Local SQLite database (gitignored)
├── requirements.txt
└── start.sh
```
