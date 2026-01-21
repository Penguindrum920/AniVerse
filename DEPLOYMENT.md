# AniVerse Deployment Guide

## Quick Start (Development)

```bash
# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
python main.py

# Frontend
cd frontend
python -m http.server 5500
```

## Production Deployment Options

### Option 1: Docker (Recommended)

```bash
# Build and run backend
cd backend
docker build -t aniverse-backend .
docker run -d \
  -p 8000:8000 \
  -v ./data:/app/data \
  -e GROQ_API_KEY=your_key \
  --name aniverse-api \
  aniverse-backend
```

### Option 2: Railway / Render

1. Push code to GitHub
2. Connect repository to Railway/Render
3. Set environment variables in dashboard:
   - `GROQ_API_KEY` (required)
   - `MAL_CLIENT_ID` (optional)
   - `MAL_CLIENT_SECRET` (optional)
4. Deploy!

### Option 3: VPS (Ubuntu)

```bash
# Install dependencies
sudo apt update && sudo apt install python3.11 python3.11-venv nginx

# Setup backend
cd /var/www/aniverse/backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Create systemd service
sudo nano /etc/systemd/system/aniverse.service
```

**aniverse.service:**
```ini
[Unit]
Description=AniVerse API
After=network.target

[Service]
User=www-data
WorkingDirectory=/var/www/aniverse/backend
Environment="GROQ_API_KEY=your_key"
ExecStart=/var/www/aniverse/backend/.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable aniverse
sudo systemctl start aniverse
```

## Frontend Hosting

### Option 1: Static Hosting (Vercel, Netlify, GitHub Pages)

Just deploy the `frontend/` folder. Update API URLs in `app.js`:

```javascript
const API_BASE = 'https://your-backend-url.com';
```

### Option 2: Nginx

```nginx
server {
    listen 80;
    server_name yourdomain.com;
    root /var/www/aniverse/frontend;
    index index.html;

    location /api {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }
}
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | ✅ | API key for Groq LLM |
| `MAL_CLIENT_ID` | ❌ | MyAnimeList OAuth client ID |
| `MAL_CLIENT_SECRET` | ❌ | MyAnimeList OAuth secret |
| `CORS_ORIGINS` | ❌ | Allowed origins (comma-separated) |
| `DATABASE_PATH` | ❌ | SQLite database path |

## Pre-deployment Checklist

- [ ] Set all required environment variables
- [ ] Build embeddings if not included: `python embeddings/build_embeddings.py`
- [ ] Build manga embeddings: `python embeddings/build_manga_embeddings.py`
- [ ] Update CORS origins for production domain
- [ ] Update API_BASE in frontend for production URL
