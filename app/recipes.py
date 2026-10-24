from __future__ import annotations

from functools import lru_cache

from .config import ROOT
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
# Header row of Recipe.xls (0-based), read with xlrd:
# 0 國家, 1 中文食譜, 2 英文食譜, 3 日文食譜, 4 韓文食譜,
# 5 食譜, 6 煮法, 7 益處, 8 禁忌, 9 元素, 10 過敏原.
# Names are one column per homepage language. 食譜／煮法／益處／元素 are single columns.
COLUMN_FIELDS = (
    ("country", "國家"),
    ("name_zh", "中文食譜"),
    ("name_en", "英文食譜"),
    ("name_ja", "日文食譜"),
    ("name_ko", "韓文食譜"),
    ("recipe", "食譜"),
    ("method", "煮法"),
    ("benefit", "益處"),
    ("ban", "禁忌"),
    ("nutrient", "元素"),
    ("allergens", "過敏原"),
)
# 禁忌篩選只用這些臟腑。膀胱不列入。子宮只在女生。
CONTRAINDICATION_ORGANS = (
    ("liver", "肝", "liver_score", "liver_pattern"),
    ("heart", "心", "heart_score", "heart_pattern"),
    ("spleen", "脾", "spleen_score", "spleen_pattern"),
    ("lung", "肺", "lung_score", "lung_pattern"),
    ("kidney", "腎", "kidney_score", "kidney_pattern"),
    ("gallbladder", "膽", "gallbladder_score", "gallbladder_pattern"),
    ("small_intestine", "小腸", "small_intestine_score", "small_intestine_pattern"),
    ("stomach", "胃", "stomach_score", "stomach_pattern"),
    ("large_intestine", "大腸", "large_intestine_score", "large_intestine_pattern"),
)
UTERUS_ORGAN = ("uterus", "子宮", "uterus_score", "uterus_pattern")
FILTER_PATTERNS = frozenset({"實熱", "實寒", "虛熱", "虛寒"})


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
    headers = [str(sheet.cell_value(0, col)).strip() for col in range(sheet.ncols)]
    index = {name: pos for pos, name in enumerate(headers)}

    def read(row: int, header: str) -> str:
        col = index.get(header)
        if col is None or col < 0 or col >= sheet.ncols:
            return ""
        return str(sheet.cell_value(row, col)).strip()

    rows: list[dict[str, str]] = []
    for row in range(1, sheet.nrows):
        item = {"id": str(row), "_headers": "\t".join(headers)}
        for field, header in COLUMN_FIELDS:
            item[field] = read(row, header)
        rows.append(item)
    return tuple(rows)


def recipe_rows() -> tuple[dict[str, str], ...]:
    path = RECIPE_PATH
    mtime = path.stat().st_mtime_ns if path.exists() else 0
    return _rows_cached(mtime)


def countries(prefix: str | None = None) -> list[str]:
    needle = (prefix or "").strip().casefold()
    seen: set[str] = set()
    ordered: list[str] = []
    for row in recipe_rows():
        name = row.get("country") or ""
        if not name or name in seen:
            continue
        if needle and not name.casefold().startswith(needle):
            continue
        seen.add(name)
        ordered.append(name)
    return ordered


def recipe_excluded(
    row: dict[str, str],
    allergy_tokens: list[str],
    condition_tokens: list[str],
    organ_tags: list[str],
) -> bool:
    if recipe_contains_allergen(row.get("allergens") or "", allergy_tokens):
        return True
    ban = row.get("ban") or ""
    if _text_has_any(ban, condition_tokens):
        return True
    return ban_has_pattern(ban, organ_tags)


def _filter_context(
    patterns: dict[str, str] | None,
    allergies: list[str] | None,
    conditions: list[str] | None,
    scores: dict | None,
    female: bool,
    by_body: bool,
) -> tuple[list[str], list[str], list[str]]:
    organ_tags = active_contraindications(scores, patterns, female) if by_body else []
    return organ_tags, condition_ban_tokens(conditions), allergy_exclude_tokens(allergies)


