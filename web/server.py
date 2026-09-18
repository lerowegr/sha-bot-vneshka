"""Small same-origin API and Vite static server, running in the bot process."""
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
from aiohttp import web

from database.quiz import (
    AlreadyCompleted, QuizDatabase, score_answers,
    validate_answers, validate_profile, validate_times,
)
from web.telegram_auth import TelegramAuthError, validate_init_data

logger = logging.getLogger(__name__)


def create_app(*, bot_token: str, database_path: str | Path,
               static_dir: str | Path | None = None, max_age: int = 3600) -> web.Application:
    if not bot_token or max_age <= 0:
        raise ValueError("BOT_TOKEN and positive max_age are required")
    db = QuizDatabase(database_path)
    app = web.Application(client_max_size=20 * 1024)

    async def initialize(_: web.Application) -> None:
        await db.initialize()

    async def complete(request: web.Request) -> web.Response:
        if request.content_type != "application/json":
            return web.json_response({"error": "json_required"}, status=415)
        try:
            payload = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return web.json_response({"error": "invalid_json"}, status=400)
        if not isinstance(payload, dict) or set(payload) != {"initData", "answers", "times", "profile"}:
            return web.json_response({"error": "invalid_payload"}, status=400)
        try:
            answers = validate_answers(payload["answers"])
            times = validate_times(payload["times"])
            validate_profile(payload["profile"])
        except ValueError:
            return web.json_response({"error": "invalid_payload"}, status=400)
        result_id, score, _ = score_answers(answers)
        try:
            user = validate_init_data(payload["initData"], bot_token, max_age=max_age)
        except TelegramAuthError:
            return web.json_response({"error": "invalid_init_data"}, status=401)
        try:
            stored_result, _ = await db.complete(user.id, user.username, answers, times, payload["profile"])
        except AlreadyCompleted:
            return web.json_response({"error": "already_completed"}, status=409)
        except aiosqlite.Error:
            logger.error("Quiz database write failed")
            return web.json_response({"error": "storage_unavailable"}, status=503)
        # stored_result equals result_id for new rows; legacy rows keep their first result.
        return web.json_response({"ok": True, "score": score, "result": stored_result},
                                 headers={"Cache-Control": "no-store"})

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"status": "ok"}, headers={"Cache-Control": "no-store"})

    app.on_startup.append(initialize)
    app.router.add_get("/healthz", health)
    app.router.add_post("/api/quiz/complete", complete)

    if static_dir is not None:
        root = Path(static_dir).resolve()

        async def serve_file(request: web.Request) -> web.StreamResponse:
            relative = request.match_info.get("path", "") or "index.html"
            if relative.startswith("api/") or any(part.startswith(".") for part in Path(relative).parts):
                raise web.HTTPNotFound()
            candidate = (root / relative).resolve()
            if not candidate.is_relative_to(root) or not candidate.is_file():
                raise web.HTTPNotFound()
            response = web.FileResponse(candidate)
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable" if relative.startswith("assets/") else "no-cache"
            return response

        app.router.add_get("/{path:.*}", serve_file)
    return app


@asynccontextmanager
async def quiz_server(*, host: str = "127.0.0.1", port: int = 8080, **kwargs):
    runner = web.AppRunner(create_app(**kwargs), access_log=None)
    try:
        await runner.setup()
        await web.TCPSite(runner, host, port).start()
        yield
    finally:
        await runner.cleanup()
