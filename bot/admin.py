"""Admin UI in a private Telegram chat; no public admin HTTP endpoints."""
import asyncio
import csv
import io
import json
import logging
from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import BaseFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.broadcast import send_broadcast
from database.broadcasts import BroadcastStore
from database.quiz import QuizDatabase

logger = logging.getLogger(__name__)
SCORE_LABELS = {f'score_{i}': f'{i}/10' for i in range(11)}
STATUS_LABELS = {
    'draft': 'черновик', 'running': 'отправляется', 'finished': 'завершена',
    'cancelled': 'отменена', 'interrupted': 'прервана',
}


def parse_admin_ids(value: str) -> frozenset[int]:
    if not value.strip():
        return frozenset()
    try:
        parts = value.split(',')
        ids = frozenset(int(part.strip()) for part in parts)
        if any(user_id <= 0 for user_id in ids):
            raise ValueError
        return ids
    except ValueError as exc:
        raise ValueError('ADMIN_IDS must be positive Telegram user IDs separated by commas') from exc


class AdminOnly(BaseFilter):
    def __init__(self, admin_ids: frozenset[int]):
        self.admin_ids = admin_ids

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        message = event if isinstance(event, Message) else event.message
        return bool(event.from_user and event.from_user.id in self.admin_ids
                    and isinstance(message, Message) and message.chat.type == 'private')


class Compose(StatesGroup):
    text = State()


def panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📊 Статистика', callback_data='admin:stats')],
        [InlineKeyboardButton(text='📄 Участники — CSV', callback_data='admin:participants')],
        [InlineKeyboardButton(text='✉️ Написать рассылку', callback_data='admin:broadcast')],
        [InlineKeyboardButton(text='🧾 Мои последние рассылки', callback_data='admin:history')],
    ])


def delivery_report(counts: dict[str, int]) -> str:
    return (
        f"Получателей в списке: {sum(counts.values())}\n"
        f"Принято Telegram: {counts.get('sent', 0)}\n"
        f"Бот заблокирован / нет права писать: {counts.get('unavailable', 0)}\n"
        f"Ошибки отправки: {counts.get('failed', 0)}\n"
        f"Неизвестный исход: {counts.get('unknown', 0)}\n"
        f"Пропущено: {counts.get('skipped', 0)}\n"
        f"Осталось: {counts.get('pending', 0) + counts.get('sending', 0)}\n"
        "Принято Telegram ≠ прочитано пользователем."
    )


def participants_csv(rows: list[dict]) -> bytes:
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(['telegram_user_id', 'telegram_username', 'result',
                     'last_name', 'first_name', 'middle_name', 'course',
                     'student_id', 'phone', 'completed_at_utc'])
    for row in rows:
        # Prevent formula interpretation in spreadsheet apps, including unusual
        # signed usernames. Identity remains the numeric Telegram ID.
        username = row['telegram_username'] or ''
        if username.startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
            username = "'" + username
        writer.writerow([row['telegram_user_id'], username, row['result'],
                         row.get('last_name') or '', row.get('first_name') or '',
                         row.get('middle_name') or '', row.get('course') or '',
                         row.get('student_id') or '', row.get('phone') or '',
                         row['completed_at']])
    return output.getvalue().encode('utf-8-sig')


class BroadcastRunner:
    def __init__(self, quiz: QuizDatabase, store: BroadcastStore):
        self.quiz, self.store = quiz, store
        self.tasks: set[asyncio.Task] = set()

    def launch(self, bot: Bot, draft: dict) -> None:
        task = asyncio.create_task(self._run(bot, draft))
        self.tasks.add(task)
        task.add_done_callback(self._done)

    def _done(self, task: asyncio.Task) -> None:
        self.tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.error('Broadcast task failed; inspect the admin journal after restart')

    async def _run(self, bot: Bot, draft: dict) -> None:
        try:
            await send_broadcast(bot, self.quiz, self.store, draft['id'], draft['text'], json.loads(draft['entities']))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.error('Broadcast interrupted; see the admin journal')
            # There is only one running broadcast in this process/database.
            await self.store.interrupt_running()
        try:
            current = await self.store.get(draft['id'], draft['admin_id'])
            report = await self.store.report(draft['id'])
            with suppress(TelegramAPIError):
                await bot.send_message(draft['admin_id'],
                    f"Рассылка: {STATUS_LABELS.get(current['status'], current['status'])}\n\n" + delivery_report(report),
                    parse_mode=None)
        except Exception:
            logger.error('Could not deliver broadcast summary; it remains in the admin journal')

    async def close(self) -> None:
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.store.interrupt_running()


