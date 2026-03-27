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

    # FTS5 index — content table mirrors capsules, no duplicate storage
    await db.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS capsules_fts
        USING fts5(url, title, content=capsules, content_rowid=rowid)
    """)

    # Keep FTS in sync with capsules via triggers
    await db.execute("""
        CREATE TRIGGER IF NOT EXISTS capsules_fts_ai
        AFTER INSERT ON capsules BEGIN
            INSERT INTO capsules_fts(rowid, url, title)
            VALUES (new.rowid, new.url, new.title);
        END
    """)
    await db.execute("""
        CREATE TRIGGER IF NOT EXISTS capsules_fts_au
        AFTER UPDATE ON capsules BEGIN
            INSERT INTO capsules_fts(capsules_fts, rowid, url, title)
            VALUES ('delete', old.rowid, old.url, old.title);
            INSERT INTO capsules_fts(rowid, url, title)
            VALUES (new.rowid, new.url, new.title);
        END
    """)

    # Backfill FTS with any rows not yet indexed
    await db.execute("""
        INSERT INTO capsules_fts(rowid, url, title)
        SELECT rowid, url, title FROM capsules
        WHERE rowid NOT IN (SELECT rowid FROM capsules_fts)
    """)

    await db.commit()


async def open_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    await ensure_schema(db)
    return db
