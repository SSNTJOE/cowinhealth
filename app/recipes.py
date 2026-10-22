from __future__ import annotations

from functools import lru_cache

from .config import ROOT
<<<<<<< HEAD

RECIPE_PATH = ROOT / "Recipe.xls"
SPLIT_MARKS = ("、", ",", ";", "/", "，")
=======
from .health_flags import CONDITION_OPTIONS, allergy_exclude_tokens
from .syndrome import ORGAN_META

RECIPE_PATH = ROOT / "Recipe.xls"
SPLIT_MARKS = ("、", ",", ";", "/", "，")
LANGS = ("zh", "en", "ja", "ko")
NAME_FIELDS = {"zh": "name_zh", "en": "name_en", "ja": "name_ja", "ko": "name_ko"}
SKIP_PATTERNS = {"", "健康", "未定", "待觀察", "色差基準", "基本色"}
COMPACT_ALIASES = {
    "實熱": "實熱",
    "實熱色": "實熱",
    "實證熱證": "實熱",
    "虛熱": "虛熱",
    "虛熱色": "虛熱",
    "虛證熱證": "虛熱",
    "實寒": "實寒",
    "實寒色": "實寒",
    "實證寒證": "實寒",
    "虛寒": "虛寒",
    "虛寒色": "虛寒",
    "虛證寒證": "虛寒",
    "濕": "濕",
    "濕熱": "濕",
    "濕熱證": "濕",
    "寒濕": "濕",
    "寒濕證": "濕",
    "濕氣較重": "濕",
    "濕症": "濕",
}
CONDITION_BAN_TOKENS = {
    "糖尿病": ("糖尿病", "消渴", "高糖"),
    "中風": ("中風", "卒中"),
    "痛風": ("痛風", "高普林", "尿酸"),
    "腎臟病": ("腎臟病", "腎衰竭", "肾病"),
    "肝病": ("肝病", "肝炎", "肝硬化"),
    "高血壓": ("高血壓", "高血压"),
    "服用抗凝血劑": ("抗凝血", "出血"),
}
TEACHING_DISCLAIMER = "教學示範，非中醫診斷或營養處方。食譜與禁忌／益處來自 Recipe.xls 欄位，不能取代醫師建議。"
# H 欄是「食材:證型」；鹽／醬油幾乎每道都標了虛寒禁忌，教學篩選時略過調味料。
SEASONING_SKIP = {
    "食鹽",
    "鹽",
    "醬油",
    "醋",
    "胡椒",
    "花生油",
    "麻油",
    "油",
    "白糖",
    "糖",
    "冰糖",
    "黃酒",
    "八角",
    "花椒",
    "月桂葉",
}
>>>>>>> 0d36a53 (Add Recipe.xls allergy checkboxes and rear-camera pulse on Android 16.)


def split_tokens(text: str | None) -> list[str]:
    blob = (text or "").strip()
    if not blob:
        return []
    for mark in SPLIT_MARKS[1:]:
        blob = blob.replace(mark, SPLIT_MARKS[0])
    seen: set[str] = set()
    tokens: list[str] = []
    for part in blob.split(SPLIT_MARKS[0]):
        token = part.strip()
        if token and token not in seen:
            seen.add(token)
            tokens.append(token)
    return tokens


def _open_sheet():
    try:
        import xlrd
    except ImportError as exc:
        raise RuntimeError("讀取 Recipe.xls 需要 xlrd==1.2.0") from exc
    if not RECIPE_PATH.exists():
        raise FileNotFoundError(str(RECIPE_PATH))
    return xlrd.open_workbook(str(RECIPE_PATH)).sheet_by_index(0)


@lru_cache(maxsize=4)
def _rows_cached(mtime_ns: int) -> tuple[dict[str, str], ...]:
    sheet = _open_sheet()
<<<<<<< HEAD
    headers = [str(sheet.cell_value(0, col)).strip() for col in range(sheet.ncols)]
    last = max(sheet.ncols - 1, 0)