def create_admin_router(quiz: QuizDatabase, admin_ids: frozenset[int], runner: BroadcastRunner) -> Router:
    router = Router(name='admin')
    router.message.filter(AdminOnly(admin_ids))
    router.callback_query.filter(AdminOnly(admin_ids))
    store = runner.store

    async def stats(message: Message) -> None:
        summary = await quiz.summary()
        total = summary['total']
        lines = [f"Завершили тест: {total} уникальных участников", '']
        for result_id in sorted(summary['by_result'], key=lambda k: int(k.split('_')[1])):
            count = summary['by_result'][result_id]
            percent = count * 100 / total if total else 0
            lines.append(f'{SCORE_LABELS.get(result_id, result_id)}: {count} ({percent:.1f}%)')
        lines.extend(['', f"В списке рассылки: {summary['eligible']}",
                      f"Отписались: {total - summary['eligible']}",
                      f"Дублей по телефону: {summary.get('dup_phones', 0)}",
                      f"Дублей по студбилету: {summary.get('dup_student_ids', 0)}",
                      'Одна попытка на человека: повторные прохождения отклоняются, засчитывается первый результат.',
                      'Посещения, незавершённые тесты и прочтения не отслеживаются.'])
        await message.answer('\n'.join(lines), parse_mode=None)

    async def export(message: Message) -> None:
        rows = await quiz.participants()
        await message.answer_document(BufferedInputFile(participants_csv(rows), filename='quiz_participants.csv'),
                                      caption=f'Участников: {len(rows)}. Дата — последнее завершение, UTC.')

    async def compose(message: Message, state: FSMContext) -> None:
        await state.set_state(Compose.text)
        await message.answer('Пришли текст рассылки про ША (до 4096 символов). '
                             'Ссылки и форматирование сохранятся. Затем покажу предпросмотр и число получателей.\n\n'
                             '/cancel — отменить. Пока ничего не отправляется участникам.')

    async def history(message: Message, admin_id: int) -> None:
        rows = await store.recent(admin_id)
        if not rows:
            await message.answer('У тебя пока нет рассылок.')
        for row in rows:
            counts = await store.report(row['id'])
            await message.answer(f"{row['created_at']}\n{STATUS_LABELS[row['status']]}\n\n" + delivery_report(counts), parse_mode=None)

    @router.message(Command('admin'))
    async def panel(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer('Админка ША\n\nСтатистика участников и рассылка.', reply_markup=panel_keyboard())

    @router.message(Command('stats'))
    async def stats_command(message: Message) -> None:
        await stats(message)

    @router.message(Command('participants'))
    async def export_command(message: Message) -> None:
        await export(message)

    @router.message(Command('broadcast'))
    async def broadcast_command(message: Message, state: FSMContext) -> None:
        await compose(message, state)

    @router.message(Command('cancel'))
    async def cancel_command(message: Message, state: FSMContext) -> None:
        await state.clear()
        await store.cancel_admin(message.from_user.id)
        await message.answer('Твои черновики отменены, активная рассылка остановлена. Уже отправленные сообщения остаются у получателей.')

    @router.callback_query(F.data.in_({'admin:stats', 'admin:participants', 'admin:broadcast', 'admin:history'}))
    async def menu(query: CallbackQuery, state: FSMContext) -> None:
        await query.answer()
        await state.clear()
        action = query.data.split(':')[1]
        if action == 'stats':
            await stats(query.message)
        elif action == 'participants':
            await export(query.message)
        elif action == 'broadcast':
            await compose(query.message, state)
        else:
            await history(query.message, query.from_user.id)

    @router.callback_query(F.data.regexp(r'^bc:(send|cancel):[0-9a-f]{32}$'))
    async def confirm(query: CallbackQuery, bot: Bot) -> None:
        _, action, broadcast_id = query.data.split(':')
        draft = await store.get(broadcast_id, query.from_user.id)
        if not draft:
            await query.answer('Этот черновик недоступен.', show_alert=True)
            return
        if action == 'cancel':
            cancelled = await store.cancel(broadcast_id, query.from_user.id)
            await query.answer('Рассылка отменена.' if cancelled else 'Рассылка уже завершена.')
            return
        if not await store.claim(broadcast_id, query.from_user.id):
            await query.answer('Уже отправлено, отменено или другая рассылка ещё идёт. Проверь журнал.', show_alert=True)
            return
        runner.launch(bot, draft)
        await query.answer('Рассылка запущена. Отчёт придёт сюда.')

    @router.message(Compose.text, F.text, ~F.text.startswith('/'))
    async def draft_message(message: Message, state: FSMContext) -> None:
        entities = [entity.model_dump(exclude_none=True, mode='json') for entity in (message.entities or [])]
        try:
            broadcast_id = await store.create_draft(message.from_user.id, message.text, entities)
        except ValueError:
            await message.answer('Нужен непустой текст до 4096 символов (эмодзи могут занимать два). Попробуй ещё раз.')
            return
        await state.clear()
        counts = await store.report(broadcast_id)
        await message.answer('Предпросмотр сообщения:')
        await message.answer(message.text, entities=message.entities, parse_mode=None)
        count = sum(counts.values())
        buttons = []
        if count:
            buttons.append([InlineKeyboardButton(text=f'Отправить участникам ({count})', callback_data=f'bc:send:{broadcast_id}')])
        buttons.append([InlineKeyboardButton(text='Отменить / остановить', callback_data=f'bc:cancel:{broadcast_id}')])
        await message.answer(f'Получателей: {count}. Только завершившие тест и не отписавшиеся. '
                             'Новые участники после этого предпросмотра в эту рассылку не добавляются.\n\n'
                             'Отправка начнётся только по кнопке. Для правок отправь /broadcast.',
                             reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

    @router.message(Compose.text)
    async def unsupported(message: Message) -> None:
        await message.answer('Для рассылки нужен текст. Фото и файлы пока не поддерживаются. /cancel — отменить.')

    return router
