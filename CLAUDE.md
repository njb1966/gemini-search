# gemini-mini-search

A lightweight Gemini-to-Web search hub: crawls Gemini capsules, indexes titles in SQLite, exposes a fuzzy-search API, and proxies capsule content as HTML.

## Architecture

```
Crawler (cron) → search.db (SQLite) → Search API (FastAPI, port 8000)
                                                ↑
Frontend (static HTML/Alpine.js) ←─────────────┘
        ↓ opens proxy links
Cloudflare Worker (gemini-to-HTTP proxy)
```

## Repo Layout

```
gemini-mini-search/
├── crawler/          # Fetches Gemini capsules, populates search.db
│   ├── crawl.py      # or main.go
│   ├── seeds.txt     # One gemini:// URL per line
│   └── Dockerfile
├── api/              # FastAPI search service
│   ├── app/
│   │   ├── main.py   # Routes: GET /search?q=, GET /health
│   │   └── db.py     # SQLite helper
│   ├── requirements.txt
│   └── Dockerfile
├── worker/           # Cloudflare Worker proxy
│   ├── src/index.js
│   ├── wrangler.toml
│   └── package.json
├── frontend/
│   └── index.html    # Alpine.js SPA, calls /api/search
├── docker-compose.yml
└── .github/workflows/ci.yml
```

## Quick Start (local prototype)

```bash
python3 -m venv venv && source venv/bin/activate
pip install fastapi uvicorn python-Levenshtein aiosqlite httpx aiofiles
echo "gemini://gemini.circumlunar.space/" > crawler/seeds.txt
python crawler/crawl.py          # populates search.db
uvicorn api.app.main:app --port 8000
# visit http://localhost:8000/search?q=gemini
```

## Services

### Crawler (`crawler/`)
- Reads `seeds.txt`; fetches each URL via `https://gemini.circumlunar.space/<encoded-url>`
- Extracts first non-blank line as title
- Inserts `{url, title}` into `search.db` table `capsules`; skips existing rows
- Run: `python crawl.py` (or Go binary); schedule daily via cron / GitHub Actions

### Search API (`api/`)
- `GET /search?q=<query>` — fuzzy Levenshtein match, returns top-10 JSON
- `GET /health` — liveness check
- CORS enabled for all origins
- Run: `uvicorn app.main:app --host 0.0.0.0 --port 8000`

### Cloudflare Worker (`worker/`)
- `GET /?url=gemini://…` — proxies capsule through public gateway, returns dark-mode HTML
- `?theme=dark|light` toggles stylesheet
- Deploy: `npx wrangler deploy`

### Frontend (`frontend/`)
- Static HTML + Alpine.js; search box → `/api/search` → renders results
- Each result links to `https://<worker>.workers.dev/?url=<gemini-url>`
- Host on GitHub Pages, Netlify, or Cloudflare Pages

## Environment Variables

| Variable | Service | Description |
|----------|---------|-------------|
| `DB_PATH` | api, crawler | Path to `search.db` (default: `./search.db`) |
| `GEMINI_GATEWAY` | crawler, worker | Gateway base URL (default: `https://gemini.circumlunar.space/`) |
| `WORKER_SUBDOMAIN` | frontend | Cloudflare Worker URL for proxy links |
| `API_BASE_URL` | frontend | Search API base (default: `/api`) |

## Database Schema

```sql
CREATE TABLE capsules (
    url        TEXT PRIMARY KEY,
    title      TEXT,
    last_seen  TEXT DEFAULT (datetime('now'))
);
-- Optional FTS for >10k rows:
CREATE VIRTUAL TABLE capsules_fts USING fts5(url, title, content=capsules);
```

## Docker Compose

```bash
docker compose up -d        # starts crawler (runs once) + api
docker compose logs -f api  # tail API logs
```

## CI/CD (`.github/workflows/ci.yml`)

1. Build & push Docker images to Docker Hub
2. Deploy API to Fly.io (`flyctl deploy`)
3. Deploy Worker (`npx wrangler deploy`)
4. Publish frontend to GitHub Pages

Required secrets: `DOCKER_USERNAME`, `DOCKER_PASSWORD`, `FLY_API_TOKEN`, `CLOUDFLARE_API_TOKEN`.

## Pre-Launch Checklist

- [ ] Seed list has ≥ 100 curated Gemini capsule URLs
- [ ] `/search` rate-limited (30 req/s per IP via `fastapi-limiter`)
- [ ] API served over HTTPS (Fly.io provides TLS automatically)
- [ ] `robots.txt` added; crawler sends polite `User-Agent`
- [ ] Privacy notice in place (query logging policy)
- [ ] README documents "add a capsule" and "use the proxy"

## Scaling Notes

- **Search speed**: swap Levenshtein for SQLite FTS5 once capsules > 10k rows
- **DB freshness**: daily GitHub Action cron pushes updated `search.db` to S3; API loads on start
- **Abuse**: validate `url` param starts with `gemini://` in Worker; add API key header for write endpoints
- **Backups**: nightly `sqlite3 search.db ".backup backup.db"` → Backblaze B2

## Key Dependencies

| Package | Purpose |
|---------|---------|
| `fastapi` + `uvicorn` | Search API server |
| `aiosqlite` | Async SQLite access |
| `python-Levenshtein` | Fuzzy title matching |
| `httpx` | Async HTTP client for crawler |
| `@cloudflare/workers-types` | Worker TypeScript types |
| `wrangler` | Cloudflare Worker CLI |