=======
>>>>>>> 0d36a53 (Add Recipe.xls allergy checkboxes and rear-camera pulse on Android 16.)
    rows: list[dict[str, str]] = []
    for row in range(1, sheet.nrows):
        rows.append(
            {
<<<<<<< HEAD
                "country": str(sheet.cell_value(row, 0)).strip() if sheet.ncols > 0 else "",
                "name_zh": str(sheet.cell_value(row, 1)).strip() if sheet.ncols > 1 else "",
                "name_en": str(sheet.cell_value(row, 2)).strip() if sheet.ncols > 2 else "",
=======
                "id": str(row),
                "country": str(sheet.cell_value(row, 0)).strip() if sheet.ncols > 0 else "",
                "name_zh": str(sheet.cell_value(row, 1)).strip() if sheet.ncols > 1 else "",
                "name_en": str(sheet.cell_value(row, 2)).strip() if sheet.ncols > 2 else "",
                "name_ja": str(sheet.cell_value(row, 3)).strip() if sheet.ncols > 3 else "",
                "name_ko": str(sheet.cell_value(row, 4)).strip() if sheet.ncols > 4 else "",
>>>>>>> 0d36a53 (Add Recipe.xls allergy checkboxes and rear-camera pulse on Android 16.)
                "recipe": str(sheet.cell_value(row, 5)).strip() if sheet.ncols > 5 else "",
                "benefit": str(sheet.cell_value(row, 6)).strip() if sheet.ncols > 6 else "",
                "ban": str(sheet.cell_value(row, 7)).strip() if sheet.ncols > 7 else "",
                "nutrient": str(sheet.cell_value(row, 8)).strip() if sheet.ncols > 8 else "",
<<<<<<< HEAD
                "allergens": str(sheet.cell_value(row, last)).strip(),
                "_headers": "\t".join(headers),
=======
                "allergens": str(sheet.cell_value(row, 9)).strip() if sheet.ncols > 9 else "",
>>>>>>> 0d36a53 (Add Recipe.xls allergy checkboxes and rear-camera pulse on Android 16.)
            }
        )
    return tuple(rows)


def recipe_rows() -> tuple[dict[str, str], ...]:
    path = RECIPE_PATH
    mtime = path.stat().st_mtime_ns if path.exists() else 0
    return _rows_cached(mtime)


<<<<<<< HEAD
=======
def countries() -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for row in recipe_rows():
        name = row.get("country") or ""
        if name and name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


>>>>>>> 0d36a53 (Add Recipe.xls allergy checkboxes and rear-camera pulse on Android 16.)
def allergen_labels() -> tuple[str, ...]:
    seen: set[str] = set()
    labels: list[str] = []
    try:
        rows = recipe_rows()
    except Exception:
        return ()
    for row in rows:
        for token in split_tokens(row.get("allergens")):
            if token not in seen:
                seen.add(token)
                labels.append(token)
    return tuple(sorted(labels))


def recipe_contains_allergen(allergen_cell: str, tokens: list[str]) -> bool:
    if not tokens:
        return False
    cell_tokens = set(split_tokens(allergen_cell))
    blob = allergen_cell or ""
    for token in tokens:
        if not token:
            continue
        if token in cell_tokens or token in blob:
            return True
    return False
<<<<<<< HEAD
=======


def normalize_lang(lang: str | None) -> str:
    raw = (lang or "zh").strip().lower()
    if raw in ("zh-hant", "zh-tw", "zh-cn", "cn", "中文"):
        return "zh"
    if raw in ("en", "english", "eng"):
        return "en"
    if raw in ("ja", "jp", "日本語", "日文"):
        return "ja"
    if raw in ("ko", "kr", "한국어", "韓文", "韩文"):
        return "ko"
    return raw if raw in LANGS else "zh"


def localized_name(row: dict[str, str], lang: str) -> str:
    field = NAME_FIELDS.get(normalize_lang(lang), "name_zh")
    return row.get(field) or row.get("name_zh") or row.get("name_en") or ""


def compact_pattern(label: str | None) -> str | None:
    text = (label or "").strip()
    if text in SKIP_PATTERNS:
        return None
    if text in COMPACT_ALIASES:
        return COMPACT_ALIASES[text]
    if "濕" in text:
        return "濕"
    if "虛" in text and "熱" in text:
        return "虛熱"
    if "實" in text and "熱" in text:
        return "實熱"
    if "虛" in text and "寒" in text:
        return "虛寒"
    if "實" in text and "寒" in text:
        return "實寒"
    return None


def split_csv(raw: str | None) -> list[str]:
    if not raw:
        return []
    blob = raw.replace("|", ",")
    return [part.strip() for part in blob.split(",") if part.strip()]


