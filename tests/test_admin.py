import asyncio
import csv
import io
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.methods import SendMessage
from aiogram.types import CallbackQuery, Chat, Message, MessageEntity, Update, User

from bot.__main__ import env_flag
from bot.admin import AdminOnly, BroadcastRunner, create_admin_router, parse_admin_ids, participants_csv
from bot.broadcast import send_broadcast
from database.broadcasts import BroadcastStore
from database.quiz import AlreadyCompleted, QuizDatabase

TOKEN = '123456789:local-test-token'


def prof(i=1, **over):
    base = {'last_name': 'Иванов', 'first_name': 'Иван', 'middle_name': 'Иванович',
            'course': 'b2', 'faculty': 'СНиМК',
            'student_id': f'10000{i}', 'phone': f'+7900000000{i}'}
    base.update(over)
    return base


GOOD = [2, 0, 0, 1, 2, 0, 2, 0, 2, 0]
SEVEN = [2, 0, 0, 0, 2, 1, 2, 0, 1, 0]
TIMES = [1000] * 10


@pytest_asyncio.fixture
async def storage(tmp_path):
    quiz = QuizDatabase(tmp_path / 'quiz.sqlite3')
    await quiz.initialize()
    return quiz, BroadcastStore(quiz)


def message(text='/admin', user_id=10, chat_type='private'):
    return Message(message_id=1, date=datetime.now(timezone.utc), text=text,
                   chat=Chat(id=user_id, type=chat_type), from_user=User(id=user_id, is_bot=False, first_name='Tester'))


def callback(data, user_id=10):
    return CallbackQuery(id='callback', from_user=User(id=user_id, is_bot=False, first_name='Tester'),
                         chat_instance='test', message=message(user_id=user_id), data=data)


def mock_bot():
    bot = Bot(TOKEN)
    bot.session = AsyncMock(return_value=message())
    return bot


def test_admin_ids_fail_closed():
    assert parse_admin_ids('') == frozenset()
    assert parse_admin_ids('10, 20,10') == {10, 20}
    for value in ['@name', '10,', '0', '-10', '10,abc']:
        with pytest.raises(ValueError):
            parse_admin_ids(value)


def test_boolean_environment_flag(monkeypatch):
    monkeypatch.delenv('TEST_FLAG', raising=False)
    assert env_flag('TEST_FLAG') is True
    for value in ['true', '1', 'YES', 'on']:
        monkeypatch.setenv('TEST_FLAG', value)
        assert env_flag('TEST_FLAG') is True
    for value in ['false', '0', 'No', 'off']:
        monkeypatch.setenv('TEST_FLAG', value)
        assert env_flag('TEST_FLAG') is False
    monkeypatch.setenv('TEST_FLAG', 'maybe')
    with pytest.raises(SystemExit):
        env_flag('TEST_FLAG')


@pytest.mark.asyncio
async def test_admin_filter_rejects_non_admins_and_groups():
    allowed = AdminOnly(frozenset({10}))
    assert await allowed(message())
    assert await allowed(callback('admin:stats'))
    assert not await allowed(message(user_id=11))
    assert not await allowed(message(chat_type='group'))
    assert not await allowed(callback('admin:stats', user_id=11))
    assert not await AdminOnly(frozenset())(message())


@pytest.mark.asyncio
async def test_stats_and_opt_out_survive_retake(storage):
    quiz, _ = storage
    assert (await quiz.summary())['total'] == 0
    await quiz.complete(1, 'one', SEVEN, TIMES, prof(1))
    await quiz.complete(2, None, GOOD, TIMES, prof(2))
    await quiz.set_subscribed(1, False)
    with pytest.raises(AlreadyCompleted):
        await quiz.complete(1, 'new_name', GOOD, TIMES, prof(1))
    await quiz.set_subscribed(99, False)
    summary = await quiz.summary()
    assert summary['total'] == 2 and summary['eligible'] == 1
    assert summary['by_result']['score_10'] == 1 and summary['by_result']['score_7'] == 1
    assert not await quiz.is_subscribed(1)
    await quiz.set_subscribed(1, True)
    assert (await quiz.summary())['eligible'] == 2


