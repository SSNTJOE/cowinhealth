"""Daily step activity synced across web + Android. Teaching demo only."""

from __future__ import annotations

from datetime import date, datetime

from .db import connect
from .user_meals import _parse_day

# Teaching approximation for an average adult walking step (~0.04–0.05 kcal/step).
# Prefer 0.04 → ≈ 25 steps per kcal. UI shows the formula so students can recalculate.
KCAL_PER_STEP = 0.04
STEPS_MIN = 3000
STEPS_MAX = 15000
KCAL_KEY = "每日熱量(大卡)"

ALLOWED_SOURCES = frozenset(
    {
        "android_health_connect",
        "android_sensor",
        "manual",
        "web_manual",
    }
)


def clamp_steps(value: int) -> int:
    return max(STEPS_MIN, min(STEPS_MAX, int(value)))


def estimate_burned_kcal(steps: int | float | None) -> float:
    try:
        n = float(steps or 0)
    except (TypeError, ValueError):
        n = 0.0
    if n <= 0:
        return 0.0
    return round(n * KCAL_PER_STEP, 1)


def compute_recommended_steps(meal_kcal: float | None) -> dict:
    """Recommend walking steps to roughly offset that day's meal calories.

    recommended_steps = clamp(round(meal_kcal / KCAL_PER_STEP), STEPS_MIN, STEPS_MAX)
    when meal_kcal > 0; otherwise 0.
    """
    try:
        intake = float(meal_kcal or 0.0)
    except (TypeError, ValueError):
        intake = 0.0
    if intake <= 0:
        recommended = 0
    else:
        recommended = clamp_steps(int(round(intake / KCAL_PER_STEP)))
    return {
        "calories_intake": round(intake, 1),
        "kcal_per_step": KCAL_PER_STEP,
        "steps_min": STEPS_MIN,
        "steps_max": STEPS_MAX,
        "recommended_steps": recommended,
        "recommended_burned_kcal": estimate_burned_kcal(recommended),
        "formula": (
            f"recommended_steps = clamp(round(meal_kcal / {KCAL_PER_STEP}), "
            f"{STEPS_MIN}, {STEPS_MAX})  # teaching demo ≈ 0.04 kcal/step"
        ),
        "disclaimer": "教學示範，非醫療／健身處方。",
    }


# Back-compat alias used by older call sites.
def compute_steps_from_calories(
    calories_intake: float | None,
    calories_target: float | None = None,
) -> dict:
    del calories_target
    return compute_recommended_steps(calories_intake)


