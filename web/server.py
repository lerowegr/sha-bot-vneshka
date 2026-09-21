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
               static_dir: str | Path | None = None, max_age: int = 3600,
               admin_ids: frozenset[int] = frozenset()) -> web.Application:
    if not bot_token or max_age <= 0:
        raise ValueError("BOT_TOKEN and positive max_age are required")
    db = QuizDatabase(database_path)
    app = web.Application(client_max_size=20 * 1024)

    async def initialize(_: web.Application) -> None:
        await db.initialize()

    async def overview(request: web.Request) -> web.Response:
        """Admin dashboard data. initData comes as a query param; only ADMIN_IDS pass."""
        raw = request.query.get("initData", "")
        try:
            user = validate_init_data(raw, bot_token, max_age=max_age)
        except TelegramAuthError:
            return web.json_response({"error": "invalid_init_data"}, status=401)
        if user.id not in admin_ids:
            return web.json_response({"error": "forbidden"}, status=403)
        try:
            summary = await db.summary()
            matrix = await db.faculty_course_matrix()
            allowlist = await db.get_allowlist()
        except aiosqlite.Error:
            logger.error("Admin overview read failed")
            return web.json_response({"error": "storage_unavailable"}, status=503)
        by_result = summary["by_result"]
        total = summary["total"]
        avg_score = (sum(int(key.split("_")[1]) * count for key, count in by_result.items()) / total) if total else 0
        return web.json_response({
            "ok": True, "total": total, "avg_score": round(avg_score, 2),
            "by_result": {key.split("_")[1]: count for key, count in by_result.items()},
            "by_course": summary["by_course"], "by_faculty": summary["by_faculty"],
            "matrix": matrix, "questions": summary["questions"],
            "avg_total_ms": summary["avg_total_ms"], "timed_count": summary["timed_count"],
            "eligible": summary["eligible"], "dup_phones": summary["dup_phones"],
            "dup_student_ids": summary["dup_student_ids"],
            "allowlist": allowlist,
        }, headers={"Cache-Control": "no-store"})

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

    async def status(request: web.Request) -> web.Response:
        """Has this user already completed? Used to lock the UI against retakes."""
        raw = request.query.get("initData", "")
        try:
            user = validate_init_data(raw, bot_token, max_age=max_age)
        except TelegramAuthError:
            return web.json_response({"error": "invalid_init_data"}, status=401)
        try:
            participants = await db.participants()
        except aiosqlite.Error:
            logger.error("Quiz status read failed")
            return web.json_response({"error": "storage_unavailable"}, status=503)
        row = next((item for item in participants if item["telegram_user_id"] == user.id), None)
        if row is None:
            return web.json_response({"ok": True, "completed": False, "is_admin": user.id in admin_ids},
                                     headers={"Cache-Control": "no-store"})
        score = row["result"].split("_")[1] if isinstance(row.get("result"), str) else None
        return web.json_response({"ok": True, "completed": True, "score": score,
                                  "result": row.get("result"), "is_admin": user.id in admin_ids},
                                 headers={"Cache-Control": "no-store"})

    async def raffle(request: web.Request) -> web.Response:
        """Draw `count` random winners. Admin-only, nothing is stored."""
        if request.content_type != "application/json":
            return web.json_response({"error": "json_required"}, status=415)
        try:
            payload = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return web.json_response({"error": "invalid_json"}, status=400)
        allowed_keys = {"initData", "count", "only_allowlisted"}
        if (not isinstance(payload, dict) or set(payload) - allowed_keys
                or "initData" not in payload or "count" not in payload):
            return web.json_response({"error": "invalid_payload"}, status=400)
        only_allowlisted = payload.get("only_allowlisted", False)
        if not isinstance(only_allowlisted, bool):
            return web.json_response({"error": "invalid_payload"}, status=400)
        try:
            user = validate_init_data(payload["initData"], bot_token, max_age=max_age)
        except TelegramAuthError:
            return web.json_response({"error": "invalid_init_data"}, status=401)
        if user.id not in admin_ids:
            return web.json_response({"error": "forbidden"}, status=403)
        try:
            winners = await db.draw_winners(user.id, payload["count"], only_allowlisted)
        except ValueError as exc:
            code = "allowlist_empty" if "allowlist" in str(exc) else "invalid_count"
            return web.json_response({"error": code}, status=400)
        except aiosqlite.Error:
            logger.error("Raffle draw failed")
            return web.json_response({"error": "storage_unavailable"}, status=503)
        return web.json_response({"ok": True, "winners": winners,
                                  "filtered": only_allowlisted},
                                 headers={"Cache-Control": "no-store"})

    async def allowlist(request: web.Request) -> web.Response:
        """Replace the commenter allowlist with pasted text. Admin-only."""
        if request.content_type != "application/json":
            return web.json_response({"error": "json_required"}, status=415)
        try:
            payload = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return web.json_response({"error": "invalid_json"}, status=400)
        if not isinstance(payload, dict) or set(payload) != {"initData", "entries"}:
            return web.json_response({"error": "invalid_payload"}, status=400)
        if not isinstance(payload["entries"], str) or len(payload["entries"]) > 20000:
            return web.json_response({"error": "invalid_payload"}, status=400)
        try:
            user = validate_init_data(payload["initData"], bot_token, max_age=max_age)
        except TelegramAuthError:
            return web.json_response({"error": "invalid_init_data"}, status=401)
        if user.id not in admin_ids:
            return web.json_response({"error": "forbidden"}, status=403)
        try:
            added, rejected = await db.set_allowlist(user.id, payload["entries"])
            current = await db.get_allowlist()
            eligible = await db.eligible_participants(True) if current else []
        except aiosqlite.Error:
            logger.error("Allowlist save failed")
            return web.json_response({"error": "storage_unavailable"}, status=503)
        return web.json_response({"ok": True, "added": added, "rejected": rejected,
                                  "total": len(current), "eligible": len(eligible)},
                                 headers={"Cache-Control": "no-store"})

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"status": "ok"}, headers={"Cache-Control": "no-store"})

    app.on_startup.append(initialize)
    app.router.add_get("/healthz", health)
    app.router.add_get("/api/admin/overview", overview)
    app.router.add_post("/api/admin/raffle", raffle)
    app.router.add_post("/api/admin/allowlist", allowlist)
    app.router.add_get("/api/quiz/status", status)
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