def condition_ban_tokens(conditions: list[str] | None) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for label in conditions or []:
        words = CONDITION_BAN_TOKENS.get(label, (label,))
        for word in words:
            if word and word not in seen:
                seen.add(word)
                tokens.append(word)
        if label in CONDITION_OPTIONS and label not in seen:
            seen.add(label)
            tokens.append(label)
    return tokens


def organ_pattern_tags(patterns: dict[str, str] | None, extra: list[str] | None = None) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()

    def add(tag: str | None) -> None:
        if tag and tag not in seen and tag not in SKIP_PATTERNS:
            seen.add(tag)
            tags.append(tag)

    mapping = patterns or {}
    for key, name, _score_key, pattern_key in ORGAN_META:
        label = mapping.get(pattern_key) or mapping.get(key) or mapping.get(name) or ""
        compact = compact_pattern(label)
        if compact and compact != "濕":
            add(f"{name}{compact}")
        elif compact == "濕":
            add("濕")
    for item in extra or []:
        compact = compact_pattern(item)
        if item.endswith(("實熱", "虛熱", "實寒", "虛寒")) and len(item) >= 3:
            add(item)
        elif compact == "濕":
            add("濕")
        elif compact and item == compact:
            add(compact)
        elif compact:
            add(item if item not in COMPACT_ALIASES else compact)
        else:
            add(item)
    return tags


def _text_has_any(blob: str, tokens: list[str]) -> bool:
    if not blob or not tokens:
        return False
    return any(token and token in blob for token in tokens)


def ban_has_pattern(ban: str, pattern_tags: list[str]) -> bool:
    if not ban or not pattern_tags:
        return False
    for part in ban.split(";"):
        chunk = part.strip()
        if not chunk:
            continue
        if ":" in chunk:
            ingredient, rest = chunk.split(":", 1)
            if ingredient.strip() in SEASONING_SKIP:
                continue
            haystack = rest
        else:
            haystack = chunk
        if any(tag and tag in haystack for tag in pattern_tags):
            return True
    return False


def benefit_score(benefit: str, organ_tags: list[str]) -> int:
    if not benefit:
        return 0
    return sum(1 for tag in organ_tags if tag != "濕" and tag in benefit)


def public_recipe(row: dict[str, str], lang: str, score: int) -> dict[str, str | int | bool]:
    return {
        "id": int(row["id"]),
        "country": row.get("country") or "",
        "name": localized_name(row, lang),
        "recipe": row.get("recipe") or "",
        "benefit": row.get("benefit") or "",
        "ban": row.get("ban") or "",
        "nutrient": row.get("nutrient") or "",
        "allergens": row.get("allergens") or "",
        "benefit_match": score > 0,
        "benefit_score": score,
    }


def filter_recipes(
    country: str,
    lang: str = "zh",
    patterns: dict[str, str] | None = None,
    pattern_labels: list[str] | None = None,
    allergies: list[str] | None = None,
    conditions: list[str] | None = None,
    limit: int = 80,
) -> dict:
    wanted = (country or "").strip()
    if not wanted:
        raise ValueError("請選擇國家")
    lang = normalize_lang(lang)
    organ_tags = organ_pattern_tags(patterns, pattern_labels)
    condition_tokens = condition_ban_tokens(conditions)
    allergy_tokens = allergy_exclude_tokens(allergies)
    matched: list[tuple[int, dict[str, str]]] = []
    safe: list[tuple[int, dict[str, str]]] = []
    for row in recipe_rows():
        if (row.get("country") or "") != wanted:
            continue
        if recipe_contains_allergen(row.get("allergens") or "", allergy_tokens):
            continue
        ban = row.get("ban") or ""
        if _text_has_any(ban, condition_tokens):
            continue
        if ban_has_pattern(ban, organ_tags):
            continue
        score = benefit_score(row.get("benefit") or "", organ_tags)
        item = (score, row)
        if score > 0:
            matched.append(item)
        else:
            safe.append(item)
    matched.sort(key=lambda item: (-item[0], localized_name(item[1], lang)))
    safe.sort(key=lambda item: localized_name(item[1], lang))
    picked = matched + safe
    recipes = [public_recipe(row, lang, score) for score, row in picked[: max(1, limit)]]
    return {
        "country": wanted,
        "lang": lang,
        "patterns": organ_tags,
        "count": len(recipes),
        "benefit_matches": len(matched),
        "recipes": recipes,
        "disclaimer": TEACHING_DISCLAIMER,
    }
>>>>>>> 0d36a53 (Add Recipe.xls allergy checkboxes and rear-camera pulse on Android 16.)
