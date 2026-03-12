"""Rebuild the local SQLite index from vault JSON files.

Run this on a new machine after cloning the Obsidian vault,
or any time you want to resync the index.

Usage:
    python -m scripts.rebuild_index
    python -m scripts.rebuild_index --clear  # wipe and rebuild from scratch
"""
import argparse
import hashlib
import logging
import sys
import time
from pathlib import Path

from src.config import VAULT_PATH

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "kb.log"),
    ],
)
from src.storage import Database
from src.vault import scan_json_files, load_json


def rebuild(clear: bool = False):
    print(f"Vault path: {VAULT_PATH}")
    if not VAULT_PATH.exists():
        print(f"ERROR: Vault path does not exist: {VAULT_PATH}")
        sys.exit(1)

    db = Database()

    if clear:
        print("Clearing existing index...")
        db.clear()

    json_files = scan_json_files()
    print(f"Found {len(json_files)} JSON files in vault")

    indexed = 0
    skipped = 0
    errors = 0
    start = time.time()

    for i, path in enumerate(json_files, 1):
        data = load_json(path)
        if not data:
            skipped += 1
            continue

        try:
            content = data.get("content", "")
            content_hash = hashlib.md5(content.encode()).hexdigest() if content else ""

            db.store(
                url=data["url"],
                title=data["title"],
                content_type=data["type"],
                timestamp=data["timestamp"],
                summary=data["summary"],
                keywords=data["keywords"],
                embedding=data["embedding"],
                content_hash=content_hash,
                json_path=str(path),
            )
            indexed += 1
        except Exception as e:
            print(f"  Error indexing {path.name}: {e}")
            errors += 1

        if i % 100 == 0:
            print(f"  Progress: {i}/{len(json_files)} ({indexed} indexed, {skipped} skipped)")

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s")
    print(f"  Indexed: {indexed}")
    print(f"  Skipped: {skipped}")
    print(f"  Errors:  {errors}")
    print(f"  Total in DB: {db.count()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rebuild SQLite index from vault")
    parser.add_argument("--clear", action="store_true", help="Clear index before rebuilding")
    args = parser.parse_args()
    rebuild(clear=args.clear)
