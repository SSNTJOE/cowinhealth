"""Online MySQL color calibration (EWMA / running means).

Persists per-shot Lab/HSV + lighting + disease/allergen context from each
face/tongue/stool/urine classify. Accumulates illuminant/CCT, brightness bias,
and soft threshold adjustments; applies them on the next classify so web and
Android stay consistent. No GPU required.

state_json.ml_hook is reserved for a deeper model later — this module only
keeps the hook shape stable.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

MODALITIES = ("face", "tongue", "stool", "urine")
DEFAULT_CCT_K = 4200.0
TARGET_BRIGHTNESS = 0.42
EMA_ALPHA = 0.12
MAX_CCT_BIAS_K = 600.0
MAX_BRIGHTNESS_BIAS = 0.25
MAX_THRESH_ADJ = 4.0
ML_HOOK_VERSION = 1

CALIB_SCHEMA_SQL = [
    """
    CREATE TABLE IF NOT EXISTS color_calib_samples (
      sample_id BIGINT AUTO_INCREMENT PRIMARY KEY,
      user_id VARCHAR(32) NULL,
      record_id INT NULL,
      device_key VARCHAR(80) NULL,
      modality VARCHAR(16) NOT NULL,
      captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      cct_raw DOUBLE NULL,
      cct_used DOUBLE NULL,
      brightness_raw DOUBLE NULL,
      brightness_gain DOUBLE NULL,
      L DOUBLE NULL,
      a_star DOUBLE NULL,
      b_star DOUBLE NULL,
      h DOUBLE NULL,
      s DOUBLE NULL,
      v DOUBLE NULL,
      class_label VARCHAR(128) NULL,
      delta_e DOUBLE NULL,
      conditions_json TEXT NULL,
      allergies_json TEXT NULL,
      features_json TEXT NULL,
      quiet TINYINT(1) NOT NULL DEFAULT 1,
      INDEX idx_calib_samp_user_mod (user_id, modality, captured_at),
      INDEX idx_calib_samp_mod_time (modality, captured_at),
      INDEX idx_calib_samp_device (device_key, modality)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS color_calib_state (
      state_key VARCHAR(128) PRIMARY KEY,
      scope VARCHAR(32) NOT NULL,
      modality VARCHAR(16) NOT NULL,
      tag VARCHAR(128) NULL,
      n INT NOT NULL DEFAULT 0,
      ewma_cct DOUBLE NULL,
      ewma_brightness DOUBLE NULL,
      ewma_L DOUBLE NULL,
      ewma_a DOUBLE NULL,
      ewma_b DOUBLE NULL,
      cct_bias_k DOUBLE NOT NULL DEFAULT 0,
      brightness_bias DOUBLE NOT NULL DEFAULT 0,
      thresh_delta_e_adj DOUBLE NOT NULL DEFAULT 0,
      thresh_a_heat_adj DOUBLE NOT NULL DEFAULT 0,
      thresh_b_yellow_adj DOUBLE NOT NULL DEFAULT 0,
      state_json TEXT NULL,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      INDEX idx_calib_state_scope_mod (scope, modality),
      INDEX idx_calib_state_tag (tag)
    )
    """,
]


def _slug(text: str, limit: int = 48) -> str:
    raw = (text or "").strip()
    if not raw:
        return "unknown"
    cleaned = re.sub(r"[^\w\u4e00-\u9fff\-]+", "_", raw, flags=re.UNICODE)
    return cleaned[:limit] or "unknown"


def make_state_key(scope: str, modality: str, tag: str | None = None) -> str:
    mod = (modality or "all").strip().lower() or "all"
    if scope == "global":
        return f"global|{mod}"
    if scope == "device":
        return f"device:{_slug(tag or 'global')}|{mod}"
    if scope == "user":
        return f"user:{_slug(tag or 'anon')}|{mod}"
    if scope == "disease":
        return f"disease:{_slug(tag or 'none')}|{mod}"
    if scope == "allergen":
        return f"allergen:{_slug(tag or 'none')}|{mod}"
    return f"{_slug(scope)}|{mod}"


def empty_compensation() -> dict[str, Any]:
    return {
        "cct_bias_k": 0.0,
        "brightness_bias": 0.0,
        "thresh_delta_e_adj": 0.0,
        "thresh_a_heat_adj": 0.0,
        "thresh_b_yellow_adj": 0.0,
        "n": 0,
        "sources": [],
        "ml_hook": {"version": ML_HOOK_VERSION, "ready": False, "backend": None},
    }


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _ewma(prev: float | None, sample: float, alpha: float) -> float:
    if prev is None:
        return float(sample)
    return (1.0 - alpha) * float(prev) + alpha * float(sample)


def _row_to_comp(row: dict[str, Any] | None, source: str) -> dict[str, Any]:
    if not row:
        return empty_compensation()
    return {
        "cct_bias_k": float(row.get("cct_bias_k") or 0.0),
        "brightness_bias": float(row.get("brightness_bias") or 0.0),
        "thresh_delta_e_adj": float(row.get("thresh_delta_e_adj") or 0.0),
        "thresh_a_heat_adj": float(row.get("thresh_a_heat_adj") or 0.0),
        "thresh_b_yellow_adj": float(row.get("thresh_b_yellow_adj") or 0.0),
        "n": int(row.get("n") or 0),
        "sources": [source],
        "ewma_cct": row.get("ewma_cct"),
        "ewma_brightness": row.get("ewma_brightness"),
        "ml_hook": _parse_ml_hook(row.get("state_json")),
    }


def _parse_ml_hook(raw: Any) -> dict[str, Any]:
    base = {"version": ML_HOOK_VERSION, "ready": False, "backend": None}
    if not raw:
        return base
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError, json.JSONDecodeError):
        return base
    if not isinstance(data, dict):
        return base
    hook = data.get("ml_hook")
    if isinstance(hook, dict):
        out = dict(base)
        out.update({k: hook.get(k, out.get(k)) for k in ("version", "ready", "backend")})
        return out
    return base


def ml_hook_placeholder(state_json: dict[str, Any] | None = None) -> dict[str, Any]:
    """Stable hook for a future on-device / server model (no GPU in v1)."""
    payload = dict(state_json or {})
    payload.setdefault(
        "ml_hook",
        {"version": ML_HOOK_VERSION, "ready": False, "backend": None, "note": "EWMA only"},
    )
    return payload


def _fetch_state(cur, state_key: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT state_key, scope, modality, tag, n, ewma_cct, ewma_brightness,
               ewma_L, ewma_a, ewma_b, cct_bias_k, brightness_bias,
               thresh_delta_e_adj, thresh_a_heat_adj, thresh_b_yellow_adj, state_json
        FROM color_calib_state
        WHERE state_key = %s
        """,
        (state_key,),
    )
    return cur.fetchone()


