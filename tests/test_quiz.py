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
            'course': 'b2', 'faculty': 'СНиМК',
            'student_id': f'10000{i}', 'phone': f'+7900000000{i}'}
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
    from database.quiz import score_answers
    db = QuizDatabase(tmp_path / "quiz.sqlite3")
    await db.initialize()
    assert await db.count() == 0
    good = [2, 0, 0, 1, 2, 0, 2, 0, 2, 0]
    times = [1000, 900, 800, 1200, 1100, 950, 1050, 700, 1300, 600]
    await asyncio.gather(*(db.complete(i, f"user{i}", good, times, prof(i)) for i in range(1, 7)))
    assert await db.count() == 6
    with pytest.raises(AlreadyCompleted):
        await db.complete(1, None, good, times, prof(1))
    assert await db.count() == 6
    first = next(row for row in await db.participants() if row["telegram_user_id"] == 1)
    assert first["result"] == "score_10" and first["phone"] == "+79000000001"
    assert first["total_ms"] == sum(times)
    summary = await db.summary()
    assert summary["questions"][0]["attempts"] == 6
    assert summary["questions"][0]["correct"] == 6
    assert summary["questions"][0]["pct"] == 100.0
    assert summary["avg_total_ms"] == sum(times)
    assert summary["by_course"]['b2'] == 6
    assert summary["by_faculty"]['СНиМК'] == 6


def test_answers_times_and_scoring():
    from database.quiz import score_answers, validate_answers, validate_times
    good = [2, 0, 0, 1, 2, 0, 2, 0, 2, 0]
    assert validate_answers(good) == good
    assert score_answers(good) == ("score_10", 10, [1] * 10)
    mixed = [0, 0, 0, 1, 2, 0, 2, 0, 2, 0]
    assert score_answers(mixed)[0] == "score_9"
    assert validate_times([1000] * 10) == [1000] * 10
    for bad_answers in [None, [], [0] * 9, [0] * 11, [4, 0, 0, 1, 2, 0, 2, 0, 2, 0],
                        ["2", 0, 0, 1, 2, 0, 2, 0, 2, 0], [True, 0, 0, 1, 2, 0, 2, 0, 2, 0]]:
        with pytest.raises(ValueError):
            validate_answers(bad_answers)
    for bad_times in [None, [1000] * 9, [1000] * 10 + [-1], ["1000"] * 10, [True] * 10,
                      [3_600_001] + [1000] * 9]:
        with pytest.raises(ValueError):
            validate_times(bad_times)


