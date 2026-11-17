"""Daily nutrient targets from daily_nutrient.xlsx (age + gender). Teaching demo only."""

from __future__ import annotations

import re
from functools import lru_cache

from .config import ROOT

XLSX_PATH = ROOT / "daily_nutrient.xlsx"

NUTRIENT_KEYS: tuple[str, ...] = (
    "每日熱量(大卡)",
    "膳食纖維(克)",
    "鈣(克)",
    "鐵(克)",
    "鋅(克)",
    "碘(克)",
    "硒(克)",
    "維生素B(克)",
    "維生素C(克)",
    "維生素D(克)",
    "碳水化合物(克)",
    "蛋白質(克)",
    "脂質(克)",
    "水分(克)",
)

RECIPE_NUTRIENT_HEADERS: tuple[str, ...] = (
    "熱量(大卡)",
    "膳食纖維(克)",
    "鈣(克)",
    "鐵(克)",
    "鋅(克)",
    "碘(克)",
    "硒(克)",
    "維生素B(克)",
    "維生素C(克)",
    "維生素D(克)",
    "碳水化合物(克)",
    "蛋白質(克)",
    "脂質(克)",
    "水分(克)",
)

RECIPE_TO_TARGET = dict(zip(RECIPE_NUTRIENT_HEADERS, NUTRIENT_KEYS))

AGE_BANDS: tuple[tuple[int, int | None, str], ...] = (
    (7, 9, "7-9 歲"),
    (10, 12, "10-12 歲"),
    (13, 15, "13-15 歲"),
    (16, 18, "16-18 歲"),
    (19, 50, "19-50 歲"),
    (51, None, "51 歲以上"),
)

_GENDER_ZH = {
    "male": "男性",
    "m": "男性",
    "boy": "男性",
    "man": "男性",
    "男": "男性",
    "男生": "男性",
    "男性": "男性",
    "female": "女性",
    "f": "女性",
    "girl": "女性",
    "woman": "女性",
    "女": "女性",
    "女生": "女性",
    "女性": "女性",
}


def normalize_gender_zh(gender: str | None) -> str:
    raw = str(gender or "").strip().lower()
    if raw in _GENDER_ZH:
        return _GENDER_ZH[raw]
    return "男性"


def age_band_label(age: int | None) -> str:
    if age is None:
        return "19-50 歲"
    try:
        years = int(age)
    except (TypeError, ValueError):
        return "19-50 歲"
    if years < 7:
        return "7-9 歲"
    for lo, hi, label in AGE_BANDS:
        if hi is None:
            if years >= lo:
                return label
        elif lo <= years <= hi:
            return label
    return "51 歲以上"


