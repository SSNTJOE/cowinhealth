from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import re
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner

from .advice import build_advice
from .analysis import analyze_session
from .config import COOKIE_NAME, ROOT, SECRET_KEY
from .db import connect, init_schema
from .syndrome import ORGAN_KEYS, ORGAN_META, PATTERN_KEYS, overlay_from_pattern_label

STATIC_DIR = Path(__file__).resolve().parent / "static"
MEDIA_ALIASES = {
    "boy-body.pgn": "boy-body.png",
    "girl-body.pgn": "girl-body.png",
    "week-hot.png": "weak-hot.png",
    "week-hot.pgn": "weak-hot.png",
    "week-cold.png": "weak-cold.png",
    "week-cold.pgn": "weak-cold.png",
    "strong-hot.pgn": "strong-hot.png",
    "strong-cold.pgn": "strong-cold.png",
    "weak-hot.pgn": "weak-hot.png",
    "weak-cold.pgn": "weak-cold.png",
}
signer = TimestampSigner(SECRET_KEY)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

app = FastAPI(title="Health-ing")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
def startup():
    init_schema()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except ValueError:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return hashlib.compare_digest(actual, expected)


def new_anonymous_id() -> str:
    conn = connect()
    try:
        with conn.cursor() as cur:
            for _ in range(30):
                user_id = f"user_{random.randint(100000, 999999)}"
                cur.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id,))
                if cur.fetchone() is None:
                    return user_id
    finally:
        conn.close()
    raise HTTPException(status_code=500, detail="無法產生匿名 ID")


def set_session(response: Response, user_id: str) -> str:
    token = signer.sign(user_id.encode("utf-8")).decode("utf-8")
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 14,
    )
    return token


def current_user_id(request: Request) -> str | None:
    header = request.headers.get("Authorization") or ""
    token = None
    if header.lower().startswith("bearer "):
        token = header.split(" ", 1)[1].strip()
    if not token:
        token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        return signer.unsign(token, max_age=60 * 60 * 24 * 14).decode("utf-8")
    except (BadSignature, SignatureExpired):
        return None


def require_user(request: Request) -> str:
    user_id = current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="請先登入")
    return user_id


def fetch_user(user_id: str) -> dict | None:
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, email, height, weight, age, gender, medical_history
                FROM users WHERE user_id = %s
                """,
                (user_id,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def decode_image(upload: UploadFile | None, image_base64: str | None) -> bytes | None:
    if upload is not None:
        return None  # caller awaits read
    if not image_base64:
        return None
    payload = image_base64.split(",", 1)[-1]
    try:
        return base64.b64decode(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Base64 圖片無法解析") from exc


def insert_record(user_id: str, result: dict, extra: dict) -> int:
    record_date = datetime.now()
    columns = [
        "user_id",
        "record_date",
        "symptoms",
        "discomfort",
        "face_color",
        "lip_color",
        "tongue_body_color",
        "tongue_coat_color",
        *ORGAN_KEYS,
        *PATTERN_KEYS,
        "diet_advice",
        "diet_url",
        "acupoint_url",
        "pulse_json",
    ]
    colors = result.get("region_colors") or {}
    values = [
        user_id,
        record_date,
        extra.get("symptoms"),
        extra.get("discomfort"),
        colors.get("face_color"),
        colors.get("lip_color"),
        colors.get("tongue_body_color"),
        colors.get("tongue_coat_color"),
        *[result["scores"][key] for key in ORGAN_KEYS],
        *[result["patterns"][key] for key in PATTERN_KEYS],
        extra.get("diet_advice"),
        extra.get("diet_url"),
        extra.get("acupoint_url"),
        extra.get("pulse_json"),
    ]
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO health_records ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})",
                values,
            )
            record_id = cur.lastrowid
    finally:
        conn.close()
    result["record_id"] = record_id
    result["record_date"] = record_date.isoformat(timespec="seconds")
    result["user_id"] = user_id
    result.update({k: extra.get(k) for k in ("symptoms", "discomfort", "diet_advice", "diet_url", "acupoint_url")})
    return record_id


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/media/{name}")
def body_image(name: str):
    wanted = MEDIA_ALIASES.get(name, name)
    for candidate in (ROOT / wanted, STATIC_DIR / wanted, ROOT / name, STATIC_DIR / name):
        if candidate.exists() and candidate.is_file():
            return FileResponse(candidate)
    raise HTTPException(status_code=404, detail="找不到圖檔")


@app.get("/api/health")
def health():
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 AS ok")
            row = cur.fetchone()
        return {"ok": True, "mysql": row["ok"] == 1}
    finally:
        conn.close()


@app.post("/api/register")
def register(email: str = Form(...), password: str = Form(...)):
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="E-mail 格式不正確")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="密碼至少 6 個字元")

    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM users WHERE email = %s", (email,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="此 E-mail 已註冊")
            user_id = new_anonymous_id()
            cur.execute(
                "INSERT INTO users (user_id, email, password_hash) VALUES (%s, %s, %s)",
                (user_id, email, hash_password(password)),
            )
    finally:
        conn.close()

    token = signer.sign(user_id.encode("utf-8")).decode("utf-8")
    payload = JSONResponse({"user_id": user_id, "email": email, "token": token})
    set_session(payload, user_id)
    return payload


@app.post("/api/login")
def login(email: str = Form(...), password: str = Form(...)):
    email = email.strip().lower()
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, password_hash FROM users WHERE email = %s",
                (email,),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if not row or not verify_password(password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="E-mail 或密碼錯誤")

    user_id = row["user_id"]
    token = signer.sign(user_id.encode("utf-8")).decode("utf-8")
    payload = JSONResponse({"user_id": user_id, "email": email, "token": token})
    set_session(payload, user_id)
    return payload


@app.post("/api/logout")
def logout():
    payload = JSONResponse({"ok": True})
    payload.delete_cookie(COOKIE_NAME)
    return payload


@app.get("/api/me")
def me(request: Request):
    user_id = current_user_id(request)
    if not user_id:
        return {"logged_in": False}
    user = fetch_user(user_id)
    if not user:
        return {"logged_in": False}
    public = {k: v for k, v in user.items() if k != "email"}
    return {"logged_in": True, "user": public}


@app.post("/api/profile")
def update_profile(
    request: Request,
    height: float | None = Form(default=None),
    weight: float | None = Form(default=None),
    age: int | None = Form(default=None),
    gender: str | None = Form(default=None),
    medical_history: str | None = Form(default=None),
):
    user_id = require_user(request)
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET height = %s, weight = %s, age = %s, gender = %s, medical_history = %s
                WHERE user_id = %s
                """,
                (height, weight, age, gender or None, medical_history or None, user_id),
            )
    finally:
        conn.close()
    user = fetch_user(user_id) or {}
    public = {k: v for k, v in user.items() if k != "email"}
    return {"ok": True, "user": public}