def test_profile_validation():
    assert validate_profile(prof(1))["phone"] == "+79000000001"
    assert validate_profile(prof(1, phone="89000000001"))["phone"] == "+79000000001"
    assert validate_profile(prof(1, phone="9000000001"))["phone"] == "+79000000001"
    assert validate_profile(prof(1, course="m1"))["course"] == "m1"
    for bad in [None, [], {**prof(1), "extra": 1},
                prof(1, last_name=""), prof(1, first_name="123"),
                prof(1, course=0), prof(1, course=7), prof(1, course="x"), prof(1, course="b5"),
                prof(1, faculty="Хогвартс"), prof(1, faculty=""),
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
    good = [2, 0, 0, 1, 2, 0, 2, 0, 2, 0]
    times = [1000] * 10
    assert await db.complete(1, "late_name", good, times, prof(1)) == ("score_7", "profile_updated")
    row = (await db.participants())[0]
    assert row["result"] == "score_7" and row["phone"] == "+79000000001"
    with pytest.raises(AlreadyCompleted):
        await db.complete(1, None, good, times, prof(1))


@pytest.mark.asyncio
async def test_api_validation_and_persistence(tmp_path):
    db_path = tmp_path / "quiz.sqlite3"
    db = QuizDatabase(db_path)
    app = create_app(bot_token=TOKEN, database_path=db_path)
    async with TestClient(TestServer(app)) as client:
        health = await client.get('/healthz')
        assert health.status == 200 and await health.json() == {'status': 'ok'}
        assert await db.count() == 0
        good = [2, 0, 0, 1, 2, 0, 2, 0, 2, 0]
        times = [1000, 900, 800, 1200, 1100, 950, 1050, 700, 1300, 600]
        base = {"initData": signed(), "answers": good, "times": times, "profile": prof(1)}
        invalid_cases = [
            ({**base, "initData": "invalid"}, 401),
            ({**base, "initData": signed(auth_date=1)}, 401),
            ({**base, "answers": [0] * 10}, 200),
            ({**base, "answers": [99] + good[1:]}, 400),
            ({**base, "answers": good[:9]}, 400),
            ({**base, "answers": "nope"}, 400),
            ({**base, "times": [1000] * 9}, 400),
            ({**base, "times": [-1] + times[1:]}, 400),
            ({**base, "times": "fast"}, 400),
            ({**base, "profile": {"bad": 1}}, 400),
            ({**base, "profile": prof(1, phone="x")}, 400),
            ({"initData": signed(), "answers": good, "times": times}, 400),
            ({"initData": signed(), "answers": good, "profile": prof(1)}, 400),
            ({"initData": signed(), "result": "score_7", "profile": prof(1)}, 400),
            ({**base, "telegram_user_id": 999}, 400),
            ({"initData": 123, "answers": good, "times": times, "profile": prof(1)}, 401),
            ([], 400),
        ]
        for payload, status in invalid_cases:
            response = await client.post('/api/quiz/complete', json=payload)
            assert response.status == status, payload
        assert await db.count() == 1
        row = (await db.participants())[0]
        assert row["result"] == "score_5" and row["total_ms"] == sum(times)
        summary = await db.summary()
        assert summary["questions"][0]["correct"] == 0
        assert summary["questions"][1]["correct"] == 1
        assert summary["questions"][0]["avg_ms"] == 1000
        response = await client.post('/api/quiz/complete', json=base)
        assert response.status == 409 and await response.json() == {'error': 'already_completed'}
        assert (await client.get('/api/quiz/complete')).status == 405


@pytest.mark.asyncio
async def test_admin_overview_auth_and_shape(tmp_path):
    from urllib.parse import quote
    db_path = tmp_path / "quiz.sqlite3"
    db = QuizDatabase(db_path)
    await db.initialize()
    good = [2, 0, 0, 1, 2, 0, 2, 0, 2, 0]
    times = [1000] * 10
    await db.complete(1, "one", good, times, prof(1))
    await db.complete(2, None, [0] * 10, [2000] * 10, prof(2, course="m1", faculty="ВШУ"))

    async def get(client, init_data):
        return await client.get("/api/admin/overview?initData=" + quote(init_data, safe=""))

    async with TestClient(TestServer(create_app(bot_token=TOKEN, database_path=db_path))) as client:
        assert (await get(client, "invalid")).status == 401
        assert (await get(client, signed())).status == 403

    async with TestClient(TestServer(create_app(bot_token=TOKEN, database_path=db_path,
                                                admin_ids=frozenset({123456})))) as client:
        response = await get(client, signed())
        assert response.status == 200
        body = await response.json()
        assert body["ok"] is True and body["total"] == 2
        assert body["avg_score"] == 7.5
        assert body["by_result"]["10"] == 1 and body["by_result"]["5"] == 1
        assert body["by_result"]["0"] == 0 and len(body["by_result"]) == 11
        assert body["by_course"]["b2"] == 1 and body["by_course"]["m1"] == 1
        assert body["by_course"]["b1"] == 0 and len(body["by_course"]) == 6
        assert body["by_faculty"]["СНиМК"] == 1 and body["by_faculty"]["ВШУ"] == 1
        assert len(body["by_faculty"]) == 8
        assert body["matrix"]["СНиМК"]["b2"] == 1 and body["matrix"]["ВШУ"]["m1"] == 1
        assert len(body["questions"]) == 10 and body["questions"][0]["attempts"] == 2
        assert body["timed_count"] == 2 and body["avg_total_ms"] == 15000
        stranger = signed(user={"id": 999, "username": "x"})
        assert (await get(client, stranger)).status == 403


@pytest.mark.asyncio
async def test_quiz_status_locks_retakes_but_not_admins(tmp_path):
    from urllib.parse import quote
    db_path = tmp_path / "quiz.sqlite3"
    db = QuizDatabase(db_path)
    await db.initialize()
    good = [2, 0, 0, 1, 2, 0, 2, 0, 2, 0]
    await db.complete(1, "one", good, [1000] * 10, prof(1))

    async def get(client, init_data):
        return await client.get("/api/quiz/status?initData=" + quote(init_data, safe=""))

    async with TestClient(TestServer(create_app(bot_token=TOKEN, database_path=db_path))) as client:
        assert (await get(client, "invalid")).status == 401
        body = await (await get(client, signed())).json()
        assert body == {"ok": True, "completed": False, "is_admin": False}
        other = signed(user={"id": 777, "username": "new"})
        body = await (await get(client, other)).json()
        assert body["completed"] is False
        mine = signed(user={"id": 1, "username": "one"})
        body = await (await get(client, mine)).json()
        assert body == {"ok": True, "completed": True, "score": "10",
                        "result": "score_10", "is_admin": False}

    async with TestClient(TestServer(create_app(bot_token=TOKEN, database_path=db_path,
                                                admin_ids=frozenset({1})))) as client:
        body = await (await get(client, signed(user={"id": 1, "username": "one"}))).json()
        assert body["completed"] is True and body["is_admin"] is True


@pytest.mark.asyncio
async def test_raffle_draw_and_history(tmp_path):
    db_path = tmp_path / "quiz.sqlite3"
    db = QuizDatabase(db_path)
    await db.initialize()
    good = [2, 0, 0, 1, 2, 0, 2, 0, 2, 0]
    times = [1000] * 10
    for i in range(1, 4):
        await db.complete(i, f"user{i}", good, times, prof(i))
    with pytest.raises(ValueError):
        await db.draw_winners(10, 0)
    with pytest.raises(ValueError):
        await db.draw_winners(10, 99)
    draw_id, winners = await db.draw_winners(10, 2)
    assert draw_id == 1 and len(winners) == 2
    assert len({w["telegram_user_id"] for w in winners}) == 2
    assert all(w["phone"].startswith("+79") for w in winners)
    history = await db.recent_raffles()
    assert len(history) == 1 and history[0]["admin_id"] == 10
    assert {w["telegram_user_id"] for w in history[0]["winners"]} == {w["telegram_user_id"] for w in winners}


@pytest.mark.asyncio
async def test_raffle_endpoint_auth_and_validation(tmp_path):
    db_path = tmp_path / "quiz.sqlite3"
    db = QuizDatabase(db_path)
    await db.initialize()
    good = [2, 0, 0, 1, 2, 0, 2, 0, 2, 0]
    await db.complete(1, "one", good, [1000] * 10, prof(1))
    app = create_app(bot_token=TOKEN, database_path=db_path, admin_ids=frozenset({123456}))
    async with TestClient(TestServer(app)) as client:
        assert (await client.post("/api/admin/raffle", data="x")).status == 415
        assert (await client.post("/api/admin/raffle", json={"initData": "bad", "count": 1})).status == 401
        stranger = signed(user={"id": 999, "username": "x"})
        assert (await client.post("/api/admin/raffle", json={"initData": stranger, "count": 1})).status == 403
        me = signed()
        assert (await client.post("/api/admin/raffle", json={"initData": me})).status == 400
        for bad_count in [0, 21, "1", 1.5, None]:
            response = await client.post("/api/admin/raffle", json={"initData": me, "count": bad_count})
            assert response.status == 400
        response = await client.post("/api/admin/raffle", json={"initData": me, "count": 5})
        assert response.status == 400
        response = await client.post("/api/admin/raffle", json={"initData": me, "count": 1})
        assert response.status == 200
        body = await response.json()
        assert body["ok"] is True and body["draw_id"] == 1 and len(body["winners"]) == 1
        assert body["winners"][0]["telegram_user_id"] == 1
        from urllib.parse import quote
        overview = await (await client.get("/api/admin/overview?initData=" + quote(me, safe=""))).json()
        assert len(overview["raffles"]) == 1 and overview["raffles"][0]["id"] == 1


@pytest.mark.asyncio
async def test_allowlist_parse_filter_and_draw(tmp_path):
    from database.quiz import QuizDatabase
    db = QuizDatabase(tmp_path / "quiz.sqlite3")
    await db.initialize()
    entries, rejected = QuizDatabase.parse_allowlist("@Ivan_Petrov, tester\n123456789  @ivan_petrov\n@@, ab, x")
    assert entries == [("ivan_petrov", "username"), ("tester", "username"), ("123456789", "user_id")]
    assert rejected == ["@@", "ab", "x"]
    assert QuizDatabase.parse_allowlist(None) == ([], [])
    assert QuizDatabase.parse_allowlist("") == ([], [])

    good = [2, 0, 0, 1, 2, 0, 2, 0, 2, 0]
    times = [1000] * 10
    await db.complete(1, "ivan_petrov", good, times, prof(1))
    await db.complete(2, "stranger", good, times, prof(2))
    await db.complete(3, None, good, times, prof(3))
    added, rejected = await db.set_allowlist(10, "@ivan_petrov, 3, nope!")
    assert added == 2 and rejected == ["nope!"]
    current = await db.get_allowlist()
    assert {(e["value"], e["kind"]) for e in current} == {("ivan_petrov", "username"), ("3", "user_id")}
    eligible = await db.eligible_participants(True)
    assert {row["telegram_user_id"] for row in eligible} == {1, 3}
    assert len(await db.eligible_participants(False)) == 3
    draw_id, winners = await db.draw_winners(10, 2, True)
    assert draw_id == 1 and {w["telegram_user_id"] for w in winners} == {1, 3}
    with pytest.raises(ValueError):
        await db.draw_winners(10, 3, True)
    await db.set_allowlist(10, "")
    assert await db.get_allowlist() == []
    with pytest.raises(ValueError):
        await db.eligible_participants(True)


@pytest.mark.asyncio
async def test_allowlist_endpoint_and_filtered_draw(tmp_path):
    db_path = tmp_path / "quiz.sqlite3"
    db = QuizDatabase(db_path)
    await db.initialize()
    good = [2, 0, 0, 1, 2, 0, 2, 0, 2, 0]
    await db.complete(1, "ivan_petrov", good, [1000] * 10, prof(1))
    await db.complete(2, "stranger_x", good, [1000] * 10, prof(2))
    app = create_app(bot_token=TOKEN, database_path=db_path, admin_ids=frozenset({123456}))
    async with TestClient(TestServer(app)) as client:
        me = signed()
        stranger = signed(user={"id": 999, "username": "x"})
        assert (await client.post("/api/admin/allowlist", json={"initData": "bad", "entries": "one"})).status == 401
        assert (await client.post("/api/admin/allowlist", json={"initData": stranger, "entries": "one"})).status == 403
        assert (await client.post("/api/admin/allowlist", json={"initData": me})).status == 400
        response = await client.post("/api/admin/allowlist", json={"initData": me, "entries": 123})
        assert response.status == 400
        response = await client.post("/api/admin/allowlist", json={"initData": me, "entries": "@Ivan_Petrov, 2, nope!"})
        assert response.status == 200
        body = await response.json()
        assert body == {"ok": True, "added": 2, "rejected": ["nope!"], "total": 2, "eligible": 2}
        response = await client.post("/api/admin/raffle", json={"initData": me, "count": 3, "only_allowlisted": True})
        assert response.status == 400
        response = await client.post("/api/admin/raffle", json={"initData": me, "count": 1, "only_allowlisted": True})
        assert response.status == 200
        body = await response.json()
        assert body["filtered"] is True and body["winners"][0]["telegram_user_id"] in (1, 2)
        response = await client.post("/api/admin/raffle", json={"initData": me, "count": 1, "only_allowlisted": "yes"})
        assert response.status == 400
        from urllib.parse import quote
        overview = await (await client.get("/api/admin/overview?initData=" + quote(me, safe=""))).json()
        assert len(overview["allowlist"]) == 2
        assert overview["raffles"][0]["filtered"] is True


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