def usable_countries(
    prefix: str | None = None,
    patterns: dict[str, str] | None = None,
    pattern_labels: list[str] | None = None,
    allergies: list[str] | None = None,
    conditions: list[str] | None = None,
    scores: dict | None = None,
    female: bool = False,
    by_body: bool = False,
) -> list[str]:
    """Countries that still have at least one recipe after the active filters."""
    del pattern_labels
    needle = (prefix or "").strip().casefold()
    organ_tags, condition_tokens, allergy_tokens = _filter_context(
        patterns, allergies, conditions, scores, female, by_body
    )
    seen: set[str] = set()
    ordered: list[str] = []
    for row in recipe_rows():
        name = row.get("country") or ""
        if not name or name in seen:
            continue
        if needle and not name.casefold().startswith(needle):
            continue
        if recipe_excluded(row, allergy_tokens, condition_tokens, organ_tags):
            continue
        seen.add(name)
        ordered.append(name)
    return ordered


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


def ban_condition_tokens(ban: str) -> set[str]:
    """Column 禁忌 is ingredient:證型,證型;ingredient:證型."""
    tokens: set[str] = set()
    for part in (ban or "").split(";"):
        chunk = part.strip()
        if not chunk:
            continue
        haystack = chunk.split(":", 1)[1] if ":" in chunk else chunk
        tokens.update(split_tokens(haystack))
    return tokens


def ban_has_pattern(ban: str, pattern_tags: list[str]) -> bool:
    if not ban or not pattern_tags:
        return False
    tokens = ban_condition_tokens(ban)
    return any(tag and tag in tokens for tag in pattern_tags)


def parse_score(raw) -> int | None:
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        raw = text
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return int(round(number))


def _first_present(mapping: dict | None, keys: tuple[str, ...]):
    if not mapping:
        return None
    for key in keys:
        if key in mapping:
            return mapping.get(key)
    return None


def active_contraindications(
    scores: dict | None,
    patterns: dict | None,
    female: bool = False,
) -> list[str]:
    """Organ+證型 tags for scores 1–5 only. Score 6, 7–10, and missing scores do not filter."""
    organs = list(CONTRAINDICATION_ORGANS)
    if female:
        organs.append(UTERUS_ORGAN)
    tags: list[str] = []
    seen: set[str] = set()
    for key, name, score_key, pattern_key in organs:
        score = parse_score(_first_present(scores, (score_key, key, name)))
        if score is None or score < 1 or score > 5:
            continue
        raw_pattern = _first_present(patterns, (pattern_key, key, name))
        compact = compact_pattern("" if raw_pattern is None else str(raw_pattern))
        if compact not in FILTER_PATTERNS:
            continue
        tag = f"{name}{compact}"
        if tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags


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
        "method": row.get("method") or "",
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
    scores: dict | None = None,
    female: bool = False,
    by_body: bool = False,
    limit: int | None = None,
) -> dict:
    del pattern_labels  # tags without a 1–5 score must not filter
    wanted = (country or "").strip()
    if not wanted:
        raise ValueError("請選擇國家")
    lang = normalize_lang(lang)
    # Off: allergens (and listed conditions) only. On: also today's 1–5 organ patterns, including 脾／胃.
    organ_tags, condition_tokens, allergy_tokens = _filter_context(
        patterns, allergies, conditions, scores, female, by_body
    )
    matched: list[tuple[int, dict[str, str]]] = []
    safe: list[tuple[int, dict[str, str]]] = []
    for row in recipe_rows():
        if (row.get("country") or "") != wanted:
            continue
        if recipe_excluded(row, allergy_tokens, condition_tokens, organ_tags):
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
    if limit is not None:
        picked = picked[: max(1, limit)]
    recipes = [public_recipe(row, lang, score) for score, row in picked]
    return {
        "country": wanted,
        "lang": lang,
        "by_body": bool(by_body),
        "patterns": organ_tags,
        "count": len(recipes),
        "benefit_matches": len(matched),
        "recipes": recipes,
        "disclaimer": TEACHING_DISCLAIMER,
    }
