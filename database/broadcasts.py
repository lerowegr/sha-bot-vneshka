"""Small durable broadcast journal, sharing the quiz database."""
import json
import uuid
from datetime import datetime, timezone

import aiosqlite

from database.quiz import QuizDatabase


class BroadcastStore:
    def __init__(self, quiz: QuizDatabase):
        self.path = quiz.path

    async def create_draft(self, admin_id: int, text: str, entities: list[dict]) -> str:
        if not text.strip() or len(text.encode('utf-16-le')) // 2 > 4096:
            raise ValueError('Message must contain 1–4096 UTF-16 code units')
        broadcast_id = uuid.uuid4().hex
        async with aiosqlite.connect(self.path, timeout=10) as db:
            await db.execute('BEGIN IMMEDIATE')
            await db.execute("UPDATE broadcasts SET status='cancelled' WHERE admin_id=? AND status='draft'", (admin_id,))
            await db.execute("INSERT INTO broadcasts VALUES (?, ?, ?, ?, 'draft', ?)",
                             (broadcast_id, admin_id, text, json.dumps(entities), datetime.now(timezone.utc).isoformat()))
            await db.execute("""
                INSERT INTO broadcast_recipients (broadcast_id, telegram_user_id)
                SELECT ?, q.telegram_user_id FROM quiz_users q WHERE NOT EXISTS (
                    SELECT 1 FROM broadcast_opt_outs o WHERE o.telegram_user_id = q.telegram_user_id
                )
            """, (broadcast_id,))
            await db.commit()
        return broadcast_id

    async def get(self, broadcast_id: str, admin_id: int) -> dict | None:
        async with aiosqlite.connect(self.path, timeout=10) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM broadcasts WHERE id=? AND admin_id=?', (broadcast_id, admin_id)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def claim(self, broadcast_id: str, admin_id: int) -> bool:
        async with aiosqlite.connect(self.path, timeout=10) as db:
            await db.execute('BEGIN IMMEDIATE')
            async with db.execute("SELECT 1 FROM broadcasts WHERE status='running'") as cursor:
                if await cursor.fetchone():
                    return False
            cursor = await db.execute("UPDATE broadcasts SET status='running' WHERE id=? AND admin_id=? AND status='draft'", (broadcast_id, admin_id))
            await db.commit()
            return cursor.rowcount == 1

    async def cancel(self, broadcast_id: str, admin_id: int) -> bool:
        async with aiosqlite.connect(self.path, timeout=10) as db:
            cursor = await db.execute("UPDATE broadcasts SET status='cancelled' WHERE id=? AND admin_id=? AND status IN ('draft', 'running')", (broadcast_id, admin_id))
            await db.commit()
            return cursor.rowcount == 1

    async def claim_recipient(self, broadcast_id: str, user_id: int) -> bool:
        async with aiosqlite.connect(self.path, timeout=10) as db:
            cursor = await db.execute("""
                UPDATE broadcast_recipients SET status='sending'
                WHERE broadcast_id=? AND telegram_user_id=? AND status='pending'
                AND EXISTS (SELECT 1 FROM broadcasts WHERE id=? AND status='running')
            """, (broadcast_id, user_id, broadcast_id))
            await db.commit()
            return cursor.rowcount == 1

    async def recipient_status(self, broadcast_id: str, user_id: int, status: str) -> None:
        async with aiosqlite.connect(self.path, timeout=10) as db:
            await db.execute('UPDATE broadcast_recipients SET status=? WHERE broadcast_id=? AND telegram_user_id=?', (status, broadcast_id, user_id))
            await db.commit()

    async def pending(self, broadcast_id: str) -> list[int]:
        async with aiosqlite.connect(self.path, timeout=10) as db:
            async with db.execute("SELECT telegram_user_id FROM broadcast_recipients WHERE broadcast_id=? AND status='pending' ORDER BY telegram_user_id", (broadcast_id,)) as cursor:
                return [row[0] for row in await cursor.fetchall()]

    async def is_running(self, broadcast_id: str) -> bool:
        async with aiosqlite.connect(self.path, timeout=10) as db:
            async with db.execute("SELECT 1 FROM broadcasts WHERE id=? AND status='running'", (broadcast_id,)) as cursor:
                return await cursor.fetchone() is not None

    async def cancel_admin(self, admin_id: int) -> None:
        async with aiosqlite.connect(self.path, timeout=10) as db:
            await db.execute("UPDATE broadcasts SET status='cancelled' WHERE admin_id=? AND status IN ('draft', 'running')", (admin_id,))
            await db.commit()

    async def finish(self, broadcast_id: str) -> None:
        async with aiosqlite.connect(self.path, timeout=10) as db:
            await db.execute("UPDATE broadcasts SET status='finished' WHERE id=? AND status='running'", (broadcast_id,))
            await db.commit()

    async def interrupt_running(self) -> None:
        # Telegram sendMessage has no idempotency key. Never resend an uncertain
        # in-flight request automatically after process interruption.
        async with aiosqlite.connect(self.path, timeout=10) as db:
            await db.execute("UPDATE broadcast_recipients SET status='unknown' WHERE status='sending'")
            await db.execute("UPDATE broadcasts SET status='interrupted' WHERE status='running'")
            await db.commit()

    async def report(self, broadcast_id: str) -> dict[str, int]:
        async with aiosqlite.connect(self.path, timeout=10) as db:
            async with db.execute('SELECT status, COUNT(*) FROM broadcast_recipients WHERE broadcast_id=? GROUP BY status', (broadcast_id,)) as cursor:
                return dict(await cursor.fetchall())

    async def recent(self, admin_id: int) -> list[dict]:
        async with aiosqlite.connect(self.path, timeout=10) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT id, status, created_at FROM broadcasts WHERE admin_id=? ORDER BY created_at DESC LIMIT 5', (admin_id,)) as cursor:
                return [dict(row) for row in await cursor.fetchall()]