def load_compensation(
    conn,
    *,
    modality: str,
    user_id: str | None = None,
    device_key: str | None = None,
    conditions: list[str] | tuple[str, ...] | None = None,
    allergies: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Merge global + device (+ mild disease/allergen threshold) compensation."""
    mod = (modality or "all").strip().lower()
    if mod not in MODALITIES:
        mod = "all"
    merged = empty_compensation()
    weights: list[tuple[dict[str, Any], float]] = []
    try:
        with conn.cursor() as cur:
            keys = [
                ("global", make_state_key("global", mod), 0.45),
                ("global_all", make_state_key("global", "all"), 0.15),
            ]
            if device_key:
                keys.append(("device", make_state_key("device", mod, device_key), 0.35))
            if user_id:
                keys.append(("user", make_state_key("user", mod, user_id), 0.20))
            for source, key, weight in keys:
                row = _fetch_state(cur, key)
                if row and int(row.get("n") or 0) > 0:
                    weights.append((_row_to_comp(row, source), weight))
            # Disease / allergen: threshold soft bias only (do not dominate CCT).
            for label in conditions or ():
                row = _fetch_state(cur, make_state_key("disease", mod, str(label)))
                if row and int(row.get("n") or 0) >= 3:
                    weights.append((_row_to_comp(row, f"disease:{label}"), 0.12))
            for label in allergies or ():
                row = _fetch_state(cur, make_state_key("allergen", mod, str(label)))
                if row and int(row.get("n") or 0) >= 3:
                    weights.append((_row_to_comp(row, f"allergen:{label}"), 0.08))
    except Exception:
        logger.exception("color_calib_state load failed")
        return merged

    if not weights:
        return merged

    total_w = sum(w for _c, w in weights) or 1.0
    for field in (
        "cct_bias_k",
        "brightness_bias",
        "thresh_delta_e_adj",
        "thresh_a_heat_adj",
        "thresh_b_yellow_adj",
    ):
        merged[field] = sum(float(c[field]) * w for c, w in weights) / total_w
    merged["n"] = max(int(c["n"]) for c, _w in weights)
    merged["sources"] = [s for c, _w in weights for s in c.get("sources") or []]
    merged["cct_bias_k"] = _clamp(merged["cct_bias_k"], -MAX_CCT_BIAS_K, MAX_CCT_BIAS_K)
    merged["brightness_bias"] = _clamp(
        merged["brightness_bias"], -MAX_BRIGHTNESS_BIAS, MAX_BRIGHTNESS_BIAS
    )
    for field in ("thresh_delta_e_adj", "thresh_a_heat_adj", "thresh_b_yellow_adj"):
        merged[field] = _clamp(merged[field], -MAX_THRESH_ADJ, MAX_THRESH_ADJ)
    return merged


def apply_lighting_compensation(
    estimated_cct: float,
    estimated_brightness: float,
    brightness_gain: float,
    online: dict[str, Any] | None,
) -> tuple[float, float, float, dict[str, Any]]:
    """Shift CCT / exposure using MySQL-accumulated biases (after device calib)."""
    online = online or empty_compensation()
    cct_bias = _clamp(float(online.get("cct_bias_k") or 0.0), -MAX_CCT_BIAS_K, MAX_CCT_BIAS_K)
    bright_bias = _clamp(
        float(online.get("brightness_bias") or 0.0), -MAX_BRIGHTNESS_BIAS, MAX_BRIGHTNESS_BIAS
    )
    compensated_cct = float(estimated_cct) + cct_bias
    # brightness_bias > 0 ⇒ scenes were dark ⇒ boost gain slightly
    compensated_gain = float(brightness_gain) * (1.0 + bright_bias)
    compensated_gain = _clamp(compensated_gain, 0.55, 1.85)
    meta = {
        "online_cct_bias_k": round(cct_bias, 2),
        "online_brightness_bias": round(bright_bias, 4),
        "online_n": int(online.get("n") or 0),
        "online_sources": list(online.get("sources") or []),
        "compensated_cct": round(compensated_cct, 1),
        "compensated_gain": round(compensated_gain, 4),
        "ml_hook": online.get("ml_hook") or {"version": ML_HOOK_VERSION, "ready": False},
    }
    return compensated_cct, float(estimated_brightness), compensated_gain, meta


def apply_threshold_adjustments(
    thresholds: dict[str, Any],
    online: dict[str, Any] | None,
    *,
    modality: str,
) -> dict[str, Any]:
    """Return a shallow-adjusted copy of Lab thresholds for classify."""
    out = dict(thresholds or {})
    online = online or empty_compensation()
    a_adj = _clamp(float(online.get("thresh_a_heat_adj") or 0.0), -MAX_THRESH_ADJ, MAX_THRESH_ADJ)
    b_adj = _clamp(float(online.get("thresh_b_yellow_adj") or 0.0), -MAX_THRESH_ADJ, MAX_THRESH_ADJ)
    de_adj = _clamp(float(online.get("thresh_delta_e_adj") or 0.0), -MAX_THRESH_ADJ, MAX_THRESH_ADJ)
    if modality == "tongue":
        if "body_heat_a_min" in out:
            out["body_heat_a_min"] = float(out["body_heat_a_min"]) + a_adj
        if "coat_yellow_b" in out:
            out["coat_yellow_b"] = float(out["coat_yellow_b"]) + b_adj
        if "coat_yellow_db" in out:
            out["coat_yellow_db"] = float(out["coat_yellow_db"]) + b_adj * 0.5
    elif modality == "face":
        if "shi_re_da" in out:
            out["shi_re_da"] = float(out["shi_re_da"]) + a_adj
        if "xu_re_da_min" in out:
            out["xu_re_da_min"] = float(out["xu_re_da_min"]) + a_adj * 0.5
        if "damp_db" in out:
            out["damp_db"] = float(out["damp_db"]) + b_adj
    # delta_e soft nudge stored for callers that score from ΔE
    out["_online_delta_e_adj"] = de_adj
    out["_online_applied"] = bool(a_adj or b_adj or de_adj)
    return out


def _lab_from_report(report: dict[str, Any]) -> tuple[float | None, float | None, float | None]:
    shot = report.get("shot_type")
    if shot == "face":
        lab = ((report.get("face_grid") or {}).get("complexion") or {}).get("lab") or {}
        return lab.get("L"), lab.get("a_star"), lab.get("b_star")
    if shot == "tongue":
        body = ((report.get("tongue_grid") or {}).get("body") or {}).get("lab") or {}
        if body:
            return body.get("L"), body.get("a_star"), body.get("b_star")
        return None, None, None
    if shot == "stool":
        lab = ((report.get("stool") or {}).get("lab") or {})
        return lab.get("L"), lab.get("a_star"), lab.get("b_star")
    if shot == "urine":
        lab = ((report.get("urine") or {}).get("lab") or {})
        return lab.get("L"), lab.get("a_star"), lab.get("b_star")
    return None, None, None


def _hsv_from_report(report: dict[str, Any]) -> tuple[float | None, float | None, float | None]:
    hsv = report.get("hsv")
    if isinstance(hsv, dict):
        if "H" in hsv:
            return hsv.get("H"), hsv.get("S"), hsv.get("V")
        return hsv.get("hue"), hsv.get("saturation"), hsv.get("value")
    return None, None, None


def _class_and_delta(report: dict[str, Any]) -> tuple[str | None, float | None]:
    shot = report.get("shot_type")
    if shot == "face":
        complexion = (report.get("face_grid") or {}).get("complexion") or {}
        health = (report.get("face_grid") or {}).get("color_health") or {}
        blocks = health.get("blocks") or []
        delta = None
        if blocks:
            try:
                delta = float(blocks[0].get("delta_e"))
            except (TypeError, ValueError):
                delta = None
        return report.get("color_label") or complexion.get("bias"), delta
    if shot == "tongue":
        body = (report.get("tongue_grid") or {}).get("body") or {}
        return report.get("color_label") or body.get("bias"), body.get("delta_e") or body.get(
            "body_delta_e"
        )
    if shot == "stool":
        hit = ((report.get("stool") or {}).get("class") or {})
        return hit.get("label") or report.get("color_label"), hit.get("delta_e")
    if shot == "urine":
        hit = ((report.get("urine") or {}).get("class") or {})
        return hit.get("label") or report.get("color_label"), hit.get("delta_e")
    return report.get("color_label"), None


def build_sample_from_report(
    report: dict[str, Any],
    *,
    user_id: str | None,
    record_id: int | None,
    device_key: str | None,
    conditions: list[str] | tuple[str, ...] | None,
    allergies: list[str] | tuple[str, ...] | None,
    quiet: bool,
) -> dict[str, Any] | None:
    modality = (report.get("shot_type") or "").strip().lower()
    if modality not in MODALITIES:
        return None
    L, a_star, b_star = _lab_from_report(report)
    h, s, v = _hsv_from_report(report)
    label, delta_e = _class_and_delta(report)
    features = {
        "lighting_calib": report.get("lighting_calib"),
        "online_calib": report.get("online_calib"),
        "cct_raw": report.get("cct_raw"),
        "brightness_raw": report.get("brightness_raw"),
        "brightness_after": report.get("brightness_after"),
        "ml_hook": {"version": ML_HOOK_VERSION, "ready": False},
    }
    if modality == "stool" and report.get("stool"):
        features["stool_class_id"] = ((report["stool"].get("class") or {}).get("id"))
    if modality == "urine" and report.get("urine"):
        features["urine_class_id"] = ((report["urine"].get("class") or {}).get("id"))
        features["turbidity"] = (report["urine"].get("turbidity"))
    return {
        "user_id": user_id,
        "record_id": record_id,
        "device_key": device_key or "global",
        "modality": modality,
        "cct_raw": report.get("cct_raw") if report.get("cct_raw") is not None else report.get(
            "color_temperature_k"
        ),
        "cct_used": report.get("color_temperature_k"),
        "brightness_raw": report.get("brightness_raw")
        if report.get("brightness_raw") is not None
        else report.get("brightness"),
        "brightness_gain": report.get("brightness_gain"),
        "L": L,
        "a_star": a_star,
        "b_star": b_star,
        "h": h,
        "s": s,
        "v": v,
        "class_label": (str(label)[:128] if label else None),
        "delta_e": delta_e,
        "conditions_json": json.dumps(list(conditions or []), ensure_ascii=False),
        "allergies_json": json.dumps(list(allergies or []), ensure_ascii=False),
        "features_json": json.dumps(features, ensure_ascii=False),
        "quiet": 1 if quiet else 0,
    }


def insert_samples(conn, samples: list[dict[str, Any]]) -> int:
    if not samples:
        return 0
    sql = """
        INSERT INTO color_calib_samples (
          user_id, record_id, device_key, modality,
          cct_raw, cct_used, brightness_raw, brightness_gain,
          L, a_star, b_star, h, s, v,
          class_label, delta_e, conditions_json, allergies_json,
          features_json, quiet
        ) VALUES (
          %s, %s, %s, %s,
          %s, %s, %s, %s,
          %s, %s, %s, %s, %s, %s,
          %s, %s, %s, %s,
          %s, %s
        )
    """
    rows = [
        (
            s.get("user_id"),
            s.get("record_id"),
            s.get("device_key"),
            s.get("modality"),
            s.get("cct_raw"),
            s.get("cct_used"),
            s.get("brightness_raw"),
            s.get("brightness_gain"),
            s.get("L"),
            s.get("a_star"),
            s.get("b_star"),
            s.get("h"),
            s.get("s"),
            s.get("v"),
            s.get("class_label"),
            s.get("delta_e"),
            s.get("conditions_json"),
            s.get("allergies_json"),
            s.get("features_json"),
            int(s.get("quiet") or 0),
        )
        for s in samples
    ]
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    return len(rows)


def _upsert_state_from_sample(
    cur,
    *,
    scope: str,
    modality: str,
    tag: str | None,
    sample: dict[str, Any],
    alpha: float,
    lighting: bool,
    thresholds: bool,
) -> None:
    key = make_state_key(scope, modality, tag)
    row = _fetch_state(cur, key)
    n = int((row or {}).get("n") or 0)
    use_alpha = min(0.45, alpha + 0.12) if n < 5 else alpha

    cct = sample.get("cct_raw")
    if cct is None:
        cct = sample.get("cct_used")
    bright = sample.get("brightness_raw")
    L = sample.get("L")
    a_star = sample.get("a_star")
    b_star = sample.get("b_star")

    ewma_cct = _ewma((row or {}).get("ewma_cct"), float(cct), use_alpha) if cct is not None else (row or {}).get("ewma_cct")
    ewma_bright = (
        _ewma((row or {}).get("ewma_brightness"), float(bright), use_alpha)
        if bright is not None
        else (row or {}).get("ewma_brightness")
    )
    ewma_L = _ewma((row or {}).get("ewma_L"), float(L), use_alpha) if L is not None else (row or {}).get("ewma_L")
    ewma_a = _ewma((row or {}).get("ewma_a"), float(a_star), use_alpha) if a_star is not None else (row or {}).get("ewma_a")
    ewma_b = _ewma((row or {}).get("ewma_b"), float(b_star), use_alpha) if b_star is not None else (row or {}).get("ewma_b")

    cct_bias = float((row or {}).get("cct_bias_k") or 0.0)
    bright_bias = float((row or {}).get("brightness_bias") or 0.0)
    de_adj = float((row or {}).get("thresh_delta_e_adj") or 0.0)
    a_adj = float((row or {}).get("thresh_a_heat_adj") or 0.0)
    b_adj = float((row or {}).get("thresh_b_yellow_adj") or 0.0)

    if lighting and ewma_cct is not None:
        target_bias = DEFAULT_CCT_K - float(ewma_cct)
        cct_bias = _clamp(
            _ewma(cct_bias, target_bias * 0.35, use_alpha),
            -MAX_CCT_BIAS_K,
            MAX_CCT_BIAS_K,
        )
    if lighting and ewma_bright is not None:
        # Positive when chronically underexposed.
        target_b = (TARGET_BRIGHTNESS - float(ewma_bright)) / max(TARGET_BRIGHTNESS, 1e-6)
        bright_bias = _clamp(
            _ewma(bright_bias, _clamp(target_b * 0.25, -MAX_BRIGHTNESS_BIAS, MAX_BRIGHTNESS_BIAS), use_alpha),
            -MAX_BRIGHTNESS_BIAS,
            MAX_BRIGHTNESS_BIAS,
        )

    if thresholds:
        delta_e = sample.get("delta_e")
        quiet = bool(int(sample.get("quiet") or 0))
        # Quiet + small ΔE → slightly raise heat/yellow gates (fewer false positives).
        # Disease-scoped updates learn the opposite: allow lower gates when patterns recur.
        if delta_e is not None:
            de = float(delta_e)
            if quiet and de < 4.0:
                de_adj = _clamp(_ewma(de_adj, 0.15, use_alpha * 0.5), -MAX_THRESH_ADJ, MAX_THRESH_ADJ)
            elif not quiet and de > 8.0:
                de_adj = _clamp(_ewma(de_adj, -0.25, use_alpha * 0.5), -MAX_THRESH_ADJ, MAX_THRESH_ADJ)
        if a_star is not None and modality in {"face", "tongue"}:
            # Drift of mean a* vs teaching normals (face ~12, tongue body ~23).
            ref_a = 23.0 if modality == "tongue" else 12.0
            drift = float(a_star) - ref_a
            # Disease/allergen buckets track observed drift; global/device stay conservative.
            if scope in {"disease", "allergen"}:
                a_adj = _clamp(_ewma(a_adj, drift * 0.05, use_alpha), -MAX_THRESH_ADJ, MAX_THRESH_ADJ)
            elif quiet:
                a_adj = _clamp(_ewma(a_adj, max(0.0, -drift) * 0.02, use_alpha * 0.4), -MAX_THRESH_ADJ, MAX_THRESH_ADJ)
        if b_star is not None and modality in {"face", "tongue", "stool", "urine"}:
            ref_b = 12.0 if modality == "tongue" else (20.0 if modality == "face" else 15.0)
            drift_b = float(b_star) - ref_b
            if scope in {"disease", "allergen"}:
                b_adj = _clamp(_ewma(b_adj, drift_b * 0.05, use_alpha), -MAX_THRESH_ADJ, MAX_THRESH_ADJ)
            elif quiet:
                b_adj = _clamp(_ewma(b_adj, max(0.0, -drift_b) * 0.02, use_alpha * 0.4), -MAX_THRESH_ADJ, MAX_THRESH_ADJ)

    state_json = json.dumps(ml_hook_placeholder({"n_next": n + 1}), ensure_ascii=False)
    cur.execute(
        """
        INSERT INTO color_calib_state (
          state_key, scope, modality, tag, n,
          ewma_cct, ewma_brightness, ewma_L, ewma_a, ewma_b,
          cct_bias_k, brightness_bias,
          thresh_delta_e_adj, thresh_a_heat_adj, thresh_b_yellow_adj,
          state_json
        ) VALUES (
          %s, %s, %s, %s, %s,
          %s, %s, %s, %s, %s,
          %s, %s,
          %s, %s, %s,
          %s
        )
        ON DUPLICATE KEY UPDATE
          n = VALUES(n),
          ewma_cct = VALUES(ewma_cct),
          ewma_brightness = VALUES(ewma_brightness),
          ewma_L = VALUES(ewma_L),
          ewma_a = VALUES(ewma_a),
          ewma_b = VALUES(ewma_b),
          cct_bias_k = VALUES(cct_bias_k),
          brightness_bias = VALUES(brightness_bias),
          thresh_delta_e_adj = VALUES(thresh_delta_e_adj),
          thresh_a_heat_adj = VALUES(thresh_a_heat_adj),
          thresh_b_yellow_adj = VALUES(thresh_b_yellow_adj),
          state_json = VALUES(state_json)
        """,
        (
            key,
            scope,
            modality,
            (tag or None),
            n + 1,
            ewma_cct,
            ewma_bright,
            ewma_L,
            ewma_a,
            ewma_b,
            cct_bias,
            bright_bias,
            de_adj,
            a_adj,
            b_adj,
            state_json,
        ),
    )


def update_states_from_sample(
    conn,
    sample: dict[str, Any],
    *,
    conditions: list[str] | tuple[str, ...] | None = None,
    allergies: list[str] | tuple[str, ...] | None = None,
) -> None:
    """Accumulate EWMA state; disease/allergen cross-check slows lighting, keeps tag buckets."""
    modality = sample.get("modality") or "all"
    quiet = bool(int(sample.get("quiet") or 0))
    device_key = sample.get("device_key") or "global"
    user_id = sample.get("user_id")
    # Lighting learns strongly on quiet shots; disease/allergen context dampens global drift.
    lighting_alpha = EMA_ALPHA if quiet else EMA_ALPHA * 0.35
    thresh_alpha = EMA_ALPHA * (0.9 if quiet else 0.55)
    try:
        with conn.cursor() as cur:
            _upsert_state_from_sample(
                cur,
                scope="global",
                modality=modality,
                tag=None,
                sample=sample,
                alpha=lighting_alpha,
                lighting=True,
                thresholds=True,
            )
            _upsert_state_from_sample(
                cur,
                scope="global",
                modality="all",
                tag=None,
                sample=sample,
                alpha=lighting_alpha * 0.8,
                lighting=True,
                thresholds=False,
            )
            _upsert_state_from_sample(
                cur,
                scope="device",
                modality=modality,
                tag=str(device_key),
                sample=sample,
                alpha=lighting_alpha,
                lighting=True,
                thresholds=True,
            )
            if user_id:
                _upsert_state_from_sample(
                    cur,
                    scope="user",
                    modality=modality,
                    tag=str(user_id),
                    sample=sample,
                    alpha=lighting_alpha,
                    lighting=True,
                    thresholds=True,
                )
            # Cross-check: special diseases / allergens get their own Lab/threshold buckets.
            for label in conditions or ():
                _upsert_state_from_sample(
                    cur,
                    scope="disease",
                    modality=modality,
                    tag=str(label),
                    sample=sample,
                    alpha=thresh_alpha,
                    lighting=False,
                    thresholds=True,
                )
            for label in allergies or ():
                _upsert_state_from_sample(
                    cur,
                    scope="allergen",
                    modality=modality,
                    tag=str(label),
                    sample=sample,
                    alpha=thresh_alpha,
                    lighting=False,
                    thresholds=True,
                )
    except Exception:
        logger.exception("color_calib_state update failed")


def persist_session_calibration(
    conn,
    *,
    reports: list[dict[str, Any]],
    user_id: str | None,
    record_id: int | None,
    device_key: str | None,
    conditions: list[str] | tuple[str, ...] | None,
    allergies: list[str] | tuple[str, ...] | None,
    quiet: bool,
) -> dict[str, Any]:
    """Insert samples and update running state. Safe to call after /api/record."""
    samples: list[dict[str, Any]] = []
    for report in reports or []:
        sample = build_sample_from_report(
            report,
            user_id=user_id,
            record_id=record_id,
            device_key=device_key,
            conditions=conditions,
            allergies=allergies,
            quiet=quiet,
        )
        if sample:
            samples.append(sample)
    summary = {"inserted": 0, "modalities": [], "quiet": quiet}
    if not samples:
        return summary
    try:
        summary["inserted"] = insert_samples(conn, samples)
        for sample in samples:
            update_states_from_sample(
                conn,
                sample,
                conditions=conditions,
                allergies=allergies,
            )
            summary["modalities"].append(sample["modality"])
    except Exception:
        logger.exception("persist_session_calibration failed")
    return summary


def inspect_calibration_growth(conn, *, limit: int = 20) -> dict[str, Any]:
    """Helper for ops: sample counts + top state keys."""
    out: dict[str, Any] = {"samples_by_modality": {}, "top_states": []}
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT modality, COUNT(*) AS n
                FROM color_calib_samples
                GROUP BY modality
                """
            )
            for row in cur.fetchall() or []:
                out["samples_by_modality"][row["modality"]] = int(row["n"])
            cur.execute(
                """
                SELECT state_key, scope, modality, n, cct_bias_k, brightness_bias,
                       thresh_a_heat_adj, thresh_b_yellow_adj, updated_at
                FROM color_calib_state
                ORDER BY n DESC, updated_at DESC
                LIMIT %s
                """,
                (int(limit),),
            )
            out["top_states"] = list(cur.fetchall() or [])
    except Exception:
        logger.exception("inspect_calibration_growth failed")
    return out