async def collect_images(
    face: UploadFile | None,
    tongue: UploadFile | None,
    face_base64: str | None,
    tongue_base64: str | None,
    image: UploadFile | None,
    image_base64: str | None,
    shot_type: str | None,
) -> list[tuple[str, bytes]]:
    images: list[tuple[str, bytes]] = []
    if image is not None:
        raw = await image.read()
        if raw:
            images.append((shot_type or "face", raw))
    elif image_base64:
        raw = decode_image(None, image_base64)
        if raw:
            images.append((shot_type or "face", raw))
    if face is not None:
        raw = await face.read()
        if raw:
            images.append(("face", raw))
    elif face_base64:
        raw = decode_image(None, face_base64)
        if raw:
            images.append(("face", raw))
    if tongue is not None:
        raw = await tongue.read()
        if raw:
            images.append(("tongue", raw))
    elif tongue_base64:
        raw = decode_image(None, tongue_base64)
        if raw:
            images.append(("tongue", raw))
    return images


@app.post("/api/analyze")
@app.post("/api/record")
async def analyze(
    request: Request,
    shot_type: str | None = Form(default=None),
    image: UploadFile | None = File(default=None),
    image_base64: str | None = Form(default=None),
    face: UploadFile | None = File(default=None),
    tongue: UploadFile | None = File(default=None),
    face_base64: str | None = Form(default=None),
    tongue_base64: str | None = Form(default=None),
    symptoms: str | None = Form(default=None),
    discomfort: str | None = Form(default=None),
    pulse_json: str | None = Form(default=None),
):
    user_id = require_user(request)
    images = await collect_images(
        face, tongue, face_base64, tongue_base64, image, image_base64, shot_type
    )
    pulse = None
    if pulse_json:
        try:
            pulse = json.loads(pulse_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="pulse_json 不是合法 JSON") from exc

    result = analyze_session(images, symptoms or "", discomfort or "", pulse)
    advice = build_advice(result["findings"], symptoms or "", discomfort or "")
    extra = {
        "symptoms": symptoms,
        "discomfort": discomfort,
        "diet_advice": advice["diet_advice"],
        "diet_url": advice["diet_url"],
        "acupoint_url": advice["acupoint_url"],
        "pulse_json": pulse_json,
    }
    insert_record(user_id, result, extra)
    return result


@app.get("/api/records")
def records(request: Request):
    user_id = require_user(request)
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT record_id, user_id, record_date, symptoms, discomfort,
                       face_color, lip_color, tongue_body_color, tongue_coat_color,
                       {", ".join(ORGAN_KEYS)},
                       {", ".join(PATTERN_KEYS)},
                       diet_advice, diet_url, acupoint_url
                FROM health_records
                WHERE user_id = %s
                ORDER BY record_date DESC
                LIMIT 20
                """,
                (user_id,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    for row in rows:
        row["overlays"] = {
            key: overlay_from_pattern_label(row.get(pattern_key))
            for key, _name, _score_key, pattern_key in ORGAN_META
        }
    return {"user_id": user_id, "records": rows}