def test_csv_has_latest_fields_and_neutralizes_formulas():
    raw = participants_csv([{'telegram_user_id': 123, 'telegram_username': '=danger',
                             'result': 'score_7', 'last_name': 'Иванова', 'first_name': 'Анна',
                             'middle_name': 'Сергеевна', 'course': 'b2', 'faculty': 'СНиМК',
                             'student_id': '100001',
                             'phone': '+79000000001', 'completed_at': '2026-09-08T00:00:00+00:00'}])
    rows = list(csv.reader(io.StringIO(raw.decode('utf-8-sig')), delimiter=';'))
    assert rows[0][:11] == ['telegram_user_id', 'telegram_username', 'result', 'last_name',
                            'first_name', 'middle_name', 'course', 'faculty', 'student_id', 'phone', 'total_time_s']
    assert rows[0][11:21] == [f'q{i}' for i in range(1, 11)]
    assert rows[0][21:31] == [f'q{i}_s' for i in range(1, 11)]
    assert rows[0][31] == 'completed_at_utc'
    assert rows[1][0] == '123' and rows[1][1] == "'=danger" and rows[1][3] == 'Иванова'


@pytest.mark.asyncio
async def test_draft_snapshot_ownership_and_repeated_confirmation(storage):
    quiz, store = storage
    await quiz.complete(1, None, GOOD, TIMES, prof(1))
    draft = await store.create_draft(10, 'Отбор скоро 🧡', [])
    await quiz.complete(2, None, GOOD, TIMES, prof(2))
    assert await store.pending(draft) == [1]
    assert await store.get(draft, 11) is None
    assert not await store.claim(draft, 11)
    results = await asyncio.gather(store.claim(draft, 10), store.claim(draft, 10))
    assert sorted(results) == [False, True]
    another = await store.create_draft(20, 'Другая рассылка', [])
    assert not await store.claim(another, 20)


@pytest.mark.asyncio
async def test_replaced_cancelled_and_interrupted_drafts_do_not_restart(storage):
    quiz, store = storage
    await quiz.complete(1, None, GOOD, TIMES, prof(1))
    old = await store.create_draft(10, 'Старый текст', [])
    current = await store.create_draft(10, 'Новый текст', [])
    assert not await store.claim(old, 10)
    await store.cancel(current, 10)
    assert not await store.claim(current, 10)
    current = await store.create_draft(10, 'Ещё текст', [])
    assert await store.claim(current, 10)
    assert await store.claim_recipient(current, 1)
    await store.interrupt_running()
    assert (await store.get(current, 10))['status'] == 'interrupted'
    assert await store.report(current) == {'unknown': 1}
    assert not await store.claim(current, 10)


@pytest.mark.asyncio
async def test_broadcast_reports_success_errors_and_late_opt_out(storage, monkeypatch):
    quiz, store = storage
    for user_id in range(1, 6):
        await quiz.complete(user_id, None, GOOD, TIMES, prof(user_id))
    draft = await store.create_draft(10, 'Отбор', [])
    await quiz.set_subscribed(5, False)
    await store.claim(draft, 10)
    async def send(user_id, text, **kwargs):
        method = SendMessage(chat_id=user_id, text=text)
        assert kwargs['parse_mode'] is None
        if user_id == 2:
            raise TelegramForbiddenError(method=method, message='blocked')
        if user_id == 3:
            raise TelegramNetworkError(method=method, message='timeout')
        if user_id == 4:
            raise TelegramBadRequest(method=method, message='chat not found')
    bot = AsyncMock()
    bot.send_message.side_effect = send
    monkeypatch.setattr('bot.broadcast.asyncio.sleep', AsyncMock())
    await send_broadcast(bot, quiz, store, draft, 'Отбор', [])
    assert bot.send_message.await_count == 4
    assert await store.report(draft) == {'sent': 1, 'unavailable': 1, 'unknown': 1, 'failed': 1, 'skipped': 1}
    assert (await store.get(draft, 10))['status'] == 'finished'


@pytest.mark.asyncio
async def test_rate_limit_retry_preserves_entities(storage, monkeypatch):
    quiz, store = storage
    await quiz.complete(1, None, GOOD, TIMES, prof(1))
    entities = [{'type': 'bold', 'offset': 0, 'length': 5}]
    draft = await store.create_draft(10, 'Отбор', entities)
    await store.claim(draft, 10)
    bot = AsyncMock()
    bot.send_message.side_effect = [TelegramRetryAfter(method=SendMessage(chat_id=1, text='Отбор'), message='slow down', retry_after=2), None]
    sleep = AsyncMock()
    monkeypatch.setattr('bot.broadcast.asyncio.sleep', sleep)
    await send_broadcast(bot, quiz, store, draft, 'Отбор', entities)
    assert bot.send_message.await_count == 2
    assert bot.send_message.await_args.kwargs['entities'] == [MessageEntity(**entities[0])]
    assert await store.report(draft) == {'sent': 1}
    sleep.assert_any_await(2.1)


