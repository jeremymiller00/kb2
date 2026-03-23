#!/bin/bash
cd "$(dirname "$0")"

# Ensure data directory exists
mkdir -p data

REBUILD=false
CLEAR=false
for arg in "$@"; do
    case "$arg" in
        --rebuild) REBUILD=true ;;
        --clear) CLEAR=true ;;
    esac
done

if [ "$REBUILD" = true ]; then
    echo "Force rebuilding database..."
    rm -f data/knowledge_base.db
fi

if [ "$REBUILD" = true ] || [ "$CLEAR" = true ] || [ ! -f data/knowledge_base.db ]; then
    if [ "$CLEAR" = true ]; then
        echo "Clearing index and rebuilding from vault..."
        python -m scripts.rebuild_index --clear
    elif [ "$REBUILD" = true ]; then
        python -m scripts.rebuild_index
    else
        echo "No local index found. Rebuilding from vault..."
        python -m scripts.rebuild_index
    fi
fi

echo "Starting kb on port ${API_PORT:-8000}..."
python -m src.app
