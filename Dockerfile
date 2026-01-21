# AniVerse Backend Dockerfile for Railway
# Data is downloaded from Google Drive on first startup

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY backend/requirements.txt .

# Install PyTorch CPU-only (smaller package) first
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Then install other requirements
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application code
COPY backend/ .

# Make startup script executable
RUN chmod +x start.sh

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0
ENV PORT=8000

# Health check (with longer start period for data download)
HEALTHCHECK --interval=30s --timeout=10s --start-period=300s --retries=5 \
    CMD curl -f http://localhost:${PORT:-8000}/api/health || exit 1

# Run the startup script (downloads data then starts server)
CMD ["./start.sh"]
