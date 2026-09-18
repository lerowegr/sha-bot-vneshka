"""Only completed participants are stored; every write is an atomic upsert."""
import re
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

RESULTS = frozenset({f"score_{i}" for i in range(11)})
RESULT_CHECK = ", ".join(f"'score_{i}'" for i in range(11))

PROFILE_FIELDS = ("last_name", "first_name", "middle_name", "course", "student_id", "phone")
_NAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁё\- ]{1,60}$")
_STUDENT_ID_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9\-]{4,20}$")


class AlreadyCompleted(Exception):
    """Raised when a participant with a saved profile tries to complete again."""


def validate_profile(profile: object) -> dict:
    """Validate the contest form and return normalized values. Raises ValueError."""
    if not isinstance(profile, dict) or set(profile) != set(PROFILE_FIELDS):
        raise ValueError("Profile must contain exactly: " + ", ".join(PROFILE_FIELDS))
    last_name = _clean_name(profile["last_name"], "last_name")
    first_name = _clean_name(profile["first_name"], "first_name")
    middle_name = _clean_name(profile["middle_name"], "middle_name")
    course = profile["course"]
    if isinstance(course, str) and course.isdigit():
        course = int(course)
    if not isinstance(course, int) or isinstance(course, bool) or not 1 <= course <= 6:
        raise ValueError("Course must be an integer 1..6")
    student_id = profile["student_id"]
    if not isinstance(student_id, str) or not _STUDENT_ID_RE.match(student_id.strip()):
        raise ValueError("Bad student_id")
    phone = _normalize_phone(profile["phone"])
    return {
        "last_name": last_name, "first_name": first_name, "middle_name": middle_name,
        "course": course, "student_id": student_id.strip(), "phone": phone,
    }


def _clean_name(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Bad {field}")
    value = " ".join(value.split())
    if not _NAME_RE.match(value):
        raise ValueError(f"Bad {field}")
    return value


def _normalize_phone(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Bad phone")
    digits = re.sub(r"[\s\-\(\)]", "", value.strip())
    if re.fullmatch(r"8\d{10}", digits):
        digits = "+7" + digits[1:]
    elif re.fullmatch(r"\d{10}", digits):
        digits = "+7" + digits
    if not re.fullmatch(r"\+7\d{10}", digits):
        raise ValueError("Bad phone")
    return digits


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
                    completed_at DATETIME NOT NULL,
                    last_name TEXT NULL,
                    first_name TEXT NULL,
                    middle_name TEXT NULL,
                    course INTEGER NULL,
                    student_id TEXT NULL,
                    phone TEXT NULL
                )
            """)
            # Add profile columns to tables created before the contest form.
            async with db.execute("PRAGMA table_info(quiz_users)") as cursor:
                columns = {row[1] for row in await cursor.fetchall()}
            for column in ("last_name", "first_name", "middle_name", "course", "student_id", "phone"):
                if column not in columns:
                    await db.execute(f"ALTER TABLE quiz_users ADD COLUMN {column} {'INTEGER' if column == 'course' else 'TEXT'} NULL")
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
                        completed_at DATETIME NOT NULL,
                        last_name TEXT NULL,
                        first_name TEXT NULL,
                        middle_name TEXT NULL,
                        course INTEGER NULL,
                        student_id TEXT NULL,
                        phone TEXT NULL
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

    async def complete(self, user_id: int, username: str | None, result: str, profile: dict | None) -> str:
        """Save first completion; fill a legacy profile-less row once; reject repeats.

        Returns 'created' or 'profile_updated'. Raises AlreadyCompleted or ValueError.
        """
        if result not in RESULTS:
            raise ValueError("Unknown quiz result")
        clean = validate_profile(profile)
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.path, timeout=10) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT last_name FROM quiz_users WHERE telegram_user_id = ?", (user_id,)
            ) as cursor:
                existing = await cursor.fetchone()
            if existing is None:
                await db.execute("""
                    INSERT INTO quiz_users
                        (telegram_user_id, telegram_username, result, completed_at,
                         last_name, first_name, middle_name, course, student_id, phone)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (user_id, username, result, now, clean["last_name"], clean["first_name"],
                      clean["middle_name"], clean["course"], clean["student_id"], clean["phone"]))
                await db.commit()
                return "created"
            if existing["last_name"] is None:
                await db.execute("""
                    UPDATE quiz_users SET telegram_username = ?, completed_at = ?,
                        last_name = ?, first_name = ?, middle_name = ?,
                        course = ?, student_id = ?, phone = ?
                    WHERE telegram_user_id = ?
                """, (username, now, clean["last_name"], clean["first_name"], clean["middle_name"],
                      clean["course"], clean["student_id"], clean["phone"], user_id))
                await db.commit()
                return "profile_updated"
            raise AlreadyCompleted("Participant already completed the quiz")

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
            async with db.execute("""
                SELECT COUNT(*) FROM (
                    SELECT phone FROM quiz_users WHERE phone IS NOT NULL
                    GROUP BY phone HAVING COUNT(*) > 1
                )
            """) as cursor:
                dup_phones = (await cursor.fetchone())[0]
            async with db.execute("""
                SELECT COUNT(*) FROM (
                    SELECT student_id FROM quiz_users WHERE student_id IS NOT NULL
                    GROUP BY student_id HAVING COUNT(*) > 1
                )
            """) as cursor:
                dup_student_ids = (await cursor.fetchone())[0]
            return {"total": sum(by_result.values()), "by_result": by_result,
                    "eligible": eligible, "dup_phones": dup_phones,
                    "dup_student_ids": dup_student_ids}