def _parse_number_token(token: str) -> float | None:
    text = (token or "").strip().replace(",", "").replace("，", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_target_value(raw) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip()
    if not text:
        return None
    single = _parse_number_token(text)
    if single is not None and not re.search(r"[–—\-〜~至到]", text):
        return single
    parts = re.split(r"[–—\-〜~至到]+", text)
    nums = [n for n in (_parse_number_token(p) for p in parts) if n is not None]
    if not nums:
        return None
    if len(nums) == 1:
        return nums[0]
    return (nums[0] + nums[1]) / 2.0


def parse_target_range(raw) -> tuple[float | None, float | None, float | None]:
    mid = parse_target_value(raw)
    if raw is None or mid is None:
        return None, None, None
    if isinstance(raw, (int, float)):
        v = float(raw)
        return v, v, v
    text = str(raw).strip()
    parts = re.split(r"[–—\-〜~至到]+", text)
    nums = [n for n in (_parse_number_token(p) for p in parts) if n is not None]
    if len(nums) >= 2:
        lo, hi = nums[0], nums[1]
        return lo, hi, (lo + hi) / 2.0
    if len(nums) == 1:
        return nums[0], nums[0], nums[0]
    return None, None, mid


@lru_cache(maxsize=2)
def _load_rows(mtime_ns: int) -> tuple[dict, ...]:
    del mtime_ns
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError("need openpyxl for daily_nutrient.xlsx") from exc
    path = XLSX_PATH
    if not path.exists():
        raise FileNotFoundError(str(path))
    wb = load_workbook(path, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    headers = [str(h).strip() if h is not None else "" for h in next(rows_iter)]
    index = {name: i for i, name in enumerate(headers) if name}
    out: list[dict] = []
    for cells in rows_iter:
        if not cells or all(c is None or str(c).strip() == "" for c in cells):
            continue

        def cell(name: str, _cells=cells, _index=index):
            i = _index.get(name)
            if i is None or i >= len(_cells):
                return None
            return _cells[i]

        band = str(cell("年齡層") or "").strip()
        gender = str(cell("性別") or "").strip()
        group = str(cell("族群分類") or "").strip()
        targets: dict[str, float] = {}
        ranges: dict[str, dict] = {}
        for key in NUTRIENT_KEYS:
            raw = cell(key)
            lo, hi, mid = parse_target_range(raw)
            if mid is not None:
                targets[key] = mid
            ranges[key] = {
                "low": lo,
                "high": hi,
                "mid": mid,
                "raw": None if raw is None else str(raw),
            }
        out.append(
            {
                "group": group,
                "age_band": band,
                "gender": gender,
                "targets": targets,
                "ranges": ranges,
            }
        )
    return tuple(out)


def nutrient_rows() -> tuple[dict, ...]:
    path = XLSX_PATH
    mtime = path.stat().st_mtime_ns if path.exists() else 0
    return _load_rows(mtime)


def lookup_targets(age: int | None, gender: str | None) -> dict:
    band = age_band_label(age)
    gender_zh = normalize_gender_zh(gender)
    matched = None
    for row in nutrient_rows():
        if row["age_band"] == band and row["gender"] == gender_zh:
            matched = row
            break
    if matched is None:
        for row in nutrient_rows():
            if row["age_band"] == "19-50 歲" and row["gender"] == "男性":
                matched = row
                break
    if matched is None:
        raise RuntimeError("daily_nutrient.xlsx has no usable rows")
    return {
        "age": age,
        "age_band": band,
        "gender": gender_zh,
        "group": matched["group"],
        "targets": dict(matched["targets"]),
        "ranges": {k: dict(v) for k, v in matched["ranges"].items()},
        "nutrient_keys": list(NUTRIENT_KEYS),
        "disclaimer": "教學示範，非診斷或營養處方。",
    }


def empty_totals() -> dict[str, float]:
    return {key: 0.0 for key in NUTRIENT_KEYS}


def sum_nutrient_maps(parts: list[dict[str, float] | None]) -> dict[str, float]:
    total = empty_totals()
    for part in parts:
        if not part:
            continue
        for key in NUTRIENT_KEYS:
            try:
                total[key] += float(part.get(key) or 0.0)
            except (TypeError, ValueError):
                continue
    return total


def surplus_map(totals: dict[str, float], targets: dict[str, float]) -> dict[str, float]:
    return {
        key: float(totals.get(key) or 0.0) - float(targets.get(key) or 0.0)
        for key in NUTRIENT_KEYS
    }


def progress_map(totals: dict[str, float], targets: dict[str, float]) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for key in NUTRIENT_KEYS:
        target = float(targets.get(key) or 0.0)
        value = float(totals.get(key) or 0.0)
        if target <= 0:
            out[key] = None
        else:
            out[key] = round(100.0 * value / target, 1)
    return out


def short_label(key: str) -> str:
    text = str(key or "")
    text = re.sub(r"[（(][^）)]*[）)]", "", text)
    return text.strip() or key


def chart_labels() -> list[str]:
    return [short_label(key) for key in NUTRIENT_KEYS]
