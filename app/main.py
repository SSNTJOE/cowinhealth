from __future__ import annotations

import base64
import hashlib
import logging
import hmac
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
from pymysql.err import IntegrityError

from .advice import build_advice
from .analysis import analyze_session
from .config import COOKIE_NAME, ROOT, SECRET_KEY
from .db import connect, init_schema
from .deviation import record_deviation
from .health_flags import (
    CONDITION_SET,
    CONDITION_OPTIONS,
    allergy_option_set,
    allergy_options,
    dumps_labels,
    history_summary,
    parse_label_list,
    user_allergies,
    user_conditions,
)
from .recipes import TEACHING_DISCLAIMER, filter_recipes, split_csv, usable_countries
from .syndrome import ORGAN_KEYS, ORGAN_META, PATTERN_KEYS, omit_uterus_judgment, overlay_from_pattern_label
from .trend import build_trend, iso_time

logger = logging.getLogger(__name__)
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
    "moisture.png": "mositure.png",
    "mositure.png": "mositure.png",
}
signer = TimestampSigner(SECRET_KEY)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

app = FastAPI(title="Health-ing")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
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
    return hmac.compare_digest(actual, expected)


GENDER_VALUES = {"female", "male", "other"}
GENDER_ALIASES = {
    "female": "female",
    "f": "female",
    "girl": "female",
    "woman": "female",
    "女": "female",
    "女生": "female",
    "male": "male",
    "m": "male",
    "boy": "male",
    "man": "male",
    "男": "male",
    "男生": "male",
    "other": "other",
    "其他": "other",
}


def allocate_user_id(cur) -> str:
    for _ in range(30):
        user_id = f"user_{random.randint(100000, 999999)}"
        cur.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id,))
        if cur.fetchone() is None:
            return user_id
    raise HTTPException(status_code=500, detail="無法產生匿名 ID")


def parse_nickname(nickname: str) -> str:
    name = (nickname or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="請填寫暱稱")
    if len(name) > 64:
        raise HTTPException(status_code=400, detail="暱稱太長")
    return name


def parse_birth_year(value: int | str) -> int:
    try:
        year = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="出生年不正確") from exc
    this_year = datetime.now().year
    if year < 1900 or year > this_year:
        raise HTTPException(status_code=400, detail="出生年不正確")
    if this_year - year > 120:
        raise HTTPException(status_code=400, detail="出生年不正確")
    return year


def parse_gender(gender: str) -> str:
    raw = (gender or "").strip()
    value = GENDER_ALIASES.get(raw) or GENDER_ALIASES.get(raw.lower())
    if value not in GENDER_VALUES:
        raise HTTPException(status_code=400, detail="請選擇性別")
    return value


def age_from_birth_year(birth_year: int) -> int:
    return datetime.now().year - birth_year


def is_profile_complete(user: dict) -> bool:
    return bool(user.get("nickname") and user.get("birth_year") and user.get("gender"))


