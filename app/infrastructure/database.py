from contextlib import asynccontextmanager

import aiosqlite
from datetime import datetime, timezone


class Database:
    def __init__(self, path: str):
        self.path = path

    async def init(self):
        async with aiosqlite.connect(self.path) as db:
            await db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS tracked_users (
                    id INTEGER PRIMARY KEY, online INTEGER, checked_at TEXT
                );
                CREATE TABLE IF NOT EXISTS online_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL, online INTEGER NOT NULL, observed_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES tracked_users(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS events_user_id ON online_events(user_id, id DESC);
            ''')
            await db.commit()

    @asynccontextmanager
    async def connect(self):
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys=ON")
            await db.execute("PRAGMA busy_timeout=5000")
            yield db

    async def add(self, user_id: int):
        async with self.connect() as db:
            await db.execute("INSERT OR IGNORE INTO tracked_users(id) VALUES (?)", (user_id,))
            await db.commit()

    async def remove(self, user_id: int) -> bool:
        async with self.connect() as db:
            cursor = await db.execute("DELETE FROM tracked_users WHERE id=?", (user_id,))
            await db.commit()
            return cursor.rowcount > 0

    async def list_users(self):
        async with self.connect() as db:
            return [dict(row) for row in await (await db.execute("SELECT * FROM tracked_users ORDER BY id")).fetchall()]

    async def record(self, user_id: int, online: bool):
        # A single write transaction prevents a deletion from resurrecting a tracked user.
        async with self.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            row = await (await db.execute("SELECT online FROM tracked_users WHERE id=?", (user_id,))).fetchone()
            if row is not None:
                now = datetime.now(timezone.utc).isoformat()
                if row['online'] is None or bool(row['online']) != online:
                    await db.execute("INSERT INTO online_events(user_id, online, observed_at) VALUES (?, ?, ?)", (user_id, int(online), now))
                await db.execute("UPDATE tracked_users SET online=?, checked_at=? WHERE id=?", (int(online), now, user_id))
            await db.commit()

    async def history(self, user_id: int, limit: int):
        async with self.connect() as db:
            return [dict(row) for row in await (await db.execute(
                "SELECT user_id, online, observed_at FROM online_events WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit))).fetchall()]
