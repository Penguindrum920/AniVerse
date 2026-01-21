#!/bin/bash
# Startup script for Railway deployment

echo "=== AniVerse Startup ==="

# Download data from GDrive if not present
echo "Checking for data files..."
python setup_data.py

# Start the server
echo "Starting server on port ${PORT:-8000}..."
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