def get_activity(user_id: str, day: str | date | None = None) -> dict | None:
    activity_date = _parse_day(day)
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT actual_steps, burned_kcal, source, updated_at
                FROM user_daily_activity
                WHERE user_id = %s AND activity_date = %s
                """,
                (user_id, activity_date),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    steps = int(row["actual_steps"] or 0)
    burned_raw = row.get("burned_kcal")
    if burned_raw is None:
        burned = estimate_burned_kcal(steps)
        burned_estimated = True
    else:
        try:
            burned = round(float(burned_raw), 1)
        except (TypeError, ValueError):
            burned = estimate_burned_kcal(steps)
            burned_estimated = True
        else:
            burned_estimated = False
    updated = row.get("updated_at")
    return {
        "date": activity_date.strftime("%Y-%m-%d"),
        "steps": steps,
        "actual_steps": steps,
        "burned_kcal": burned,
        "burned_estimated": burned_estimated,
        "source": row.get("source") or "manual",
        "updated_at": updated.isoformat(sep=" ", timespec="seconds")
        if hasattr(updated, "isoformat")
        else str(updated or ""),
    }


def get_actual_steps(user_id: str, day: str | date | None = None) -> dict | None:
    """Back-compat wrapper returning the activity row (or None)."""
    return get_activity(user_id, day)


def upsert_activity(
    user_id: str,
    *,
    activity_date: str | date | None,
    steps: int | float | str,
    burned_kcal: float | int | str | None = None,
    source: str | None = "manual",
) -> dict:
    day = _parse_day(activity_date)
    try:
        step_n = int(round(float(steps)))
    except (TypeError, ValueError) as exc:
        raise ValueError("步數不正確") from exc
    if step_n < 0 or step_n > 500_000:
        raise ValueError("步數需介於 0 與 500000 之間")

    burned_value = None
    if burned_kcal is not None and str(burned_kcal).strip() != "":
        try:
            burned_value = round(float(burned_kcal), 1)
        except (TypeError, ValueError) as exc:
            raise ValueError("消耗熱量不正確") from exc
        if burned_value < 0 or burned_value > 50_000:
            raise ValueError("消耗熱量需介於 0 與 50000 之間")
    else:
        burned_value = estimate_burned_kcal(step_n)

    src = str(source or "manual").strip().lower() or "manual"
    if src not in ALLOWED_SOURCES:
        raise ValueError(
            "source 請用 android_health_connect / android_sensor / manual / web_manual"
        )

    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_daily_activity
                  (user_id, activity_date, actual_steps, burned_kcal, source)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  actual_steps = VALUES(actual_steps),
                  burned_kcal = VALUES(burned_kcal),
                  source = VALUES(source),
                  updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, day, step_n, burned_value, src),
            )
    finally:
        conn.close()

    saved = get_activity(user_id, day)
    if saved:
        return saved
    return {
        "date": day.strftime("%Y-%m-%d"),
        "steps": step_n,
        "actual_steps": step_n,
        "burned_kcal": burned_value,
        "burned_estimated": burned_kcal is None or str(burned_kcal).strip() == "",
        "source": src,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def upsert_actual_steps(
    user_id: str,
    *,
    activity_date: str | date | None,
    actual_steps: int | float | str,
    source: str | None = "manual",
    burned_kcal: float | int | str | None = None,
) -> dict:
    return upsert_activity(
        user_id,
        activity_date=activity_date,
        steps=actual_steps,
        burned_kcal=burned_kcal,
        source=source,
    )


def today_payload(user_id: str, user: dict, day: str | date | None = None) -> dict:
    """GET /api/activity/today helper: meals + recommendation + synced activity."""
    from . import user_meals

    summary = attach_activity_to_day(user_meals.day_summary(user_id, user, day), user_id)
    activity = summary.get("activity")
    return {
        "date": summary.get("date"),
        "meal_kcal": summary.get("calories_intake"),
        "recommended_steps": summary.get("recommended_steps"),
        "recommended_burned_kcal": summary.get("recommended_burned_kcal"),
        "kcal_per_step": summary.get("kcal_per_step"),
        "steps_min": summary.get("steps_min"),
        "steps_max": summary.get("steps_max"),
        "formula": summary.get("formula"),
        "disclaimer": summary.get("disclaimer"),
        "activity": activity,
        "day": summary,
    }


def attach_activity_to_day(summary: dict, user_id: str) -> dict:
    """Mutate/extend a meals day_summary with steps recommendation + synced actual."""
    totals = summary.get("totals") or {}
    targets = summary.get("targets") or {}
    computed = compute_recommended_steps(totals.get(KCAL_KEY))
    try:
        target_kcal = float(targets.get(KCAL_KEY) or 0.0) or None
    except (TypeError, ValueError):
        target_kcal = None
    intake = float(computed["calories_intake"] or 0.0)
    surplus = None
    if target_kcal is not None:
        surplus = round(intake - target_kcal, 1)
    activity = get_activity(user_id, summary.get("date"))
    actual = int(activity["actual_steps"]) if activity else None
    burned = float(activity["burned_kcal"]) if activity else None
    recommended = int(computed["recommended_steps"])
    gap = None if actual is None else int(actual) - recommended
    burned_gap = None
    if burned is not None:
        burned_gap = round(burned - intake, 1)
    summary.update(computed)
    summary["calories_target"] = round(target_kcal, 1) if target_kcal is not None else None
    summary["calories_surplus"] = surplus
    summary["actual_steps"] = actual
    summary["burned_kcal"] = burned
    summary["steps_source"] = activity.get("source") if activity else None
    summary["steps_updated_at"] = activity.get("updated_at") if activity else None
    summary["steps_gap"] = gap
    summary["burned_gap_vs_intake"] = burned_gap
    summary["activity"] = activity
    return summary
