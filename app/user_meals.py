"""Logged meals + daily nutrient totals vs HPA targets. Teaching demo only."""

from __future__ import annotations

import json
from calendar import monthrange
from datetime import date, datetime

from .db import connect
from .nutrient_targets import (
    NUTRIENT_KEYS,
    RECIPE_NUTRIENT_HEADERS,
    RECIPE_TO_TARGET,
    chart_labels,
    empty_totals,
    lookup_targets,
    progress_map,
    sum_nutrient_maps,
    surplus_map,
)
from .recipes import recipe_by_id, recipe_nutrient_map


MEAL_SLOTS = ("早餐", "午餐", "晚餐", "點心")


def _parse_day(value: str | date | None) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return date.today()
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("日期格式請用 YYYY-MM-DD") from exc


def _normalize_slot(slot: str | None) -> str:
    raw = str(slot or "").strip()
    if raw in MEAL_SLOTS:
        return raw
    aliases = {
        "breakfast": "早餐",
        "lunch": "午餐",
        "dinner": "晚餐",
        "snack": "點心",
        "morning": "早餐",
        "noon": "午餐",
        "night": "晚餐",
    }
    return aliases.get(raw.lower(), "午餐")


def _parse_servings(value) -> float:
    try:
        servings = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("份量不正確") from exc
    if servings <= 0 or servings > 20:
        raise ValueError("份量需介於 0 與 20 之間")
    return round(servings, 2)


def _scale_nutrients(base: dict[str, float], servings: float) -> dict[str, float]:
    return {key: round(float(base.get(key) or 0.0) * servings, 6) for key in NUTRIENT_KEYS}


def _loads_nutrients(raw) -> dict[str, float]:
    if isinstance(raw, dict):
        data = raw
    else:
        try:
            data = json.loads(raw or "{}")
        except (TypeError, json.JSONDecodeError):
            data = {}
    out = empty_totals()
    for key in NUTRIENT_KEYS:
        try:
            out[key] = float(data.get(key) or 0.0)
        except (TypeError, ValueError):
            out[key] = 0.0
    return out


def _serialize_meal(row: dict) -> dict:
    return {
        "meal_id": int(row["meal_id"]),
        "meal_date": row["meal_date"].strftime("%Y-%m-%d")
        if hasattr(row["meal_date"], "strftime")
        else str(row["meal_date"])[:10],
        "meal_slot": row.get("meal_slot") or "午餐",
        "recipe_id": int(row["recipe_id"]) if row.get("recipe_id") is not None else None,
        "recipe_name": row.get("recipe_name") or "",
        "country": row.get("country") or "",
        "servings": float(row["servings"]) if row.get("servings") is not None else 1.0,
        "nutrients": _loads_nutrients(row.get("nutrients_json")),
        "created_at": row["created_at"].isoformat(sep=" ", timespec="seconds")
        if hasattr(row.get("created_at"), "isoformat")
        else str(row.get("created_at") or ""),
    }


