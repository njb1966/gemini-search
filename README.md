# Gemini Search

A lightweight search engine for the [Gemini](https://geminiprotocol.net/) small web. Crawls Gemini capsules natively, indexes titles in SQLite with full-text search, and proxies capsule content as readable HTML.

**Live at [gemsearch.njb1966.com](https://gemsearch.njb1966.com)**

## Features

- **Full-text search** — FTS5 for multi-word and partial queries, Levenshtein fuzzy matching as a typo fallback
- **Native Gemini protocol** — crawler and proxy speak Gemini directly over TLS (no third-party gateway)
- **Geminitext rendering** — headings, links, lists, and preformatted blocks rendered as proper HTML
- **Chained proxy browsing** — links within capsules route back through the proxy, so you can browse capsule to capsule
- **Community submissions** — capsule owners can submit their URL directly from the search page
- **Daily crawling** — index refreshes automatically every night at 4am
- **Link following** — crawler discovers new capsules by following `gemini://` links found in indexed pages

## Architecture

```
Crawler (cron, daily) ──→ search.db (SQLite + FTS5)
                                  ↑
                     FastAPI Search API (port 8000)
                                  ↑
           Nginx (port 8090) ─────┴───── serves frontend/
                  ↑
     Cloudflare Tunnel (gemsearch.njb1966.com)
                                  ↓
              Cloudflare Worker (Gemini proxy)
                  ↓
         Native Gemini TLS (port 1965)
```

## Repo Layout

```
gemini-mini-search/
├── crawler/
│   ├── crawl.py          # Native Gemini crawler, follows links one level deep
│   ├── seeds.txt         # Curated seed capsule URLs
│   └── Dockerfile
├── api/
│   ├── app/
│   │   ├── main.py       # FastAPI: /search, /proxy, /submit, /health
│   │   └── db.py         # SQLite + FTS5 schema and helpers
│   ├── requirements.txt
│   └── Dockerfile
├── worker/
│   ├── src/index.js      # Cloudflare Worker: fetches + renders Geminitext as HTML
│   ├── wrangler.toml
│   └── package.json
├── frontend/
│   └── index.html        # Alpine.js SPA: search, results, capsule submission
├── nginx/
│   └── nginx.conf        # Serves frontend, proxies /api/ → FastAPI
└── docker-compose.yml
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/search?q=<query>` | FTS5 search, Levenshtein fallback, returns top 10 JSON |
| `GET /api/proxy?url=gemini://…` | Fetches capsule via native Gemini, returns raw text |
| `POST /api/submit?url=gemini://…` | Validates, fetches, and indexes a submitted capsule |
| `GET /api/health` | Liveness check |

## Running Locally

```bash
# Start everything
docker compose up --build

# Visit
open http://localhost:8090

# Run the crawler manually
docker compose run --rm crawler
```

## Deployment

The site is self-hosted behind a Cloudflare Tunnel. Pushing to `main` automatically deploys the Cloudflare Worker via GitHub Actions. Server updates are applied manually:

```bash
git pull && docker compose up -d --build
```

The crawler runs daily via cron:
```
0 4 * * * docker compose -f /home/nick/Projects/gemini-mini-search/docker-compose.yml run --rm crawler
```

## Adding Your Capsule

Visit [gemsearch.njb1966.com](https://gemsearch.njb1966.com) and use the **Add your capsule** form at the bottom of the page. Your capsule will be fetched and indexed immediately, and re-crawled nightly.

Or add your URL directly to `seeds.txt` and open a pull request.

## Environment Variables

| Variable | Service | Default |
|----------|---------|---------|
| `DB_PATH` | api, crawler | `./search.db` |
| `SEEDS_PATH` | crawler | `./seeds.txt` |
| `GEMINI_GATEWAY` | worker | `https://gemsearch.njb1966.com/api` |

---

Designed by **Nickel Works** &copy; 2026
