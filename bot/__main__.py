import asyncio
import logging
import os
from pathlib import Path
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from dotenv import load_dotenv

from web.server import quiz_server
from database.quiz import QuizDatabase
from database.broadcasts import BroadcastStore
from bot.admin import BroadcastRunner, create_admin_router, parse_admin_ids

ROOT = Path(__file__).resolve().parent.parent


def env_flag(name: str, default: bool = True) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {'1', 'true', 'yes', 'on'}:
        return True
    if normalized in {'0', 'false', 'no', 'off'}:
        return False
    raise SystemExit(f'{name} must be true or false')


async def main() -> None:
    load_dotenv(ROOT / ".env")
    token = os.environ.get("BOT_TOKEN", "").strip()
    mini_app_url = os.environ.get("MINI_APP_URL", "").strip()
    parsed_url = urlparse(mini_app_url)
    polling_enabled = env_flag('BOT_POLLING_ENABLED')
    if polling_enabled and not token:
        raise SystemExit("Set BOT_TOKEN in .env before starting the bot.")
    if polling_enabled and (parsed_url.scheme != "https" or not parsed_url.netloc or parsed_url.username or parsed_url.password):
        raise SystemExit("Set MINI_APP_URL to your public HTTPS Mini App URL.")
    db_path = Path(os.environ.get("QUIZ_DB_PATH", "data/quiz.sqlite3"))
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    server_options = {
        'bot_token': token or '0:local-preview-only',
        'database_path': db_path,
        'static_dir': ROOT / 'dist',
        'max_age': int(os.environ.get('INIT_DATA_MAX_AGE', '3600')),
        'host': os.environ.get('HTTP_HOST', '127.0.0.1'),
        'port': int(os.environ.get('HTTP_PORT', '8080')),
    }
    if not polling_enabled:
        logging.info('BOT_POLLING_ENABLED=false: serving local UI preview without Telegram polling')
        async with quiz_server(**server_options):
            await asyncio.Event().wait()
        return

    router = Router()
    quiz = QuizDatabase(db_path)
    try:
        admin_ids = parse_admin_ids(os.environ.get('ADMIN_IDS', ''))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    server_options['admin_ids'] = admin_ids

    @router.message(CommandStart(), F.chat.type == "private")
    async def start(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer(
            "Привет! На связи организаторы Школы Актива 2026.\n\n"
            "Проходи тест и узнай, как хорошо ты знаком с проектом.\n\n"
            "Сначала заполни данные для розыгрыша (ФИО, курс, факультет, студбилет, телефон), "
            "потом 10 вопросов • в конце увидишь количество правильных ответов.\n"
            "Попытка одна! Скрин результата отправь в комментарии к конкурсному посту.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="ПРОЙТИ ТЕСТ ↗", web_app=WebAppInfo(url=mini_app_url))
            ]]),
        )

    @router.message(Command('stop'), F.chat.type == 'private')
    async def unsubscribe(message: Message) -> None:
        await quiz.set_subscribed(message.from_user.id, False)
        await message.answer('Рассылка отключена. /subscribe — включить снова.')

    @router.message(Command('subscribe'), F.chat.type == 'private')
    async def subscribe(message: Message) -> None:
        await quiz.set_subscribed(message.from_user.id, True)
        await message.answer('Рассылка включена. Если ты завершил тест, сообщим здесь о новостях ША.')

    dispatcher = Dispatcher()
    broadcasts = BroadcastStore(quiz)
    runner = BroadcastRunner(quiz, broadcasts)
    # User commands stay available even while an admin is composing a message.
    dispatcher.include_router(router)
    dispatcher.include_router(create_admin_router(quiz, admin_ids, runner))
    async with Bot(token=token) as bot:
        async with quiz_server(**server_options):
            await broadcasts.interrupt_running()
            try:
                await dispatcher.start_polling(bot, close_bot_session=False)
            finally:
                await runner.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Avoid HTTP request logging: initData and tokens should never reach logs.
    asyncio.run(main())
