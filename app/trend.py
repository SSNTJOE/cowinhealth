from __future__ import annotations

from datetime import datetime

# Unique color + marker per organ. Markers are names both Chart.js and Android map.
TREND_ORGANS = [
    {"key": "heart", "label": "心", "score_key": "heart_score", "color": "#d32f2f", "marker": "circle"},
    {"key": "liver", "label": "肝", "score_key": "liver_score", "color": "#2e7d32", "marker": "triangle"},
    {"key": "spleen", "label": "脾", "score_key": "spleen_score", "color": "#ef6c00", "marker": "square"},
    {"key": "lung", "label": "肺", "score_key": "lung_score", "color": "#1565c0", "marker": "diamond"},
    {"key": "kidney", "label": "腎", "score_key": "kidney_score", "color": "#6a1b9a", "marker": "x"},
    {"key": "gallbladder", "label": "膽", "score_key": "gallbladder_score", "color": "#f9a825", "marker": "star"},
    {"key": "large_intestine", "label": "大腸", "score_key": "large_intestine_score", "color": "#5d4037", "marker": "plus"},
    {"key": "small_intestine", "label": "小腸", "score_key": "small_intestine_score", "color": "#00838f", "marker": "rounded"},
    {"key": "bladder", "label": "膀胱", "score_key": "bladder_score", "color": "#558b2f", "marker": "dash"},
    {"key": "uterus", "label": "子宮", "score_key": "uterus_score", "color": "#c2185b", "marker": "line"},
]


def iso_time(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    text = str(value).replace(" ", "T")
    return text[:19]


def build_trend(rows: list[dict]) -> dict:
    chronological = list(reversed(rows or []))
    organs = []
    for spec in TREND_ORGANS:
        points = []
        for row in chronological:
            raw = row.get(spec["score_key"])
            try:
                score = int(raw)
            except (TypeError, ValueError):
                score = 5
            points.append({"t": iso_time(row.get("record_date")), "y": score})
        organs.append({**spec, "points": points})
    return {
        "y_min": 1,
        "y_max": 10,
        "y_label": "分數（5 未定，愈接近 1 偏移愈明確）",
        "organs": organs,
    }
