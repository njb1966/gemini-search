import os
import aiosqlite

DB_PATH = os.environ.get("DB_PATH", "./search.db")


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


async def open_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    await ensure_schema(db)
    return db
