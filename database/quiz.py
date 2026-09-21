"""Only completed participants are stored; every write is an atomic upsert."""
import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

RESULTS = frozenset({f"score_{i}" for i in range(11)})
RESULT_CHECK = ", ".join(f"'score_{i}'" for i in range(11))

# Эталон теста — должен 1-в-1 совпадать с src/data/questions.ts.
# Клиент присылает индексы в ИСХОДНОМ порядке (не перемешанном), сервер считает баллы сам.
QUESTIONS = [
    {"label": "Возраст проекта", "answers": ["20", "22", "25", "24"], "correct": 2},
    {"label": "Фраза «Школа Актива»", "answers": ["море знаний, позитива", "много счастья, позитива", "море цифр, позитива"], "correct": 0},
    {"label": "Место проекта", "answers": ["УОК Лесное Озеро", "УОК Лесная Поляна", "УОК Лесная Опушка", "УОК Березовая Роща"], "correct": 0},
    {"label": "Футболки наставников", "answers": ["фиолетовые", "синие", "белые", "красные"], "correct": 1},
    {"label": "Длительность", "answers": ["1", "2", "3", "4"], "correct": 2},
    {"label": "Директора", "answers": ["Катя и Лера", "Арина и Влад", "Даша и Кристина", "Катя и Никита"], "correct": 0},
    {"label": "«Из искры»", "answers": ["свет", "позитив", "пламя", "костёр"], "correct": 2},
    {"label": "Фиолетовая футболка", "answers": ["тренера", "методиста", "техпода", "наставника"], "correct": 0},
    {"label": "Когда проект", "answers": ["в сентябре", "в октябре", "в ноябре", "в декабре"], "correct": 2},
    {"label": "Хочешь на ША", "answers": ["Да", "Пока думаю", "Нет("], "correct": 0},
]
MAX_TIME_MS = 3_600_000

PROFILE_FIELDS = ("last_name", "first_name", "middle_name", "course", "faculty", "student_id", "phone")
COURSES = ("b1", "b2", "b3", "b4", "m1", "m2")
COURSE_LABELS = {"b1": "Бакалавриат, 1 курс", "b2": "Бакалавриат, 2 курс",
                 "b3": "Бакалавриат, 3 курс", "b4": "Бакалавриат, 4 курс",
                 "m1": "Магистратура, 1 курс", "m2": "Магистратура, 2 курс"}
# Старые числовые курсы (1..6) маппятся в новую сетку для сводок.
LEGACY_COURSES = {1: "b1", 2: "b2", 3: "b3", 4: "b4", 5: "m1", 6: "m2"}
FACULTIES = ("ИТиАБД", "ВШУ", "МЭО", "СНиМК", "ФинФак", "ЮрФак", "НАБ", "ФЭБ")
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
    if course not in COURSES:
        raise ValueError("Course must be one of b1..b4, m1..m2")
    faculty = profile["faculty"]
    if faculty not in FACULTIES:
        raise ValueError("Unknown faculty")
    student_id = profile["student_id"]
    if not isinstance(student_id, str) or not _STUDENT_ID_RE.match(student_id.strip()):
        raise ValueError("Bad student_id")
    phone = _normalize_phone(profile["phone"])
    return {
        "last_name": last_name, "first_name": first_name, "middle_name": middle_name,
        "course": course, "faculty": faculty,
        "student_id": student_id.strip(), "phone": phone,
    }


def validate_answers(answers: object) -> list[int]:
    """Check 10 canonical answer indices. Raises ValueError."""
    if not isinstance(answers, list) or len(answers) != len(QUESTIONS):
        raise ValueError("answers must be a list of 10 indices")
    clean = []
    for i, (index, question) in enumerate(zip(answers, QUESTIONS)):
        if not isinstance(index, int) or isinstance(index, bool):
            raise ValueError(f"Bad answer for question {i + 1}")
        if not 0 <= index < len(question["answers"]):
            raise ValueError(f"Bad answer for question {i + 1}")
        clean.append(index)
    return clean


def validate_times(times: object) -> list[int]:
    """Check 10 per-question times in ms. Raises ValueError."""
    if not isinstance(times, list) or len(times) != len(QUESTIONS):
        raise ValueError("times must be a list of 10 values")
    clean = []
    for i, value in enumerate(times):
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"Bad time for question {i + 1}")
        if not 0 <= value <= MAX_TIME_MS:
            raise ValueError(f"Bad time for question {i + 1}")
        clean.append(value)
    return clean