@pytest.mark.asyncio
async def test_cancel_during_rate_limit_stops_retry(storage, monkeypatch):
    quiz, store = storage
    await quiz.complete(1, None, GOOD, TIMES, prof(1))
    draft = await store.create_draft(10, 'Отбор', [])
    await store.claim(draft, 10)
    bot = AsyncMock()
    bot.send_message.side_effect = TelegramRetryAfter(method=SendMessage(chat_id=1, text='Отбор'), message='slow', retry_after=1)
    async def sleep(_):
        await store.cancel(draft, 10)
    monkeypatch.setattr('bot.broadcast.asyncio.sleep', sleep)
    await send_broadcast(bot, quiz, store, draft, 'Отбор', [])
    assert bot.send_message.await_count == 1
    assert (await store.get(draft, 10))['status'] == 'cancelled'


@pytest.mark.asyncio
async def test_admin_router_preview_requires_confirmation_and_auth(storage):
    quiz, store = storage
    await quiz.complete(1, None, GOOD, TIMES, prof(1))
    runner = BroadcastRunner(quiz, store)
    runner.launch = AsyncMock()
    dispatcher = Dispatcher()
    dispatcher.include_router(create_admin_router(quiz, frozenset({10}), runner))
    bot = mock_bot()
    await dispatcher.feed_update(bot, Update(update_id=1, message=message('/admin', user_id=11)))
    await dispatcher.feed_update(bot, Update(update_id=2, callback_query=callback('admin:stats', user_id=11)))
    assert bot.session.await_count == 0
    await dispatcher.feed_update(bot, Update(update_id=3, message=message('/broadcast')))
    await dispatcher.feed_update(bot, Update(update_id=4, message=message('Отбор в пятницу 🧡')))
    runner.launch.assert_not_called()
    draft = (await store.recent(10))[0]
    assert draft['status'] == 'draft'
    sent = [call.args[1] for call in bot.session.await_args_list]
    assert any(getattr(method, 'text', '') == 'Отбор в пятницу 🧡' for method in sent)
    await dispatcher.feed_update(bot, Update(update_id=5, callback_query=callback(f"bc:send:{draft['id']}", user_id=11)))
    runner.launch.assert_not_called()
    # launch is synchronous; a regular mock avoids spawning a real broadcast.
    from unittest.mock import Mock
    runner.launch = Mock()
    for update_id in [6, 7]:
        await dispatcher.feed_update(bot, Update(update_id=update_id, callback_query=callback(f"bc:send:{draft['id']}")))
    runner.launch.assert_called_once()
    await dispatcher.storage.close()


@pytest.mark.asyncio
async def test_message_length_validation(storage):
    _, store = storage
    for text in ['', ' ', '🧡' * 2049]:
        with pytest.raises(ValueError):
            await store.create_draft(10, text, [])


@pytest.mark.asyncio
async def test_runner_sends_and_reports_without_blocking_router(storage, monkeypatch):
    quiz, store = storage
    await quiz.complete(1, None, GOOD, TIMES, prof(1))
    broadcast_id = await store.create_draft(10, 'Отбор открыт', [])
    await store.claim(broadcast_id, 10)
    runner = BroadcastRunner(quiz, store)
    bot = AsyncMock()
    monkeypatch.setattr('bot.broadcast.asyncio.sleep', AsyncMock())
    runner.launch(bot, await store.get(broadcast_id, 10))
    await asyncio.gather(*runner.tasks)
    calls = bot.send_message.await_args_list
    assert calls[0].args == (1, 'Отбор открыт')
    assert calls[1].args[0] == 10 and 'Принято Telegram: 1' in calls[1].args[1]
    assert (await store.get(broadcast_id, 10))['status'] == 'finished'
    await runner.close()


@pytest.mark.asyncio
async def test_existing_schema_migrates_without_losing_participants(tmp_path):
    import aiosqlite
    path = tmp_path / 'legacy.sqlite3'
    async with aiosqlite.connect(path) as db:
        await db.execute('CREATE TABLE quiz_users (telegram_user_id INTEGER PRIMARY KEY, telegram_username TEXT, result TEXT NOT NULL, completed_at DATETIME NOT NULL)')
        await db.execute("INSERT INTO quiz_users VALUES (1, NULL, 'backend', '2026-09-08')")
        await db.commit()
    quiz = QuizDatabase(path)
    await quiz.initialize()
    assert await quiz.count() == 1
    assert (await quiz.participants())[0]['result'] == 'score_5'
    draft = await BroadcastStore(quiz).create_draft(10, 'Отбор', [])
    assert await BroadcastStore(quiz).pending(draft) == [1]
