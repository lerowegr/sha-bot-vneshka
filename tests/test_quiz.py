import asyncio
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from aiogram.utils.web_app import check_webapp_signature
from aiohttp.test_utils import TestClient, TestServer

from database.quiz import QuizDatabase
from web.server import create_app
from web.telegram_auth import TelegramAuthError, validate_init_data

TOKEN = "123456789:test-token-for-local-tests-only"


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
    await asyncio.gather(*(db.complete(i, f"user{i}", "score_7") for i in range(1, 7)))
    await db.complete(1, None, "score_10")
    assert await db.count() == 6
    first = next(row for row in await db.participants() if row["telegram_user_id"] == 1)
    assert first["result"] == "score_10" and first["telegram_username"] is None
    assert first["completed_at"]


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
            ({"initData": "invalid", "result": "score_7"}, 401),
            ({"initData": signed(auth_date=1), "result": "score_7"}, 401),
            ({"initData": signed(), "result": "hacker"}, 400),
            ({"initData": signed(), "result": []}, 400),
            ({"initData": 123, "result": "score_7"}, 401),
            ({"initData": signed(), "result": "score_7", "telegram_user_id": 999}, 400),
            ([], 400),
        ]
        for payload, status in invalid_cases:
            response = await client.post('/api/quiz/complete', json=payload)
            assert response.status == status
        assert await db.count() == 0
        assert (await client.post('/api/quiz/complete', data='{', headers={'Content-Type': 'application/json'})).status == 400
        assert (await client.post('/api/quiz/complete', data='x')).status == 415
        assert (await client.post('/api/quiz/complete', json={'initData': 'x' * 25000, 'result': 'score_7'})).status == 413
        for result in ['score_7', 'score_10']:
            response = await client.post('/api/quiz/complete', json={'initData': signed(), 'result': result})
            assert response.status == 200 and await response.json() == {'ok': True}
        assert await db.count() == 1
        assert (await db.participants())[0]['result'] == 'score_10'
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
