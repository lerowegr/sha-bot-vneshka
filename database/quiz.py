"""Only completed participants are stored; every write is an atomic upsert."""
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

RESULTS = frozenset({f"score_{i}" for i in range(11)})
RESULT_CHECK = ", ".join(f"'score_{i}'" for i in range(11))


class QuizDatabase:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path, timeout=10) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS quiz_users (
                    telegram_user_id INTEGER PRIMARY KEY,
                    telegram_username TEXT NULL,
                    result TEXT NOT NULL CHECK (
                        result IN ('score_0', 'score_1', 'score_2', 'score_3', 'score_4', 'score_5', 'score_6', 'score_7', 'score_8', 'score_9', 'score_10')
                    ),
                    completed_at DATETIME NOT NULL
                )
            """)
            # Migrate legacy CT base (backend/frontend/...) to new score_* schema.
            async with db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='quiz_users'") as cursor:
                row = await cursor.fetchone()
            if row and row[0] and 'score_0' not in row[0]:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS quiz_users_new (
                        telegram_user_id INTEGER PRIMARY KEY,
                        telegram_username TEXT NULL,
                        result TEXT NOT NULL CHECK (
                            result IN ('score_0', 'score_1', 'score_2', 'score_3', 'score_4', 'score_5', 'score_6', 'score_7', 'score_8', 'score_9', 'score_10')
                        ),
                        completed_at DATETIME NOT NULL
                    )
                """)
                await db.execute("""
                    INSERT OR IGNORE INTO quiz_users_new (telegram_user_id, telegram_username, result, completed_at)
                    SELECT telegram_user_id, telegram_username,
                        CASE WHEN result IN ('score_0','score_1','score_2','score_3','score_4','score_5','score_6','score_7','score_8','score_9','score_10')
                            THEN result ELSE 'score_5' END,
                        completed_at FROM quiz_users
                """)
                await db.execute("DROP TABLE quiz_users")
                await db.execute("ALTER TABLE quiz_users_new RENAME TO quiz_users")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS broadcast_opt_outs (
                    telegram_user_id INTEGER PRIMARY KEY
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS broadcasts (
                    id TEXT PRIMARY KEY,
                    admin_id INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    entities TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS broadcast_recipients (
                    broadcast_id TEXT NOT NULL,
                    telegram_user_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    PRIMARY KEY (broadcast_id, telegram_user_id)
                )
            """)
            await db.commit()

    async def complete(self, user_id: int, username: str | None, result: str) -> None:
        if result not in RESULTS:
            raise ValueError("Unknown quiz result")
        async with aiosqlite.connect(self.path, timeout=10) as db:
            await db.execute("""
                INSERT INTO quiz_users
                    (telegram_user_id, telegram_username, result, completed_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(telegram_user_id) DO UPDATE SET
                    telegram_username = excluded.telegram_username,
                    result = excluded.result,
                    completed_at = excluded.completed_at
            """, (user_id, username, result, datetime.now(timezone.utc).isoformat()))
            await db.commit()

    async def count(self) -> int:
        async with aiosqlite.connect(self.path, timeout=10) as db:
            async with db.execute("SELECT COUNT(*) FROM quiz_users") as cursor:
                row = await cursor.fetchone()
                return row[0]

    async def participants(self) -> list[dict]:
        async with aiosqlite.connect(self.path, timeout=10) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM quiz_users ORDER BY completed_at DESC") as cursor:
                return [dict(row) for row in await cursor.fetchall()]

    async def set_subscribed(self, user_id: int, subscribed: bool) -> None:
        async with aiosqlite.connect(self.path, timeout=10) as db:
            if subscribed:
                await db.execute("DELETE FROM broadcast_opt_outs WHERE telegram_user_id = ?", (user_id,))
            else:
                await db.execute("INSERT OR IGNORE INTO broadcast_opt_outs VALUES (?)", (user_id,))
            await db.commit()

    async def is_subscribed(self, user_id: int) -> bool:
        async with aiosqlite.connect(self.path, timeout=10) as db:
            async with db.execute("SELECT 1 FROM broadcast_opt_outs WHERE telegram_user_id = ?", (user_id,)) as cursor:
                return await cursor.fetchone() is None

    async def summary(self) -> dict:
        async with aiosqlite.connect(self.path, timeout=10) as db:
            async with db.execute("SELECT result, COUNT(*) FROM quiz_users GROUP BY result") as cursor:
                by_result = {role: 0 for role in sorted(RESULTS)}
                by_result.update(dict(await cursor.fetchall()))
            async with db.execute("""
                SELECT COUNT(*) FROM quiz_users q WHERE NOT EXISTS (
                    SELECT 1 FROM broadcast_opt_outs o WHERE o.telegram_user_id = q.telegram_user_id
                )
            """) as cursor:
                eligible = (await cursor.fetchone())[0]
            return {"total": sum(by_result.values()), "by_result": by_result, "eligible": eligible}