def list_meals(user_id: str, day: str | date | None = None) -> list[dict]:
    meal_day = _parse_day(day)
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT meal_id, meal_date, meal_slot, recipe_id, recipe_name, country,
                       servings, nutrients_json, created_at
                FROM user_meals
                WHERE user_id = %s AND meal_date = %s
                ORDER BY FIELD(meal_slot, '早餐', '午餐', '晚餐', '點心'), meal_id
                """,
                (user_id, meal_day),
            )
            rows = cur.fetchall() or []
    finally:
        conn.close()
    return [_serialize_meal(row) for row in rows]


def add_meal(
    user_id: str,
    *,
    recipe_id: int | str,
    meal_date: str | date | None = None,
    meal_slot: str | None = None,
    servings: float | str = 1,
    lang: str = "zh",
) -> dict:
    day = _parse_day(meal_date)
    slot = _normalize_slot(meal_slot)
    amount = _parse_servings(servings)
    row = recipe_by_id(recipe_id)
    if not row:
        raise ValueError("找不到食譜")
    base = recipe_nutrient_map(row)
    nutrients = _scale_nutrients(base, amount)
    from .recipes import localized_name

    name = localized_name(row, lang)
    country = row.get("country") or ""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_meals
                  (user_id, meal_date, meal_slot, recipe_id, recipe_name, country,
                   servings, nutrients_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    day,
                    slot,
                    int(row["id"]),
                    name,
                    country,
                    amount,
                    json.dumps(nutrients, ensure_ascii=False),
                ),
            )
            meal_id = int(cur.lastrowid)
            cur.execute(
                """
                SELECT meal_id, meal_date, meal_slot, recipe_id, recipe_name, country,
                       servings, nutrients_json, created_at
                FROM user_meals WHERE meal_id = %s
                """,
                (meal_id,),
            )
            saved = cur.fetchone()
    finally:
        conn.close()
    return _serialize_meal(saved)


def delete_meal(user_id: str, meal_id: int) -> bool:
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM user_meals WHERE meal_id = %s AND user_id = %s",
                (int(meal_id), user_id),
            )
            return cur.rowcount > 0
    finally:
        conn.close()


def day_summary(user_id: str, user: dict, day: str | date | None = None) -> dict:
    meal_day = _parse_day(day)
    meals = list_meals(user_id, meal_day)
    totals = sum_nutrient_maps([m.get("nutrients") for m in meals])
    age = user.get("age")
    if age is None and user.get("birth_year"):
        age = datetime.now().year - int(user["birth_year"])
    targets_payload = lookup_targets(age, user.get("gender"))
    targets = targets_payload["targets"]
    surplus = surplus_map(totals, targets)
    progress = progress_map(totals, targets)
    return {
        "date": meal_day.strftime("%Y-%m-%d"),
        "meals": meals,
        "meal_count": len(meals),
        "totals": totals,
        "targets": targets,
        "ranges": targets_payload["ranges"],
        "surplus": surplus,
        "progress": progress,
        "age_band": targets_payload["age_band"],
        "gender": targets_payload["gender"],
        "group": targets_payload["group"],
        "nutrient_keys": list(NUTRIENT_KEYS),
        "chart_labels": chart_labels(),
        "recipe_headers": list(RECIPE_NUTRIENT_HEADERS),
        "recipe_to_target": dict(RECIPE_TO_TARGET),
        "disclaimer": targets_payload["disclaimer"],
    }


def month_overview(user_id: str, user: dict, year: int, month: int) -> dict:
    if month < 1 or month > 12:
        raise ValueError("月份不正確")
    last_day = monthrange(year, month)[1]
    start = date(year, month, 1)
    end = date(year, month, last_day)
    age = user.get("age")
    if age is None and user.get("birth_year"):
        age = datetime.now().year - int(user["birth_year"])
    targets_payload = lookup_targets(age, user.get("gender"))
    kcal_key = "每日熱量(大卡)"
    kcal_target = float(targets_payload["targets"].get(kcal_key) or 0.0)

    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT meal_date, nutrients_json
                FROM user_meals
                WHERE user_id = %s AND meal_date BETWEEN %s AND %s
                ORDER BY meal_date, meal_id
                """,
                (user_id, start, end),
            )
            rows = cur.fetchall() or []
    finally:
        conn.close()

    by_day: dict[str, list[dict[str, float]]] = {}
    for row in rows:
        day_key = (
            row["meal_date"].strftime("%Y-%m-%d")
            if hasattr(row["meal_date"], "strftime")
            else str(row["meal_date"])[:10]
        )
        by_day.setdefault(day_key, []).append(_loads_nutrients(row.get("nutrients_json")))

    days = []
    for day_num in range(1, last_day + 1):
        day_key = f"{year:04d}-{month:02d}-{day_num:02d}"
        parts = by_day.get(day_key) or []
        totals = sum_nutrient_maps(parts)
        kcal = float(totals.get(kcal_key) or 0.0)
        pct = round(100.0 * kcal / kcal_target, 1) if kcal_target > 0 else None
        days.append(
            {
                "date": day_key,
                "meal_count": len(parts),
                "kcal": kcal,
                "kcal_pct": pct,
                "has_meals": bool(parts),
            }
        )
    return {
        "year": year,
        "month": month,
        "days": days,
        "kcal_target": kcal_target,
        "age_band": targets_payload["age_band"],
        "gender": targets_payload["gender"],
        "disclaimer": targets_payload["disclaimer"],
    }
