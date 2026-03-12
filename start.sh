#!/bin/bash
cd "$(dirname "$0")"

# Ensure data directory exists
mkdir -p data

# Parse arguments
if [ "$1" = "--rebuild" ]; then
    echo "Force rebuilding database..."
    rm -f data/knowledge_base.db
    python -m scripts.rebuild_index
elif [ ! -f data/knowledge_base.db ]; then
    echo "No local index found. Rebuilding from vault..."
    python -m scripts.rebuild_index
fi

echo "Starting kb on port ${API_PORT:-8000}..."
python -m src.app
