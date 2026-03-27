import asyncio
import re
import ssl
import urllib.parse
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
import Levenshtein
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .db import DB_PATH, open_db

limiter = Limiter(key_func=get_remote_address, default_limits=["30/second"])

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE


def extract_title(body: str) -> str | None:
    in_pre = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_pre = not in_pre
            continue
        if in_pre or not stripped:
            continue
        if stripped.startswith("=>"):
            continue
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
        else:
            title = stripped
        return title[:500] if title else None
    return None


async def fetch_gemini_text(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname
    port = parsed.port or 1965
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=_ssl_ctx), timeout=10.0
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not connect: {exc}")
    try:
        writer.write(f"{url}\r\n".encode("utf-8"))
        await asyncio.wait_for(writer.drain(), timeout=10.0)
        header = (await asyncio.wait_for(reader.readline(), timeout=10.0)).decode("utf-8", errors="replace").strip()
        if not header[:2].startswith("2"):
            raise HTTPException(status_code=502, detail=f"Gemini error: {header}")
        body = await asyncio.wait_for(reader.read(256 * 1024), timeout=10.0)
        return body.decode("utf-8", errors="replace")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    app.state.db = await open_db()
    yield
    await app.state.db.close()


app = FastAPI(title="gemini-mini-search", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "db": DB_PATH}


def _fts_query(q: str) -> str:
    """Convert a user query into an FTS5 prefix-match expression."""
    tokens = re.findall(r"\w+", q.lower())
    return " ".join(f"{t}*" for t in tokens) if tokens else ""


@app.get("/search")
@limiter.limit("30/second")
async def search(request: Request, q: str = Query(..., min_length=1)):
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query must not be blank")

    db = request.app.state.db

    # Try FTS5 first — handles multi-word queries and partial matches
    fts_q = _fts_query(q)
    if fts_q:
        try:
            async with db.execute(
                """SELECT url, title, rank
                   FROM capsules_fts
                   WHERE capsules_fts MATCH ?
                   ORDER BY rank
                   LIMIT 20""",
                (fts_q,),
            ) as cursor:
                fts_rows = await cursor.fetchall()

            if fts_rows:
                # FTS5 rank is negative BM25 (more negative = better match).
                # Normalise to a 0–1 score for display.
                best = min(r[2] for r in fts_rows)
                worst = max(r[2] for r in fts_rows)
                spread = (worst - best) or 1.0
                results = [
                    {
                        "url": url,
                        "title": title,
                        "score": round(1.0 - (rank - best) / spread, 3),
                    }
                    for url, title, rank in fts_rows
                ]
                return results[:10]
        except Exception:
            pass  # FTS error — fall through to Levenshtein

    # Levenshtein fallback — handles typos / fuzzy matches
    async with db.execute(
        "SELECT url, title FROM capsules WHERE title IS NOT NULL"
    ) as cursor:
        rows = await cursor.fetchall()

    q_lower = q.lower()
    scored = [
        {
            "url": url,
            "title": title,
            "score": round(max(
                Levenshtein.ratio(q_lower, title.lower()),
                Levenshtein.ratio(q_lower, url.lower()),
            ), 3),
        }
        for url, title in rows
    ]
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:10]


@app.get("/proxy")
async def proxy_gemini(url: str = Query(...)):
    if not url.startswith("gemini://"):
        raise HTTPException(status_code=400, detail="URL must start with gemini://")
    text = await fetch_gemini_text(url)
    return PlainTextResponse(text)


@app.post("/submit")
@limiter.limit("5/minute")
async def submit(request: Request, url: str = Query(...)):
    url = url.strip()
    if not url.startswith("gemini://"):
        raise HTTPException(status_code=400, detail="URL must start with gemini://")

    db = request.app.state.db
    async with db.execute("SELECT url FROM capsules WHERE url = ?", (url,)) as cursor:
        if await cursor.fetchone():
            return {"status": "already_indexed", "url": url}

    text = await fetch_gemini_text(url)
    title = extract_title(text)
    if not title:
        raise HTTPException(status_code=422, detail="Could not extract a title from that capsule")

    await db.execute(
        "INSERT OR IGNORE INTO capsules (url, title) VALUES (?, ?)",
        (url, title),
    )
    await db.commit()
    return {"status": "indexed", "url": url, "title": title}
