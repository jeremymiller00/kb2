import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4.1-mini")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMENSIONS = 1536

# Obsidian vault path — source of truth, synced across machines via git
VAULT_PATH = Path(os.getenv("DSV_KB_PATH", ""))

# Local SQLite database — a derived index, rebuilt from vault on each machine
PROJECT_DIR = Path(__file__).parent.parent
DB_PATH = PROJECT_DIR / "data" / "knowledge_base.db"

# Vault subdirectories
NOTES_DIR = VAULT_PATH / "_new-notes"
DATA_DIR = VAULT_PATH  # JSON data files live alongside notes in the vault

# API port
API_PORT = int(os.getenv("API_PORT", "8000"))