def _positive_float(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def compute_bmi(height, weight) -> float | None:
    height_cm = _positive_float(height)
    weight_kg = _positive_float(weight)
    if height_cm is None or weight_kg is None:
        return None
    meters = height_cm / 100.0
    return round(weight_kg / (meters * meters), 1)


def bmi_category_tw(bmi: float | None) -> str | None:
    if bmi is None:
        return None
    if bmi < 18.5:
        return "過輕"
    if bmi < 24:
        return "健康體重"
    if bmi < 27:
        return "過重"
    if bmi < 30:
        return "輕度肥胖"
    if bmi < 35:
        return "中度肥胖"
    return "重度肥胖"


def healthy_weight_range(height) -> str | None:
    height_cm = _positive_float(height)
    if height_cm is None:
        return None
    h2 = (height_cm * height_cm) / 10000.0
    min_kg = round(18.5 * h2, 1)
    exclusive_kg = 24 * h2
    max_kg = round(int(exclusive_kg * 10 + 1e-8) / 10 - 0.1, 1)
    if min_kg <= 0 or max_kg < min_kg:
        return None
    return f"{min_kg:.1f}–{max_kg:.1f} kg"


def serialize_user(user: dict, include_email: bool = False) -> dict:
    height = float(user["height"]) if user.get("height") is not None else None
    weight = float(user["weight"]) if user.get("weight") is not None else None
    bmi = compute_bmi(height, weight)
    public = {
        "user_id": user.get("user_id"),
        "nickname": user.get("nickname"),
        "birth_year": user.get("birth_year"),
        "age": int(user["age"]) if user.get("age") is not None else None,
        "gender": user.get("gender"),
        "height": height,
        "weight": weight,
        "bmi": bmi,
        "bmi_category": bmi_category_tw(bmi),
        "healthy_bmi_range": "18.5–23.9" if _positive_float(height) else None,
        "healthy_weight_range": healthy_weight_range(height),
        "medical_history": user.get("medical_history"),
        "conditions": user_conditions(user),
        "allergies": user_allergies(user),
        "allergy_options": list(allergy_options()),
        "profile_complete": is_profile_complete(user),
    }
    if include_email:
        public["email"] = user.get("email")
    return public


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
                SELECT user_id, email, nickname, birth_year, height, weight, age, gender,
                       medical_history, conditions_json, allergies_json, complexion_lab_json
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


def _stored_organ_score(scores: dict, key: str):
    if isinstance(scores, dict) and key in scores and scores[key] is not None:
        return scores[key]
    if key == "uterus_score":
        return 0
    raise KeyError(key)


def _stored_organ_pattern(patterns: dict, key: str) -> str:
    value = patterns.get(key) if isinstance(patterns, dict) else None
    if value not in (None, ""):
        return value
    if key == "uterus_pattern":
        return "未定"
    raise KeyError(key)


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
        "face_grid_json",
        "face_measurements_json",
        "complexion_label",
        "complexion_hex",
        "complexion_hsv_json",
        "tongue_grid_json",
        "tongue_measurements_json",
        "organ_composite_json",
    ]
    colors = result.get("region_colors") or {}
    complexion = result.get("complexion") or {}
    face_grid = result.get("face_grid")
    measurements = (face_grid or {}).get("measurements")
    tongue_grid = result.get("tongue_grid")
    tongue_measurements = (tongue_grid or {}).get("measurements")
    values = [
        user_id,
        record_date,
        extra.get("symptoms"),
        extra.get("discomfort"),
        colors.get("face_color"),
        colors.get("lip_color"),
        colors.get("tongue_body_color"),
        colors.get("tongue_coat_color"),
        *[_stored_organ_score(result["scores"], key) for key in ORGAN_KEYS],
        *[_stored_organ_pattern(result["patterns"], key) for key in PATTERN_KEYS],
        extra.get("diet_advice"),
        extra.get("diet_url"),
        extra.get("acupoint_url"),
        extra.get("pulse_json"),
        json.dumps(face_grid, ensure_ascii=False) if face_grid else None,
        json.dumps(measurements, ensure_ascii=False) if measurements else None,
        complexion.get("bias") or extra.get("complexion_label"),
        complexion.get("hex"),
        json.dumps(complexion.get("hsv"), ensure_ascii=False) if complexion.get("hsv") else None,
        json.dumps(tongue_grid, ensure_ascii=False) if tongue_grid else None,
        json.dumps(tongue_measurements, ensure_ascii=False) if tongue_measurements else None,
        json.dumps(result.get("organ_health"), ensure_ascii=False) if result.get("organ_health") else None,
    ]
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO health_records ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})",
                values,
            )
            record_id = cur.lastrowid
            lab = complexion.get("lab")
            if lab:
                payload = dict(lab)
                if complexion.get("S") is not None:
                    payload["S"] = complexion.get("S")
                cur.execute(
                    "UPDATE users SET complexion_lab_json = %s WHERE user_id = %s",
                    (json.dumps(payload, ensure_ascii=False), user_id),
                )
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


@app.get("/register")
def register_page():
    return FileResponse(STATIC_DIR / "register.html")


@app.get("/profile")
def profile_page():
    return FileResponse(STATIC_DIR / "profile.html")


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


@app.get("/api/flags")
def health_flag_options():
    options = list(allergy_options())
    return {
        "conditions": list(CONDITION_OPTIONS),
        "allergies": options,
        "allergy_options": options,
    }


