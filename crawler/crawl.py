import asyncio
import os
import ssl
import urllib.parse
import aiosqlite

DB_PATH = os.environ.get("DB_PATH", "./search.db")
SEEDS_PATH = os.environ.get("SEEDS_PATH", "./seeds.txt")
CONCURRENCY = 5
TIMEOUT = 10.0
MAX_BODY = 256 * 1024   # 256 KB
MAX_DISCOVERED = 500    # cap on how many linked capsules to crawl


_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE


async def fetch_gemini(url: str) -> str | None:
    """Fetch a Gemini URL and return the body text, or None on failure."""
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname
    port = parsed.port or 1965
    if not host:
        return None

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=_ssl_ctx),
            timeout=TIMEOUT,
        )
    except Exception as exc:
        raise ConnectionError(str(exc)) from exc

    try:
        writer.write(f"{url}\r\n".encode("utf-8"))
        await asyncio.wait_for(writer.drain(), timeout=TIMEOUT)

        header_bytes = await asyncio.wait_for(reader.readline(), timeout=TIMEOUT)
        header = header_bytes.decode("utf-8", errors="replace").strip()

        if not header or not header[:2].isdigit():
            return None

        status = header[:2]
        if not status.startswith("2"):
            return None

        body_bytes = await asyncio.wait_for(reader.read(MAX_BODY), timeout=TIMEOUT)
        return body_bytes.decode("utf-8", errors="replace")
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


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


def extract_links(body: str) -> list[str]:
    """Extract gemini:// URLs from link lines."""
    links = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped.startswith("=>"):
            continue
        parts = stripped[2:].split()
        if parts and parts[0].startswith("gemini://"):
            # Normalise: strip trailing slashes only from root URLs
            url = parts[0].rstrip("/")
            parsed = urllib.parse.urlparse(url)
            if parsed.path == "":
                url = url + "/"
            links.append(url)
    return links


async def ensure_schema(db: aiosqlite.Connection) -> None:
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("""
        CREATE TABLE IF NOT EXISTS capsules (
            url        TEXT PRIMARY KEY,
            title      TEXT,
            last_seen  TEXT DEFAULT (datetime('now'))
        )
    """)
    await db.commit()


async def fetch_and_index(
    db: aiosqlite.Connection,
    sem: asyncio.Semaphore,
    gemini_url: str,
    label: str = "",
) -> str | None:
    """Fetch, index, and return body (for link extraction), or None on failure."""
    async with sem:
        try:
            body = await fetch_gemini(gemini_url)
        except Exception as exc:
            print(f"[ERROR] {label}{gemini_url}: {exc}")
            return None

    if body is None:
        print(f"[SKIP]  {label}{gemini_url}: non-success or empty")
        return None

    title = extract_title(body)
    if not title:
        print(f"[SKIP]  {label}{gemini_url}: no title")
        return None

    await db.execute("""
        INSERT INTO capsules (url, title, last_seen) VALUES (?, ?, datetime('now'))
        ON CONFLICT(url) DO UPDATE SET title=excluded.title, last_seen=datetime('now')
    """, (gemini_url, title))
    await db.commit()
    print(f"[OK]    {label}{gemini_url}: {title!r}")
    return body


async def main() -> None:
    try:
        with open(SEEDS_PATH) as f:
            seeds = [
                line.strip() for line in f
                if line.strip() and not line.startswith("#")
            ]
    except FileNotFoundError:
        print(f"[ERROR] Seeds file not found: {SEEDS_PATH}")
        return

    print(f"Loaded {len(seeds)} seeds from {SEEDS_PATH}")

    async with aiosqlite.connect(DB_PATH) as db:
        await ensure_schema(db)
        sem = asyncio.Semaphore(CONCURRENCY)

        # Phase 1: crawl seeds and collect links
        print("\n=== Phase 1: Seeds ===")
        discovered: set[str] = set()
        seed_set = set(seeds)

        seed_bodies = await asyncio.gather(*[
            fetch_and_index(db, sem, url) for url in seeds
        ])

        for body in seed_bodies:
            if body:
                for link in extract_links(body):
                    if link not in seed_set:
                        discovered.add(link)

        # Phase 2: crawl discovered links (one level deep)
        to_crawl = list(discovered)[:MAX_DISCOVERED]
        print(f"\n=== Phase 2: Discovered links ({len(to_crawl)} URLs) ===")

        await asyncio.gather(*[
            fetch_and_index(db, sem, url, label="  ") for url in to_crawl
        ])

        # Summary
        async with db.execute("SELECT COUNT(*) FROM capsules") as cur:
            count = (await cur.fetchone())[0]

    print(f"\nCrawl complete. {count} capsules in index.")


if __name__ == "__main__":
    asyncio.run(main())
