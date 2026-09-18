import asyncio

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.types import MessageEntity

from database.broadcasts import BroadcastStore
from database.quiz import QuizDatabase


async def send_broadcast(bot: Bot, quiz: QuizDatabase, store: BroadcastStore,
                         broadcast_id: str, text: str, entities: list[dict], *, delay: float = .1) -> None:
    parsed_entities = [MessageEntity.model_validate(entity) for entity in entities]
    for user_id in await store.pending(broadcast_id):
        if not await store.claim_recipient(broadcast_id, user_id):
            break
        outcome = 'failed'
        for attempt in range(3):
            if not await store.is_running(broadcast_id) or not await quiz.is_subscribed(user_id):
                outcome = 'skipped'
                break
            try:
                await bot.send_message(user_id, text, entities=parsed_entities, parse_mode=None)
                outcome = 'sent'
                break
            except TelegramRetryAfter as exc:
                if attempt < 2:
                    await asyncio.sleep(exc.retry_after + .1)
                # Only explicit rate-limit failures are safe to retry.
            except TelegramForbiddenError:
                outcome = 'unavailable'
                break
            except TelegramNetworkError:
                outcome = 'unknown'
                break
            except TelegramAPIError:
                outcome = 'failed'
                break
        await store.recipient_status(broadcast_id, user_id, outcome)
        await asyncio.sleep(delay)
    await store.finish(broadcast_id)
