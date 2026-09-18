import asyncio
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from aiogram.utils.web_app import check_webapp_signature
from aiohttp.test_utils import TestClient, TestServer

from database.quiz import AlreadyCompleted, QuizDatabase, validate_profile
from web.server import create_app
from web.telegram_auth import TelegramAuthError, validate_init_data

TOKEN = "123456789:test-token-for-local-tests-only"


def prof(i=1, **over):
    base = {'last_name': 'Иванов', 'first_name': 'Иван', 'middle_name': 'Иванович',
            'course': 2, 'student_id': f'10000{i}', 'phone': f'+7900000000{i}'}
    base.update(over)
    return base


def signed(*, user=None, auth_date=None, extra=None):
    fields = {"auth_date": str(int(time.time()) if auth_date is None else auth_date),
              "user": json.dumps({"id": 123456, "username": "tester"} if user is None else user, ensure_ascii=False)}
    fields.update(extra or {})
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_valid_signature_matches_aiogram():
    data = signed(extra={"query_id": "abc", "signature": "third-party-signature"})
    assert check_webapp_signature(TOKEN, data)
    assert validate_init_data(data, TOKEN).id == 123456


def test_user_without_username_and_unicode():
    user = validate_init_data(signed(user={"id": 2**40, "first_name": "Анна 🧡"}), TOKEN)
    assert user.id == 2**40 and user.username is None


@pytest.mark.parametrize("data", [
    "", "invalid", "hash=wrong", signed() + "&auth_date=1",
    signed().replace("tester", "attacker"), signed(auth_date=1),
    signed(auth_date=int(time.time()) + 300), signed(user={"id": True}),
    signed(user={"id": "123"}), signed(user={"id": -1}), signed(user=[]),
    signed(user={"id": 123, "username": []}),
])
def test_rejects_invalid_data(data):
    with pytest.raises(TelegramAuthError):
        validate_init_data(data, TOKEN)


def test_rejects_wrong_bot():
    with pytest.raises(TelegramAuthError):
        validate_init_data(signed(), "different-token")


@pytest.mark.asyncio
async def test_database_upsert_and_concurrency(tmp_path):
    db = QuizDatabase(tmp_path / "quiz.sqlite3")
    await db.initialize()
    assert await db.count() == 0
    await asyncio.gather(*(db.complete(i, f"user{i}", "score_7", prof(i)) for i in range(1, 7)))
    assert await db.count() == 6
    with pytest.raises(AlreadyCompleted):
        await db.complete(1, None, "score_10", prof(1))
    assert await db.count() == 6
    first = next(row for row in await db.participants() if row["telegram_user_id"] == 1)
    assert first["result"] == "score_7" and first["phone"] == "+79000000001"
    assert first["completed_at"]


def test_profile_validation():
    assert validate_profile(prof(1))["phone"] == "+79000000001"
    assert validate_profile(prof(1, phone="89000000001"))["phone"] == "+79000000001"
    assert validate_profile(prof(1, phone="9000000001"))["phone"] == "+79000000001"
    assert validate_profile(prof(1, course="3"))["course"] == 3
    for bad in [None, [], {**prof(1), "extra": 1},
                prof(1, last_name=""), prof(1, first_name="123"),
                prof(1, course=0), prof(1, course=7), prof(1, course="x"),
                prof(1, student_id="ab"), prof(1, phone="123"),
                prof(1, phone=""), {k: v for k, v in prof(1).items() if k != "phone"}]:
        with pytest.raises(ValueError):
            validate_profile(bad)


@pytest.mark.asyncio
async def test_legacy_row_gets_profile_once(tmp_path):
    import aiosqlite
    path = tmp_path / "legacy.sqlite3"
    async with aiosqlite.connect(path) as conn:
        await conn.execute("CREATE TABLE quiz_users (telegram_user_id INTEGER PRIMARY KEY, telegram_username TEXT, result TEXT NOT NULL, completed_at DATETIME NOT NULL)")
        await conn.execute("INSERT INTO quiz_users VALUES (1, NULL, 'score_7', '2026-09-08')")
        await conn.commit()
    db = QuizDatabase(path)
    await db.initialize()
    assert await db.complete(1, "late_name", "score_10", prof(1)) == "profile_updated"
    row = (await db.participants())[0]
    assert row["result"] == "score_7" and row["phone"] == "+79000000001"
    with pytest.raises(AlreadyCompleted):
        await db.complete(1, None, "score_10", prof(1))


@pytest.mark.asyncio
async def test_api_validation_and_persistence(tmp_path):
    db_path = tmp_path / "quiz.sqlite3"
    db = QuizDatabase(db_path)
    app = create_app(bot_token=TOKEN, database_path=db_path)
    async with TestClient(TestServer(app)) as client:
        health = await client.get('/healthz')
        assert health.status == 200 and await health.json() == {'status': 'ok'}
        assert await db.count() == 0
        invalid_cases = [
            ({"initData": "invalid", "result": "score_7", "profile": prof(1)}, 401),
            ({"initData": signed(auth_date=1), "result": "score_7", "profile": prof(1)}, 401),
            ({"initData": signed(), "result": "hacker", "profile": prof(1)}, 400),
            ({"initData": signed(), "result": [], "profile": prof(1)}, 400),
            ({"initData": 123, "result": "score_7", "profile": prof(1)}, 401),
            ({"initData": signed(), "result": "score_7", "profile": {"bad": 1}}, 400),
            ({"initData": signed(), "result": "score_7", "profile": prof(1, phone="x")}, 400),
            ({"initData": signed(), "result": "score_7"}, 400),
            ({"initData": signed(), "result": "score_7", "profile": prof(1), "telegram_user_id": 999}, 400),
            ([], 400),
        ]
        for payload, status in invalid_cases:
            response = await client.post('/api/quiz/complete', json=payload)
            assert response.status == status
        assert await db.count() == 0
        assert (await client.post('/api/quiz/complete', data='{', headers={'Content-Type': 'application/json'})).status == 400
        assert (await client.post('/api/quiz/complete', data='x')).status == 415
        assert (await client.post('/api/quiz/complete', json={'initData': 'x' * 25000, 'result': 'score_7', 'profile': prof(1)})).status == 413
        response = await client.post('/api/quiz/complete', json={'initData': signed(), 'result': 'score_7', 'profile': prof(1)})
        assert response.status == 200 and await response.json() == {'ok': True}
        assert await db.count() == 1
        assert (await db.participants())[0]['result'] == 'score_7'
        response = await client.post('/api/quiz/complete', json={'initData': signed(), 'result': 'score_10', 'profile': prof(1)})
        assert response.status == 409 and await response.json() == {'error': 'already_completed'}
        assert (await db.participants())[0]['result'] == 'score_7'
        assert (await client.get('/api/quiz/complete')).status == 405


@pytest.mark.asyncio
async def test_static_files_and_private_file_protection(tmp_path):
    static = tmp_path / 'dist'
    static.mkdir()
    (static / 'index.html').write_text('<html>Mini App</html>')
    (static / '.env').write_text('private')
    private = tmp_path / 'private.txt'
    private.write_text('private')
    (static / 'escape.txt').symlink_to(private)
    async with TestClient(TestServer(create_app(bot_token=TOKEN, database_path=tmp_path / 'db.sqlite3', static_dir=static))) as client:
        response = await client.get('/')
        assert response.status == 200 and 'Mini App' in await response.text()
        for path in ['/.env', '/escape.txt', '/api/missing', '/missing.js']:
            assert (await client.get(path)).status == 404
