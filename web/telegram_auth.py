"""Telegram Mini App HMAC verification, independent of HTTP and storage."""
import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl


class TelegramAuthError(ValueError):
    pass


@dataclass(frozen=True)
class TelegramUser:
    id: int
    username: str | None


def validate_init_data(
    init_data: str, bot_token: str, *, max_age: int = 3600, now: float | None = None
) -> TelegramUser:
    if not bot_token or max_age <= 0:
        raise ValueError("Invalid Telegram authentication configuration")
    if not isinstance(init_data, str) or not init_data or len(init_data) > 16384:
        raise TelegramAuthError("Invalid initData")
    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True,
                          encoding="utf-8", errors="strict", max_num_fields=64)
    except (ValueError, UnicodeError) as exc:
        raise TelegramAuthError("Malformed initData") from exc
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise TelegramAuthError("Duplicate initData fields")
    supplied_hash = fields.pop("hash", "")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", supplied_hash):
        raise TelegramAuthError("Missing or invalid hash")
    # HMAC includes every field except hash (including signature when present).
    check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, supplied_hash.lower()):
        raise TelegramAuthError("Invalid signature")
    try:
        auth_date = int(fields["auth_date"])
    except (KeyError, ValueError) as exc:
        raise TelegramAuthError("Invalid auth_date") from exc
    timestamp = time.time() if now is None else now
    if auth_date <= 0 or timestamp - auth_date > max_age or auth_date > timestamp + 30:
        raise TelegramAuthError("Expired or future initData")
    try:
        user = json.loads(fields["user"])
    except (KeyError, ValueError) as exc:
        raise TelegramAuthError("Missing or malformed user") from exc
    if not isinstance(user, dict) or type(user.get("id")) is not int or not 0 < user["id"] < 2**52:
        raise TelegramAuthError("Invalid Telegram user id")
    username = user.get("username")
    if username is not None and (not isinstance(username, str) or len(username) > 64):
        raise TelegramAuthError("Invalid username")
    return TelegramUser(id=user["id"], username=username or None)
