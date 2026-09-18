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


def participants_csv(rows: list[dict], details: dict[int, dict] | None = None) -> bytes:
    from database.quiz import QUESTIONS
    details = details or {}
    # Semicolons: Russian Excel splits rows by ; out of the box.
    output = io.StringIO(newline='')
    writer = csv.writer(output, delimiter=';')
    header = (['telegram_user_id', 'telegram_username', 'result',
               'last_name', 'first_name', 'middle_name', 'course', 'faculty',
               'student_id', 'phone', 'total_time_s'] +
              [f'q{i + 1}' for i in range(len(QUESTIONS))] +
              [f'q{i + 1}_s' for i in range(len(QUESTIONS))] +
              ['completed_at_utc'])
    writer.writerow(header)
    for row in rows:
        # Prevent formula interpretation in spreadsheet apps, including unusual
        # signed usernames. Identity remains the numeric Telegram ID.
        username = row['telegram_username'] or ''
        if username.startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
            username = "'" + username
        entry = details.get(row['telegram_user_id'], {})
        flags = entry.get('flags') or [None] * len(QUESTIONS)
        times = entry.get('times') or [None] * len(QUESTIONS)
        total = row.get('total_ms')
        result = row['result']
        score = result.split('_')[1] if isinstance(result, str) and '_' in result else result
        writer.writerow([row['telegram_user_id'], username, score,
                         row.get('last_name') or '', row.get('first_name') or '',
                         row.get('middle_name') or '', _course_label(row.get('course')),
                         row.get('faculty') or '',
                         row.get('student_id') or '', row.get('phone') or '',
                         _fmt_secs(total) if total is not None else ''] +
                        ['' if flag is None else flag for flag in flags] +
                        ['' if ms is None else _fmt_secs(ms) for ms in times] +
                        [row['completed_at']])
    return output.getvalue().encode('utf-8-sig')


def _fmt_secs(ms: int | float) -> str:
    seconds = (ms or 0) / 1000
    if seconds >= 60:
        minutes = int(seconds // 60)
        return f"{minutes}м {seconds - minutes * 60:04.1f}с"
    return f"{seconds:.1f}с"


def _course_label(course: object) -> str:
    from database.quiz import COURSE_LABELS, LEGACY_COURSES
    if isinstance(course, int) and not isinstance(course, bool):
        return COURSE_LABELS.get(LEGACY_COURSES.get(course, course), str(course))
    return COURSE_LABELS.get(course, str(course or ''))


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
        by_result = summary['by_result']
        avg_score = (sum(int(key.split('_')[1]) * count for key, count in by_result.items()) / total) if total else 0
        general = [f"Участников: {total} уникальных", '']
        nonzero = [(int(key.split('_')[1]), count) for key, count in by_result.items() if count]
        for score, count in sorted(nonzero):
            general.append(f'{score}/10: {count} ({count * 100 / total:.1f}%)')
        general.extend(['', f'Средний балл: {avg_score:.1f}/10',
                        f"В списке рассылки: {summary['eligible']}",
                        f"Отписались: {total - summary['eligible']}",
                        f"Дублей по телефону: {summary.get('dup_phones', 0)}",
                        f"Дублей по студбилету: {summary.get('dup_student_ids', 0)}",
                        'Попытка одна: засчитывается первый результат.'])
        await message.answer('\n'.join(general), parse_mode=None)

        from database.quiz import COURSES, COURSE_LABELS, FACULTIES
        by_course = summary.get('by_course', {})
        courses = [f"{COURSE_LABELS[course]}: {by_course.get(course, 0)}"
                   + (f" ({by_course[course] * 100 / total:.1f}%)" if total else '')
                   for course in COURSES]
        leader = max(COURSES, key=lambda course: by_course.get(course, 0)) if total else None
        await message.answer('Курсы:\n' + '\n'.join(courses) +
                             (f"\n\nЧаще всего проходит: {COURSE_LABELS[leader]}" if leader else ''),
                             parse_mode=None)

        by_faculty = summary.get('by_faculty', {})
        faculties = [f"{faculty}: {by_faculty.get(faculty, 0)}"
                     + (f" ({by_faculty[faculty] * 100 / total:.1f}%)" if total else '')
                     for faculty in FACULTIES]
        top_faculty = max(FACULTIES, key=lambda faculty: by_faculty.get(faculty, 0)) if total else None
        await message.answer('Факультеты:\n' + '\n'.join(faculties) +
                             (f"\n\nСамый активный: {top_faculty}" if top_faculty else ''),
                             parse_mode=None)

        questions = summary.get('questions', [])
        ranked = sorted(enumerate(questions, start=1), key=lambda item: item[1]['pct'])
        lines = []
        for number, question in ranked:
            if question['attempts']:
                lines.append(f"{number}. {question['label']} — {question['pct']:.0f}% верных "
                             f"(n={question['attempts']}, ср. {_fmt_secs(question['avg_ms'])})")
            else:
                lines.append(f"{number}. {question['label']} — пока нет данных")
        await message.answer('Вопросы (от сложного к простому):\n' + '\n'.join(lines), parse_mode=None)

        timed = summary.get('timed_count', 0)
        avg_total = summary.get('avg_total_ms', 0)
        await message.answer(
            f"Время (замер с открытия вопроса до ответа):\n"
            f"Среднее суммарное: {_fmt_secs(avg_total)} (n={timed})\n"
            f"Среднее на вопрос: {_fmt_secs(avg_total / 10) if timed else '—'}\n\n"
            f"Посещения, незавершённые тесты и прочтения не отслеживаются.",
            parse_mode=None)

    async def export(message: Message) -> None:
        rows = await quiz.participants()
        details = await quiz.answer_details()
        await message.answer_document(BufferedInputFile(participants_csv(rows, details), filename='quiz_participants.csv'),
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