def score_answers(answers: list[int]) -> tuple[str, int, list[int]]:
    """Return (result_id, score, per-question correct flags)."""
    flags = [1 if index == q["correct"] else 0 for index, q in zip(answers, QUESTIONS)]
    score = sum(flags)
    return f"score_{score}", score, flags


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
                    course TEXT NULL,
                    faculty TEXT NULL,
                    student_id TEXT NULL,
                    phone TEXT NULL,
                    total_ms INTEGER NULL
                )
            """)
            # Add profile columns to tables created before the contest form.
            async with db.execute("PRAGMA table_info(quiz_users)") as cursor:
                columns = {row[1] for row in await cursor.fetchall()}
            for column in ("last_name", "first_name", "middle_name", "course", "faculty", "student_id", "phone", "total_ms"):
                if column not in columns:
                    await db.execute(f"ALTER TABLE quiz_users ADD COLUMN {column} {'INTEGER' if column == 'total_ms' else 'TEXT'} NULL")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS quiz_answers (
                    telegram_user_id INTEGER NOT NULL,
                    q_index INTEGER NOT NULL,
                    correct INTEGER NOT NULL,
                    time_ms INTEGER NOT NULL,
                    PRIMARY KEY (telegram_user_id, q_index)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS raffle_allowlist (
                    value TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    added_by INTEGER NOT NULL,
                    created_at DATETIME NOT NULL
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
                        completed_at DATETIME NOT NULL,
                        last_name TEXT NULL,
                        first_name TEXT NULL,
                        middle_name TEXT NULL,
                        course TEXT NULL,
                        faculty TEXT NULL,
                        student_id TEXT NULL,
                        phone TEXT NULL,
                        total_ms INTEGER NULL
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

    async def complete(self, user_id: int, username: str | None,
                       answers: list[int] | tuple[int, ...], times: list[int] | tuple[int, ...],
                       profile: dict | None) -> tuple[str, str]:
        """Save first completion; fill a legacy profile-less row once; reject repeats.

        The score is always computed server-side from canonical answers.
        Returns (result_id, status) where status is 'created' or 'profile_updated'.
        Raises AlreadyCompleted or ValueError.
        """
        clean_answers = validate_answers(answers)
        clean_times = validate_times(times)
        clean = validate_profile(profile)
        result_id, _, flags = score_answers(clean_answers)
        total_ms = sum(clean_times)
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.path, timeout=10) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT last_name, result FROM quiz_users WHERE telegram_user_id = ?", (user_id,)
            ) as cursor:
                existing = await cursor.fetchone()
            if existing is None:
                await db.execute("""
                    INSERT INTO quiz_users
                        (telegram_user_id, telegram_username, result, completed_at,
                         last_name, first_name, middle_name, course, faculty,
                         student_id, phone, total_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (user_id, username, result_id, now, clean["last_name"], clean["first_name"],
                      clean["middle_name"], clean["course"], clean["faculty"],
                      clean["student_id"], clean["phone"], total_ms))
                await db.executemany("""
                    INSERT INTO quiz_answers (telegram_user_id, q_index, correct, time_ms)
                    VALUES (?, ?, ?, ?)
                """, [(user_id, i, flag, ms) for i, (flag, ms) in enumerate(zip(flags, clean_times))])
                await db.commit()
                return result_id, "created"
            if existing["last_name"] is None:
                await db.execute("""
                    UPDATE quiz_users SET telegram_username = ?, completed_at = ?,
                        last_name = ?, first_name = ?, middle_name = ?,
                        course = ?, faculty = ?, student_id = ?, phone = ?
                    WHERE telegram_user_id = ?
                """, (username, now, clean["last_name"], clean["first_name"], clean["middle_name"],
                      clean["course"], clean["faculty"], clean["student_id"], clean["phone"], user_id))
                await db.commit()
                return existing["result"], "profile_updated"
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

    async def answer_details(self) -> dict[int, dict]:
        """Per-user answers: {user_id: {'flags': [...], 'times': [...]}} in question order."""
        details: dict[int, dict] = {}
        async with aiosqlite.connect(self.path, timeout=10) as db:
            async with db.execute(
                "SELECT telegram_user_id, q_index, correct, time_ms FROM quiz_answers"
            ) as cursor:
                async for user_id, q_index, correct, time_ms in cursor:
                    entry = details.setdefault(user_id, {
                        "flags": [None] * len(QUESTIONS), "times": [None] * len(QUESTIONS)})
                    if 0 <= q_index < len(QUESTIONS):
                        entry["flags"][q_index] = correct
                        entry["times"][q_index] = time_ms
        return details

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
            async with db.execute("""
                SELECT course, COUNT(*) FROM quiz_users
                WHERE course IS NOT NULL GROUP BY course
            """) as cursor:
                by_course = {course: 0 for course in COURSES}
                for raw, count in await cursor.fetchall():
                    key = LEGACY_COURSES.get(raw, raw) if isinstance(raw, int) else raw
                    if key in by_course:
                        by_course[key] += count
            async with db.execute("""
                SELECT faculty, COUNT(*) FROM quiz_users
                WHERE faculty IS NOT NULL GROUP BY faculty
            """) as cursor:
                by_faculty = {faculty: 0 for faculty in FACULTIES}
                by_faculty.update({row[0]: row[1] for row in await cursor.fetchall()
                                   if row[0] in FACULTIES})
            async with db.execute("""
                SELECT q_index, COUNT(*), COALESCE(SUM(correct), 0), COALESCE(AVG(time_ms), 0)
                FROM quiz_answers GROUP BY q_index
            """) as cursor:
                answer_rows = {row[0]: row[1:] for row in await cursor.fetchall()}
            questions = []
            for i, question in enumerate(QUESTIONS):
                attempts, correct, avg_ms = answer_rows.get(i, (0, 0, 0))
                questions.append({
                    "label": question["label"], "attempts": attempts, "correct": correct,
                    "pct": (100.0 * correct / attempts) if attempts else 0.0,
                    "avg_ms": avg_ms,
                })
            async with db.execute("""
                SELECT COUNT(total_ms), COALESCE(AVG(total_ms), 0) FROM quiz_users
                WHERE total_ms IS NOT NULL
            """) as cursor:
                timed_count, avg_total_ms = await cursor.fetchone()
            return {"total": sum(by_result.values()), "by_result": by_result,
                    "eligible": eligible, "dup_phones": dup_phones,
                    "dup_student_ids": dup_student_ids, "by_course": by_course,
                    "by_faculty": by_faculty,
                    "questions": questions, "timed_count": timed_count,
                    "avg_total_ms": avg_total_ms}

    async def faculty_course_matrix(self) -> dict[str, dict[str, int]]:
        """{faculty: {course_code: participants}} for dashboard slices."""
        matrix = {faculty: {course: 0 for course in COURSES} for faculty in FACULTIES}
        async with aiosqlite.connect(self.path, timeout=10) as db:
            async with db.execute("""
                SELECT faculty, course, COUNT(*) FROM quiz_users
                WHERE faculty IS NOT NULL AND course IS NOT NULL
                GROUP BY faculty, course
            """) as cursor:
                async for faculty, raw_course, count in cursor:
                    if faculty not in matrix:
                        continue
                    course = LEGACY_COURSES.get(raw_course, raw_course) if isinstance(raw_course, int) else raw_course
                    if course in COURSES:
                        matrix[faculty][course] += count
        return matrix

    async def draw_winners(self, admin_id: int, count: int, only_allowlisted: bool = False) -> list[dict]:
        """Pick `count` random participants (crypto-secure). Nothing is stored.

        Raises ValueError on bad count or empty pool.
        """
        if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 20:
            raise ValueError("count must be an integer 1..20")
        pool = await self.eligible_participants(bool(only_allowlisted))
        if not pool:
            raise ValueError("no participants yet")
        if count > len(pool):
            raise ValueError("count exceeds participants")
        rng = secrets.SystemRandom()
        winners = rng.sample(pool, count)
        return [{
            "telegram_user_id": row["telegram_user_id"],
            "telegram_username": row.get("telegram_username"),
            "last_name": row.get("last_name"), "first_name": row.get("first_name"),
            "middle_name": row.get("middle_name"), "course": row.get("course"),
            "faculty": row.get("faculty"), "student_id": row.get("student_id"),
            "phone": row.get("phone"), "result": row.get("result"),
        } for row in winners]

    @staticmethod
    def parse_allowlist(raw: object) -> tuple[list[tuple[str, str]], list[str]]:
        """Split pasted text into (value, kind) entries plus rejected tokens.

        Usernames lose @ and lowercase; pure digits become user_id.
        """
        if not isinstance(raw, str):
            return [], []
        tokens = re.split(r"[\s,;]+", raw.strip())
        entries: list[tuple[str, str]] = []
        rejected: list[str] = []
        seen: set[str] = set()
        for token in tokens:
            if not token:
                continue
            if token.isdigit():
                key = ("user_id", token)
            else:
                name = token.lstrip("@").lower()
                if not re.fullmatch(r"[a-z0-9_]{5,32}", name):
                    rejected.append(token)
                    continue
                key = ("username", name)
            if key in seen:
                continue
            seen.add(key)
            entries.append((key[1], key[0]))
        return entries, rejected

    async def set_allowlist(self, admin_id: int, raw: object) -> tuple[int, list[str]]:
        """Replace the allowlist with freshly parsed entries. Returns (added, rejected)."""
        entries, rejected = self.parse_allowlist(raw)
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.path, timeout=10) as db:
            await db.execute("DELETE FROM raffle_allowlist")
            await db.executemany("""
                INSERT INTO raffle_allowlist (value, kind, added_by, created_at)
                VALUES (?, ?, ?, ?)
            """, [(value, kind, admin_id, now) for value, kind in entries])
            await db.commit()
        return len(entries), rejected

    async def get_allowlist(self) -> list[dict]:
        async with aiosqlite.connect(self.path, timeout=10) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT value, kind, added_by, created_at FROM raffle_allowlist ORDER BY value
            """) as cursor:
                return [dict(row) for row in await cursor.fetchall()]

    async def eligible_participants(self, only_allowlisted: bool) -> list[dict]:
        """All participants, optionally narrowed to the allowlist (by id or username)."""
        pool = await self.participants()
        if not only_allowlisted:
            return pool
        allowed = await self.get_allowlist()
        if not allowed:
            raise ValueError("allowlist is empty")
        ids = {entry["value"] for entry in allowed if entry["kind"] == "user_id"}
        names = {entry["value"] for entry in allowed if entry["kind"] == "username"}
        return [row for row in pool
                if str(row["telegram_user_id"]) in ids
                or (row.get("telegram_username") or "").lower() in names]
