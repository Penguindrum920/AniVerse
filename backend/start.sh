#!/bin/bash
# Startup script for Railway deployment

echo "=== AniVerse Startup ==="

# Download data from GDrive in background while server starts
echo "Starting data download (runs in background)..."
python setup_data.py &
DATA_PID=$!

# Start the server immediately so healthcheck passes
echo "Starting server on port ${PORT:-8000}..."
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
