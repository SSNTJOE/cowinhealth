"""Auth hardening: bcrypt, local captcha, honeypot, SQL identifier allow-lists."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import string
import time
from typing import Iterable

import bcrypt
from captcha.image import ImageCaptcha
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner

from .config import SECRET_KEY

CAPTCHA_TTL_SECONDS = 300
CAPTCHA_LEN = 4
HONEYPOT_FIELD = "website_url"

_captcha_signer = TimestampSigner(SECRET_KEY + "|captcha")
_image_captcha = ImageCaptcha(width=160, height=56, fonts=None)

# Schema DDL / COUNT(*) may only target these tables (never user input).
ALLOWED_TABLES = frozenset(
    {
        "users",
        "user_meals",
        "user_daily_activity",
        "health_records",
        "catalog_recipes",
        "catalog_foods",
        "catalog_daily_nutrient",
        "catalog_deviations",
        "catalog_health_labels",
        "recipe_translations",
        "color_calib_samples",
        "color_calib_state",
        "affiliate_links",
    }
)

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def assert_safe_identifier(name: str, *, kind: str = "identifier") -> str:
    text = str(name or "").strip()
    if not _IDENT_RE.fullmatch(text):
        raise ValueError(f"不安全的 {kind}：{name!r}")
    return text


def assert_allowed_table(name: str) -> str:
    table = assert_safe_identifier(name, kind="table")
    if table not in ALLOWED_TABLES:
        raise ValueError(f"不允許的資料表：{table}")
    return table


def assert_allowed_columns(names: Iterable[str], allowed: Iterable[str]) -> list[str]:
    allow = frozenset(allowed)
    out: list[str] = []
    for name in names:
        col = assert_safe_identifier(name, kind="column")
        if col not in allow:
            raise ValueError(f"不允許的欄位：{col}")
        out.append(col)
    return out


def hash_password(password: str) -> str:
    """bcrypt salted hash; stored string is utf-8 bcrypt hash."""
    raw = (password or "").encode("utf-8")
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=12)).decode("utf-8")


def _verify_legacy_pbkdf2(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except ValueError:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return hmac.compare_digest(actual, expected)


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    text = str(stored)
    raw = (password or "").encode("utf-8")
    if text.startswith("$2a$") or text.startswith("$2b$") or text.startswith("$2y$"):
        try:
            return bcrypt.checkpw(raw, text.encode("utf-8"))
        except ValueError:
            return False
    # Migrate old pbkdf2 hashes transparently on next successful login.
    return _verify_legacy_pbkdf2(password, text)


def needs_rehash(stored: str | None) -> bool:
    if not stored:
        return True
    text = str(stored)
    return not (text.startswith("$2a$") or text.startswith("$2b$") or text.startswith("$2y$"))


def honeypot_triggered(value: str | None) -> bool:
    return bool((value or "").strip())


def _random_captcha_text(length: int = CAPTCHA_LEN) -> str:
    alphabet = string.ascii_uppercase + string.digits
    # Drop ambiguous glyphs for teaching UX.
    alphabet = alphabet.replace("O", "").replace("0", "").replace("I", "").replace("1", "")
    return "".join(secrets.choice(alphabet) for _ in range(length))


def issue_captcha() -> dict[str, str]:
    answer = _random_captcha_text()
    expires = int(time.time()) + CAPTCHA_TTL_SECONDS
    token = _captcha_signer.sign(f"{answer.lower()}:{expires}".encode("utf-8")).decode("utf-8")
    png = _image_captcha.generate(answer).read()
    return {
        "captcha_token": token,
        "image_base64": base64.b64encode(png).decode("ascii"),
        "expires_in": str(CAPTCHA_TTL_SECONDS),
        "mime": "image/png",
    }


def captcha_png_response(token: str, image_b64: str) -> bytes:
    del token
    return base64.b64decode(image_b64)


def verify_captcha(token: str | None, answer: str | None) -> bool:
    if not token or answer is None:
        return False
    try:
        raw = _captcha_signer.unsign(token.encode("utf-8"), max_age=CAPTCHA_TTL_SECONDS + 30)
        payload = raw.decode("utf-8")
        expected, expires_s = payload.rsplit(":", 1)
        if int(expires_s) < int(time.time()):
            return False
        return hmac.compare_digest(expected, str(answer).strip().lower())
    except (BadSignature, SignatureExpired, ValueError, UnicodeError):
        return False


def reject_bot_or_captcha(
    *,
    website_url: str | None,
    captcha_token: str | None,
    captcha_answer: str | None,
) -> None:
    from fastapi import HTTPException

    if honeypot_triggered(website_url):
        # Generic message — do not confirm honeypot to bots.
        raise HTTPException(status_code=400, detail="請求被拒絕")
    if not verify_captcha(captcha_token, captcha_answer):
        raise HTTPException(status_code=400, detail="驗證碼錯誤或已過期，請重新取得")