def latest_record_judgment(user_id: str) -> tuple[dict[str, int], dict[str, str]]:
    columns = [*ORGAN_KEYS, *PATTERN_KEYS]
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {", ".join(columns)}
                FROM health_records
                WHERE user_id = %s
                ORDER BY record_date DESC
                LIMIT 1
                """,
                (user_id,),
            )
            row = cur.fetchone() or {}
    finally:
        conn.close()
    scores: dict[str, int] = {}
    for key in ORGAN_KEYS:
        raw = row.get(key)
        if raw is None or raw == "":
            continue
        try:
            scores[key] = int(raw)
        except (TypeError, ValueError):
            continue
    patterns = {key: (row.get(key) or "") for key in PATTERN_KEYS}
    return scores, patterns


def _json_object(raw: str | None, label: str) -> dict | None:
    if raw is None or not str(raw).strip():
        return None
    text = str(raw).strip()
    if not text.startswith("{"):
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"{label} JSON 不正確") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail=f"{label} 必須是物件")
    return data


def _is_female(explicit: str | None, profile: dict | None) -> bool:
    if explicit is not None and str(explicit).strip() != "":
        return str(explicit).strip().lower() in {"1", "true", "yes", "female", "f", "女"}
    return (profile or {}).get("gender") == "female"


def _recipe_filter_args(
    request: Request,
    patterns: str | None,
    scores: str | None,
    allergies: str | None,
    conditions: str | None,
    female: str | None,
) -> dict:
    user_id = current_user_id(request)
    profile = fetch_user(user_id) if user_id else None
    allergy_list = split_csv(allergies) if allergies is not None else user_allergies(profile)
    condition_list = split_csv(conditions) if conditions is not None else user_conditions(profile)
    client_scores = _json_object(scores, "scores")
    client_patterns = _json_object(patterns, "patterns")
    if client_scores is not None or client_patterns is not None:
        score_map = client_scores or {}
        pattern_map = {
            str(key): "" if value is None else str(value)
            for key, value in (client_patterns or {}).items()
        }
    elif user_id:
        score_map, pattern_map = latest_record_judgment(user_id)
    else:
        score_map, pattern_map = {}, {}
    return {
        "patterns": pattern_map,
        "scores": score_map,
        "allergies": allergy_list,
        "conditions": condition_list,
        "female": _is_female(female, profile),
    }


@app.get("/api/recipes/countries")
def api_recipe_countries(
    request: Request,
    prefix: str | None = None,
    lang: str = "zh",
    patterns: str | None = None,
    scores: str | None = None,
    allergies: str | None = None,
    conditions: str | None = None,
    female: str | None = None,
    by_body: bool = False,
):
    del lang  # country names stay column 1; lang is accepted so the client can reuse recipe params
    args = _recipe_filter_args(request, patterns, scores, allergies, conditions, female)
    try:
        names = usable_countries(prefix, by_body=by_body, **args)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="找不到 Recipe.xls") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "countries": names,
        "prefix": (prefix or "").strip(),
        "by_body": bool(by_body),
        "disclaimer": TEACHING_DISCLAIMER,
    }


@app.get("/api/recipes")
def api_recipes(
    request: Request,
    country: str,
    lang: str = "zh",
    patterns: str | None = None,
    scores: str | None = None,
    allergies: str | None = None,
    conditions: str | None = None,
    female: str | None = None,
    by_body: bool = False,
):
    args = _recipe_filter_args(request, patterns, scores, allergies, conditions, female)
    allergy_list = args["allergies"]
    condition_list = args["conditions"]
    try:
        payload = filter_recipes(
            country=country,
            lang=lang,
            by_body=by_body,
            **args,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="找不到 Recipe.xls") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    payload["allergies"] = allergy_list
    payload["conditions"] = condition_list
    return payload


@app.post("/api/register")
def register(
    email: str = Form(...),
    password: str = Form(...),
):
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
            user_id = allocate_user_id(cur)
            cur.execute(
                """
                INSERT INTO users (user_id, email, password_hash)
                VALUES (%s, %s, %s)
                """,
                (user_id, email, hash_password(password)),
            )
    except HTTPException:
        raise
    except IntegrityError:
        raise HTTPException(status_code=409, detail="此 E-mail 已註冊")
    finally:
        conn.close()

    token = signer.sign(user_id.encode("utf-8")).decode("utf-8")
    payload = JSONResponse(
        {
            "user_id": user_id,
            "token": token,
            "profile_complete": False,
        }
    )
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
    user = fetch_user(user_id) or {"user_id": user_id}
    payload = JSONResponse(
        {
            "user_id": user_id,
            "token": token,
            "profile_complete": is_profile_complete(user),
        }
    )
    set_session(payload, user_id)
    return payload


@app.post("/api/logout")
def logout():
    payload = JSONResponse({"ok": True})
    payload.delete_cookie(COOKIE_NAME)
    return payload


@app.get("/api/me")
def me(request: Request, include_email: bool = False):
    user_id = current_user_id(request)
    if not user_id:
        return {"logged_in": False}
    user = fetch_user(user_id)
    if not user:
        return {"logged_in": False}
    public = serialize_user(user, include_email=include_email)
    return {
        "logged_in": True,
        "user": public,
        "profile_complete": public["profile_complete"],
    }


@app.post("/api/profile")
def update_profile(
    request: Request,
    nickname: str | None = Form(default=None),
    birth_year: int | None = Form(default=None),
    height: float | None = Form(default=None),
    weight: float | None = Form(default=None),
    gender: str | None = Form(default=None),
    medical_history: str | None = Form(default=None),
    conditions_json: str | None = Form(default=None),
    allergies_json: str | None = Form(default=None),
):
    user_id = require_user(request)
    current = fetch_user(user_id)
    if not current:
        raise HTTPException(status_code=401, detail="請先登入")

    next_nickname = (
        parse_nickname(nickname)
        if nickname is not None and str(nickname).strip()
        else current.get("nickname")
    )
    next_birth = parse_birth_year(birth_year) if birth_year is not None else current.get("birth_year")
    next_gender = parse_gender(gender) if gender else current.get("gender")
    next_age = age_from_birth_year(next_birth) if next_birth else current.get("age")
    next_height = height if height is not None else current.get("height")
    next_weight = weight if weight is not None else current.get("weight")
    if conditions_json is not None:
        next_conditions = parse_label_list(
            conditions_json, CONDITION_SET, CONDITION_OPTIONS, "conditions_json"
        )
    else:
        next_conditions = user_conditions(current)
    if allergies_json is not None:
        next_allergies = parse_label_list(
            allergies_json, allergy_option_set(), allergy_options(), "allergies_json"
        )
    else:
        next_allergies = user_allergies(current)
    if conditions_json is not None or allergies_json is not None:
        next_history = history_summary(next_conditions, next_allergies)
    elif medical_history is not None:
        next_history = medical_history
    else:
        next_history = current.get("medical_history")

    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET nickname = %s, birth_year = %s, height = %s, weight = %s,
                    age = %s, gender = %s, medical_history = %s,
                    conditions_json = %s, allergies_json = %s
                WHERE user_id = %s
                """,
                (
                    next_nickname,
                    next_birth,
                    next_height,
                    next_weight,
                    next_age,
                    next_gender,
                    next_history,
                    dumps_labels(next_conditions),
                    dumps_labels(next_allergies),
                    user_id,
                ),
            )
    finally:
        conn.close()
    user = fetch_user(user_id) or {}
    public = serialize_user(user, include_email=True)
    return {"ok": True, "user": public, "profile_complete": public["profile_complete"]}


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
    include_pulse: str | None = Form(default=None),
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

    profile = fetch_user(user_id) or {}
    personal_lab = None
    raw_lab = profile.get("complexion_lab_json")
    if raw_lab:
        try:
            personal_lab = json.loads(raw_lab) if isinstance(raw_lab, str) else raw_lab
        except json.JSONDecodeError:
            personal_lab = None
    confirm_with_pulse = str(include_pulse or "").strip().lower() in {"1", "true", "yes", "android"}
    result = analyze_session(
        images,
        symptoms or "",
        discomfort or "",
        pulse,
        personal_lab=personal_lab,
        confirm_with_pulse=confirm_with_pulse,
        female=(profile or {}).get("gender") == "female",
    )
    advice = build_advice(
        result["findings"],
        symptoms or "",
        discomfort or "",
        conditions=user_conditions(profile),
        allergies=user_allergies(profile),
    )
    extra = {
        "symptoms": symptoms,
        "discomfort": discomfort,
        "diet_advice": advice["diet_advice"],
        "diet_url": advice["diet_url"],
        "acupoint_url": advice["acupoint_url"],
        "pulse_json": pulse_json,
    }
    insert_record(user_id, result, extra)
    try:
        record_deviation(user_id, profile, result, symptoms or "", discomfort or "")
    except Exception:
        logger.exception("檢測差異沒有寫入 deviation.xls")
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
                       diet_advice, diet_url, acupoint_url,
                       face_grid_json, face_measurements_json,
                       complexion_label, complexion_hex, complexion_hsv_json,
                       tongue_grid_json, tongue_measurements_json, organ_composite_json
                FROM health_records
                WHERE user_id = %s
                ORDER BY record_date DESC
                LIMIT 50
                """,
                (user_id,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    profile = fetch_user(user_id) or {}
    female = profile.get("gender") == "female"
    for row in rows:
        row["record_date"] = iso_time(row.get("record_date"))
        row["overlays"] = {
            key: overlay_from_pattern_label(row.get(pattern_key))
            for key, _name, _score_key, pattern_key in ORGAN_META
        }
        raw_grid = row.get("face_grid_json")
        if raw_grid:
            try:
                row["face_grid"] = json.loads(raw_grid)
            except json.JSONDecodeError:
                row["face_grid"] = None
        else:
            row["face_grid"] = None
        raw_tongue = row.get("tongue_grid_json")
        if raw_tongue:
            try:
                row["tongue_grid"] = json.loads(raw_tongue)
            except json.JSONDecodeError:
                row["tongue_grid"] = None
        else:
            row["tongue_grid"] = None
        raw_health = row.get("organ_composite_json")
        if raw_health:
            try:
                row["organ_health"] = json.loads(raw_health)
            except json.JSONDecodeError:
                row["organ_health"] = None
        else:
            row["organ_health"] = None
        health = row.get("organ_health")
        if isinstance(health, dict) and isinstance(health.get("pattern_scores"), dict):
            row["pattern_scores"] = health["pattern_scores"]
        if not female:
            omit_uterus_judgment(row)
    return {"user_id": user_id, "records": rows, "trend": build_trend(rows, include_uterus=female)}
