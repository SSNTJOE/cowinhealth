"""Find or create a Recipe.xls row via best-effort public web research; sync Foods.xls."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from html import unescape
from typing import Callable

from .config import ROOT
from .recipes import (
    COLUMN_FIELDS,
    NAME_FIELDS,
    RECIPE_PATH,
    TEACHING_DISCLAIMER,
    active_recipe_path,
    invalidate_recipe_cache,
    localized_name,
    normalize_lang,
    public_recipe,
    recipe_rows,
)

FOODS_PATH = ROOT / "Foods.xls"
SEARCH_TIMEOUT_SEC = 12
USER_AGENT = "Health-ingRecipeBot/1.0 (teaching demo; contact: local)"
CREATE_NOTE = "此列由網路公開資料自動彙整，欄位可能不完整；教學示範，非醫療建議。"
PARTIAL_NOTE = "部分欄位未能從網路可靠取得，已標示留白，請人工核對。"
UPDATE_NOTE = "已依網路公開資料補齊先前空白欄位；教學示範，非醫療建議。"
UNSUPPORTED_LANG_NOTE = (
    "目前僅支援中文／英文／日文／韓文食譜名稱；請改用這四種語文再搜尋或建檔。"
)
COUNTRY_CORRECTED_NOTE = "已依 Recipe.xls／目錄找到此食譜，並改回正確國家。"

FOOD_HEADERS = ("食材中文", "食材英文", "食材日文", "食材韓文", "益處", "禁忌", "元素表")

ALLERGEN_FOODS = frozenset(
    {
        "鯉魚", "鯽魚", "鱸魚", "草魚", "鰱魚", "青魚", "帶魚", "黃魚", "鯖魚", "鮪魚",
        "鮭魚", "鱈魚", "鯛魚", "秋刀魚", "沙丁魚", "鰻魚", "鱔魚", "泥鰍", "虱目魚",
        "石斑魚", "比目魚", "鯊魚", "白鯧", "烏魚", "鰹魚", "吳郭魚", "蝦", "蝦米",
        "龍蝦", "螃蟹", "蛤蜊", "牡蠣", "蜆", "淡菜", "干貝", "鮑魚", "章魚", "魷魚",
        "烏賊", "海蜇", "田螺", "蟶子", "海參", "海膽", "雞蛋", "蛋白", "蛋黃", "鴨蛋",
        "皮蛋", "鵪鶉蛋", "牛奶", "羊奶", "奶油", "起司", "優格", "小麥", "大麥", "燕麥",
        "黃豆", "黑豆", "豆腐", "豆漿", "豆干", "腐竹", "納豆", "醬油", "毛豆", "黃豆芽",
        "味噌", "花生", "花生油", "杏仁果", "腰果", "夏威夷豆", "核桃", "松子", "栗子",
        "甜杏仁", "北杏仁", "白果", "黑芝麻", "白芝麻", "麻油", "南瓜子", "葵花子",
        "亞麻仁", "蕎麥", "芹菜", "西洋芹", "芥末", "芥菜", "山葵", "醋", "黃酒", "葡萄酒",
    }
)

# Normalize wiki wording so Foods.xls names can match (variants / cooking terms).
_TEXT_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("鷄", "雞"),
    ("葱", "蔥"),
    ("麵粉", "小麥"),
    ("面粉", "小麥"),
    ("低筋麵粉", "小麥"),
    ("中筋麵粉", "小麥"),
    ("高筋麵粉", "小麥"),
    ("植物粉", "小麥"),
    ("鹽巴", "食鹽"),
    ("葱花", "蔥"),
    ("蔥花", "蔥"),
    ("tomato sauce", "番茄"),
    ("potato starch", "小麥"),
    ("glutinous rice flour", "小麥"),
    ("sweet potato flour", "小麥"),
    ("corn starch", "小麥"),
    ("cornstarch", "小麥"),
    ("scallion", "蔥"),
    ("green onion", "蔥"),
    ("chicken egg", "雞蛋"),
    ("peanut oil", "花生油"),
    ("soy sauce", "醬油"),
    ("wheat flour", "小麥"),
    ("flour", "小麥"),
    ("eggs", "雞蛋"),
    ("egg", "雞蛋"),
    ("salt", "食鹽"),
    ("cheese", "起司"),
    ("ham", "火腿"),
)

_WRITE_LOCK = threading.Lock()
_ING_RE = re.compile(r"^(.+?)\s+(\d+(?:\.\d+)?)\s*克$")
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_SALT_RE = re.compile(r"(?<![食廚海岩])鹽(?![酸水漬酥])")


ResearchFn = Callable[[str, str, str], dict[str, str | list[tuple[str, int]] | bool]]


def ensure_recipe(
    country: str,
    name: str,
    lang: str = "zh",
    *,
    research_fn: ResearchFn | None = None,
) -> dict:
    """Return existing recipe, backfill incomplete rows, or append a researched row.

    Lookup order:
    1. Country-scoped match (when country is provided).
    2. Global match on zh/en/ja/ko name columns in Recipe.xls / MySQL catalog —
       even when the selected country is wrong; return the real country so UI can
       correct the selector (no create).
    3. On miss: only zh/en/ja/ko name scripts may web-research and create; other
       scripts soft-fail without writing.
    Country may be empty: same global lookup, then research with inferred country
    (fallback ``Global``).
    """
    wanted_country = (country or "").strip()
    wanted_name = (name or "").strip()
    if not wanted_name:
        raise ValueError("請輸入食譜名稱")
    lang = normalize_lang(lang)

    existing, country_corrected = _resolve_existing_recipe(wanted_country, wanted_name, lang)
    if existing is not None:
        wanted_country = (existing.get("country") or "").strip() or wanted_country
    if existing is not None and not _row_needs_fill(existing):
        note = COUNTRY_CORRECTED_NOTE if country_corrected else ""
        return {
            "created": False,
            "partial": False,
            "country_corrected": country_corrected,
            "recipe": public_recipe(existing, lang, 0),
            "foods_added": [],
            "note": note,
            "disclaimer": TEACHING_DISCLAIMER,
        }

    # Miss in catalog: reject unsupported scripts before any web create.
    if not name_script_supported(wanted_name):
        return {
            "created": False,
            "rejected": True,
            "reason": "unsupported_lang",
            "partial": False,
            "country_corrected": False,
            "recipe": None,
            "foods_added": [],
            "note": UNSUPPORTED_LANG_NOTE,
            "disclaimer": TEACHING_DISCLAIMER,
        }

    if not _WRITE_LOCK.acquire(blocking=False):
        raise RuntimeError("另一筆食譜正在建立中，請稍後再試")
    try:
        # Re-check under lock in case a parallel request just wrote.
        invalidate_recipe_cache()
        existing, country_corrected = _resolve_existing_recipe(wanted_country, wanted_name, lang)
        if existing is not None:
            wanted_country = (existing.get("country") or "").strip() or wanted_country
        if existing is not None and not _row_needs_fill(existing):
            note = COUNTRY_CORRECTED_NOTE if country_corrected else ""
            return {
                "created": False,
                "partial": False,
                "country_corrected": country_corrected,
                "recipe": public_recipe(existing, lang, 0),
                "foods_added": [],
                "note": note,
                "disclaimer": TEACHING_DISCLAIMER,
            }

        research_country = wanted_country or _country_hint_for_name(wanted_name) or ""
        research = (research_fn or research_dish)(research_country, wanted_name, lang)
        inferred = str(research.get("country") or "").strip()
        if not wanted_country:
            wanted_country = (
                inferred
                or _country_hint_for_name(wanted_name)
                or _infer_country_from_text(str(research.get("source") or ""), wanted_name)
                or "Global"
            )
        fields = build_row_fields(wanted_country, wanted_name, lang, research)
        foods_added = sync_foods_for_ingredients(fields.get("recipe") or "")
        # Enrich benefit/ban/nutrient from Foods.xls when ingredients matched.
        fields = enrich_from_foods(fields)
        updated = False
        if existing is not None:
            fields = _merge_fill_fields(existing, fields)
            row = update_recipe_row(str(existing["id"]), fields)
            updated = True
        else:
            row = append_recipe_row(fields)
        invalidate_recipe_cache()
        partial = bool(research.get("partial")) or _is_partial(fields)
        note_parts = [UPDATE_NOTE if updated else CREATE_NOTE]
        if partial:
            note_parts.append(PARTIAL_NOTE)
        return {
            "created": not updated,
            "updated": updated,
            "partial": partial,
            "country_corrected": country_corrected,
            "recipe": public_recipe(row, lang, 0),
            "foods_added": foods_added,
            "note": " ".join(note_parts),
            "disclaimer": TEACHING_DISCLAIMER,
        }
    finally:
        _WRITE_LOCK.release()


def _resolve_existing_recipe(
    country: str, name: str, lang: str
) -> tuple[dict[str, str] | None, bool]:
    """Country-scoped hit first; else global zh/en/ja/ko name match.

    Returns ``(row, country_corrected)``. ``country_corrected`` is True when the
    caller supplied a country that did not match, but a same-name row exists
    under another country (UI should switch the country selector).
    """
    wanted_country = (country or "").strip()
    wanted_name = (name or "").strip()
    if not wanted_name:
        return None, False
    if wanted_country:
        scoped = _find_existing(wanted_country, wanted_name, lang)
        if scoped is not None:
            return scoped, False
    global_hit = _find_existing_by_name(wanted_name, lang)
    if global_hit is None:
        return None, False
    found_country = (global_hit.get("country") or "").strip()
    corrected = bool(wanted_country and found_country and found_country != wanted_country)
    return global_hit, corrected


def name_script_supported(name: str) -> bool:
    """True when dish name uses only zh / en (Latin) / ja / ko letter scripts.

    Digits, spaces, and punctuation are ignored. Any other letter script
    (Cyrillic, Arabic, Thai, Devanagari, …) soft-fails create/search-and-create.
    """
    text = (name or "").strip()
    if not text:
        return False
    saw_letter = False
    for ch in text:
        if ch.isspace() or ch.isdigit():
            continue
        code = ord(ch)
        if code < 0x80 and not ch.isalpha():
            continue
        if 0x2000 <= code <= 0x206F:
            continue
        if 0x3000 <= code <= 0x303F:
            continue
        if 0xFF00 <= code <= 0xFFEF:
            if 0xFF21 <= code <= 0xFF3A or 0xFF41 <= code <= 0xFF5A:
                saw_letter = True
                continue
            if not (0xFF10 <= code <= 0xFF19):
                if not ch.isalpha() and not ("\u4e00" <= ch <= "\u9fff"):
                    continue
        if ("A" <= ch <= "Z") or ("a" <= ch <= "z") or (0x00C0 <= code <= 0x024F):
            saw_letter = True
            continue
        if "\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf":
            saw_letter = True
            continue
        if "\u3040" <= ch <= "\u30ff" or "\u31f0" <= ch <= "\u31ff":
            saw_letter = True
            continue
        if "\uac00" <= ch <= "\ud7af" or "\u1100" <= ch <= "\u11ff":
            saw_letter = True
            continue
        if _unicode_letter_category(ch):
            return False
    return saw_letter or bool(text)


def _unicode_letter_category(ch: str) -> bool:
    try:
        import unicodedata

        return unicodedata.category(ch).startswith("L")
    except Exception:
        return ch.isalpha()


def _row_needs_fill(row: dict) -> bool:
    """True when C–K style fields are still blank (e.g. prior failed/partial create)."""
    if not (row.get("recipe") or "").strip():
        return True
    if not (row.get("method") or "").strip():
        return True
    # Foreign names (C–E) all blank while a Chinese title exists.
    if (row.get("name_zh") or "").strip() and not any(
        (row.get(key) or "").strip() for key in ("name_en", "name_ja", "name_ko")
    ):
        return True
    # Enrichment columns H/J blank even though ingredients exist.
    if (row.get("recipe") or "").strip():
        if not (row.get("benefit") or "").strip():
            return True
        if not (row.get("nutrient") or "").strip():
            return True
    return False


def _merge_fill_fields(existing: dict, fields: dict[str, str]) -> dict[str, str]:
    """Keep any non-empty existing cells; fill blanks from research."""
    merged = dict(fields)
    for key in (
        "country",
        "name_zh",
        "name_en",
        "name_ja",
        "name_ko",
        "recipe",
        "method",
        "benefit",
        "ban",
        "nutrient",
        "allergens",
    ):
        old = str(existing.get(key) or "").strip()
        new = str(merged.get(key) or "").strip()
        if old and not new:
            merged[key] = old
        elif old and new and key.startswith("name_") and old == existing.get("name_zh"):
            # Prefer researched foreign names over echoing the Chinese title.
            merged[key] = new or old
        elif not new and old:
            merged[key] = old
    merged["country"] = fields.get("country") or existing.get("country") or ""
    return merged


def _find_existing(country: str, name: str, lang: str) -> dict[str, str] | None:
    needle = name.casefold()
    name_field = NAME_FIELDS.get(lang, "name_zh")
    for row in recipe_rows():
        if (row.get("country") or "") != country:
            continue
        candidates = [
            row.get(name_field) or "",
            row.get("name_zh") or "",
            row.get("name_en") or "",
            row.get("name_ja") or "",
            row.get("name_ko") or "",
            localized_name(row, lang),
        ]
        for label in candidates:
            if label and label.strip().casefold() == needle:
                return row
    return None


def _normalize_dish_key(name: str) -> str:
    """Casefold + unify common noodle/script variants for fuzzy catalog match."""
    text = (name or "").strip().casefold()
    if not text:
        return ""
    # Traditional/simplified / JP noodle variants and whitespace noise.
    for src, dst in (
        ("麵", "面"),
        ("麺", "面"),
        ("鷄", "雞"),
        ("鶏", "雞"),
        (" ", ""),
        ("\u3000", ""),
        ("·", ""),
        ("・", ""),
    ):
        text = text.replace(src, dst)
    return text


def _name_lookup_candidates(name: str) -> list[str]:
    """Exact typed form plus normalized noodle-script variants for SQL/XLS lookup."""
    raw = (name or "").strip()
    if not raw:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for candidate in (
        raw,
        raw.replace("面", "麵").replace("麺", "麵"),
        raw.replace("麵", "面").replace("麺", "面"),
        raw.replace("麵", "麺").replace("面", "麺"),
    ):
        key = candidate.strip()
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _score_name_row(
    row: dict[str, str], needle: str, needle_norm: str, name_field: str
) -> tuple | None:
    labels = {
        "lang": (row.get(name_field) or "").strip().casefold(),
        "zh": (row.get("name_zh") or "").strip().casefold(),
        "en": (row.get("name_en") or "").strip().casefold(),
        "ja": (row.get("name_ja") or "").strip().casefold(),
        "ko": (row.get("name_ko") or "").strip().casefold(),
    }
    norms = {key: _normalize_dish_key(val) for key, val in labels.items() if val}
    exact = any(label == needle for label in labels.values() if label)
    fuzzy = bool(needle_norm) and any(val == needle_norm for val in norms.values())
    if not exact and not fuzzy:
        return None
    return (
        0 if exact else 1,
        0 if labels.get("lang") == needle or norms.get("lang") == needle_norm else 1,
        0 if labels.get("zh") == needle or norms.get("zh") == needle_norm else 1,
        0 if labels.get("en") == needle or norms.get("en") == needle_norm else 1,
        0
        if labels.get("ja") == needle
        or labels.get("ko") == needle
        or norms.get("ja") == needle_norm
        or norms.get("ko") == needle_norm
        else 1,
        0 if (row.get("recipe") or "").strip() else 1,
        0 if (row.get("method") or "").strip() else 1,
        row.get("country") or "",
        str(row.get("id") or ""),
    )


def _find_existing_by_name(name: str, lang: str) -> dict[str, str] | None:
    """Global zh/en/ja/ko name match (exact, then noodle-script fuzzy).

    Prefers MySQL name query, then full catalog scan. Ranking prefers an exact hit
    on the UI language column, then name_zh, then other name_* columns — so a
    polluted foreign-name cell does not beat the real dish.
    """
    needle = (name or "").strip().casefold()
    if not needle:
        return None
    needle_norm = _normalize_dish_key(name)
    name_field = NAME_FIELDS.get(lang, "name_zh")
    scored: list[tuple[tuple, dict[str, str]]] = []
    seen_ids: set[str] = set()

    def consider(row: dict[str, str]) -> None:
        rid = str(row.get("id") or "")
        if rid and rid in seen_ids:
            return
        rank = _score_name_row(row, needle, needle_norm, name_field)
        if rank is None:
            return
        if rid:
            seen_ids.add(rid)
        scored.append((rank, row))

    # Fast path: exact (+ script-variant) SQL hits across countries.
    try:
        from .shared_catalog import fetch_recipe_rows_by_names

        mysql_hits = fetch_recipe_rows_by_names(_name_lookup_candidates(name))
        if mysql_hits:
            for row in mysql_hits:
                consider(row)
    except Exception:
        pass

    if not scored:
        for row in recipe_rows():
            consider(row)

    if not scored:
        return None
    scored.sort(key=lambda item: item[0])
    return scored[0][1]


# Well-known dishes → Recipe.xls country spelling (fallback before Global).
_DISH_COUNTRY_HINTS: dict[str, str] = {
    "蛋餅": "Taiwan",
    "台式蛋餅": "Taiwan",
    "danbing": "Taiwan",
    "dan bing": "Taiwan",
    "滷肉飯": "Taiwan",
    "魯肉飯": "Taiwan",
    "牛肉麵": "Taiwan",
    "臭豆腐": "Taiwan",
    "刈包": "Taiwan",
    "珍珠奶茶": "Taiwan",
    "壽司": "Japan",
    "寿司": "Japan",
    "sushi": "Japan",
    "拉麵": "Japan",
    "ラーメン": "Japan",
    "ramen": "Japan",
    "泡菜": "Korea",
    "김치": "Korea",
    "kimchi": "Korea",
    "韓式拌飯": "Korea",
    "비빔밥": "Korea",
    "pizza": "Italy",
    "披薩": "Italy",
    "pasta": "Italy",
    "義大利麵": "Italy",
    "hamburger": "United States",
    "漢堡": "United States",
}

_COUNTRY_TEXT_HINTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"Taiwan(?:ese)?|台灣|臺灣|台湾|台式", re.I), "Taiwan"),
    (re.compile(r"Japan(?:ese)?|日本|和食|寿司|壽司", re.I), "Japan"),
    (re.compile(r"Korea(?:n)?|韓國|韩国|韓式|한식", re.I), "Korea"),
    (re.compile(r"China|Chinese|中國|中国|中式", re.I), "China"),
    (re.compile(r"Italy|Italian|義大利|意大利|義式", re.I), "Italy"),
    (re.compile(r"France|French|法國|法国|法式", re.I), "France"),
    (re.compile(r"Thailand|Thai|泰國|泰国|泰式", re.I), "Thailand"),
    (re.compile(r"India(?:n)?|印度", re.I), "India"),
    (re.compile(r"United States|American|美國|美国", re.I), "United States"),
    (re.compile(r"Vietnam(?:ese)?|越南", re.I), "Vietnam"),
    (re.compile(r"Mexico|Mexican|墨西哥", re.I), "Mexico"),
)


def _country_hint_for_name(name: str) -> str:
    key = (name or "").strip().casefold()
    if not key:
        return ""
    for dish, country in _DISH_COUNTRY_HINTS.items():
        if dish.casefold() == key:
            return country
    return ""


def _infer_country_from_text(blob: str, name: str = "") -> str:
    hint = _country_hint_for_name(name)
    if hint:
        return hint
    text = blob or ""
    if not text.strip():
        return ""
    for pattern, country in _COUNTRY_TEXT_HINTS:
        if pattern.search(text):
            return country
    return ""


def build_row_fields(
    country: str,
    name: str,
    lang: str,
    research: dict,
) -> dict[str, str]:
    names = {
        "name_zh": str(research.get("name_zh") or (name if lang == "zh" else "")).strip(),
        "name_en": str(research.get("name_en") or (name if lang == "en" else "")).strip(),
        "name_ja": str(research.get("name_ja") or (name if lang == "ja" else "")).strip(),
        "name_ko": str(research.get("name_ko") or (name if lang == "ko" else "")).strip(),
    }
    if not names["name_zh"] and lang == "zh":
        names["name_zh"] = name
    if not any(names.values()):
        names[NAME_FIELDS.get(lang, "name_zh")] = name

    ingredients = research.get("ingredients") or []
    if isinstance(ingredients, str):
        recipe_text = ingredients.strip()
        pairs = parse_ingredient_text(recipe_text)
    else:
        pairs = [(str(n).strip(), int(g)) for n, g in ingredients if str(n).strip()]
        recipe_text = format_ingredients(pairs) if pairs else ""

    allergens = str(research.get("allergens") or "").strip()
    if not allergens and pairs:
        allergens = "、".join(n for n, _g in pairs if n in ALLERGEN_FOODS)

    return {
        "country": country,
        "name_zh": names["name_zh"],
        "name_en": names["name_en"],
        "name_ja": names["name_ja"],
        "name_ko": names["name_ko"],
        "recipe": recipe_text,
        "method": str(research.get("method") or "").strip(),
        "benefit": str(research.get("benefit") or "").strip(),
        "ban": str(research.get("ban") or "").strip(),
        "nutrient": str(research.get("nutrient") or "").strip(),
        "allergens": allergens,
    }


def _is_partial(fields: dict[str, str]) -> bool:
    return not (fields.get("recipe") and fields.get("method"))


def format_ingredients(pairs: list[tuple[str, int]]) -> str:
    return "、".join(f"{name} {gram}克" for name, gram in pairs)


def parse_ingredient_text(text: str) -> list[tuple[str, int]]:
    pairs: list[tuple[str, int]] = []
    for part in (text or "").split("、"):
        piece = part.strip()
        if not piece:
            continue
        match = _ING_RE.match(piece)
        if not match:
            continue
        try:
            gram = int(round(float(match.group(2))))
        except ValueError:
            continue
        if gram > 0:
            pairs.append((match.group(1).strip(), gram))
    return pairs


def research_dish(country: str, name: str, lang: str) -> dict:
    """Best-effort Wikipedia research. Soft-fail per request; prefer country-specific pages."""
    snippets: list[str] = []
    titles: dict[str, str] = {}
    network_errors = 0
    chosen_title = ""
    chosen_lang = ""
    # When country is blank, still bias seeds/queries with a dish hint if known.
    effective_country = (country or "").strip() or _country_hint_for_name(name) or ""

    for wiki_lang in _wiki_langs(lang):
        hits: list[str] = []
        for seed in _seed_titles(effective_country, name, wiki_lang):
            if seed not in hits:
                hits.append(seed)
        for query in _search_queries(effective_country, name, wiki_lang, lang):
            try:
                found = _wiki_search(query, wiki_lang)
            except TimeoutError:
                network_errors += 1
                continue
            except Exception:
                network_errors += 1
                continue
            for title in found:
                if title and title not in hits and not _is_overview_title(title, name):
                    hits.append(title)
            # Keep gathering a few queries when the first only returns weak overview hits.
            if any(_dish_title_score(t, effective_country, name) >= 20 for t in hits):
                break
        hits = _rank_wiki_hits(hits, effective_country, name)
        for title in hits[:4]:
            if _is_overview_title(title, name):
                continue
            try:
                extract = _wiki_extract(title, wiki_lang)
                summary = {}
                if not extract:
                    summary = _wiki_summary(title, wiki_lang)
            except TimeoutError:
                network_errors += 1
                continue
            except Exception:
                network_errors += 1
                continue
            if not extract:
                extract = str((summary or {}).get("extract") or "").strip()
            display = str((summary or {}).get("title") or title).strip()
            if extract and _extract_seems_relevant(extract, name, title):
                snippets.append(extract)
                if not chosen_title:
                    chosen_title = title
                    chosen_lang = wiki_lang
                if display and wiki_lang not in titles:
                    titles[wiki_lang] = display
                break
        if snippets:
            break

    # Multilingual names via langlinks from the best dish page only.
    if chosen_title and chosen_lang:
        try:
            for link_lang, link_title in _wiki_langlinks(chosen_title, chosen_lang).items():
                if link_lang in ("zh", "en", "ja", "ko") and link_title and not _is_overview_title(link_title, name):
                    titles.setdefault(link_lang, link_title)
        except Exception:
            pass
        if chosen_lang == "zh" and titles.get("en"):
            try:
                en_extract = _wiki_extract(titles["en"], "en")
                if en_extract and _extract_seems_relevant(en_extract, name, titles["en"]):
                    snippets.append(en_extract)
            except Exception:
                pass

    names = {
        "name_zh": titles.get("zh", ""),
        "name_en": titles.get("en", ""),
        "name_ja": titles.get("ja", ""),
        "name_ko": titles.get("ko", ""),
    }
    if lang == "zh" or _looks_cjk(name):
        names["name_zh"] = name
    if lang == "zh":
        names["name_zh"] = name
    if lang == "en" and not names["name_en"]:
        names["name_en"] = name
    elif lang == "ja" and not names["name_ja"]:
        names["name_ja"] = name
    elif lang == "ko" and not names["name_ko"]:
        names["name_ko"] = name
    for key in ("name_en", "name_ja", "name_ko"):
        if _is_overview_title(names.get(key) or "", name):
            names[key] = ""
    names = _polish_multilingual_names(effective_country, name, names)
    blob_preview = "\n".join(snippets)
    inferred_country = (
        (country or "").strip()
        or _infer_country_from_text(f"{chosen_title}\n{blob_preview}", name)
        or effective_country
        or "Global"
    )

    if not snippets and network_errors and not titles:
        fallback = _teaching_fallback(inferred_country, name, names)
        if fallback:
            fallback["country"] = inferred_country
            return fallback
        raise TimeoutError("網路搜尋逾時或失敗")

    blob = "\n".join(snippets)
    food_index = load_food_name_index()
    primary = _primary_research_blob(snippets[0] if snippets else "")
    pairs = extract_ingredients_from_text(primary, food_index)
    if len(pairs) < 3:
        pairs = extract_ingredients_from_text(_primary_research_blob(blob), food_index)
    pairs = _augment_cooking_fat(pairs, blob)
    if not pairs:
        fallback = _teaching_fallback(inferred_country, name, names)
        if fallback:
            fallback["country"] = inferred_country
            return fallback
        recipe_text = ""
        method = ""
        partial = True
    else:
        if sum(g for _n, g in pairs) != 500:
            pairs = _normalize_grams(pairs, total=500)
        recipe_text = format_ingredients(pairs)
        method = _method_from_extract(snippets[0] if snippets else blob, pairs) or _simple_method(pairs)
        partial = False

    source_bit = (snippets[0][:180] + "…") if snippets else ""
    if source_bit and not method:
        method = f"參考公開資料摘要：{source_bit}"
        partial = True

    return {
        **names,
        "country": inferred_country,
        "ingredients": recipe_text,
        "method": method,
        "benefit": "",
        "ban": "",
        "nutrient": "",
        "allergens": "、".join(n for n, _g in pairs if n in ALLERGEN_FOODS) if pairs else "",
        "partial": partial,
        "source": source_bit,
    }


def _seed_titles(country: str, name: str, wiki_lang: str) -> list[str]:
    """Known good Wikipedia titles to try before search (Taiwan breakfast dishes etc.)."""
    country_cf = (country or "").casefold()
    name = (name or "").strip()
    seeds: list[str] = []
    if wiki_lang == "zh":
        if country_cf == "taiwan":
            seeds.append(f"台式{name}")
            if name == "蛋餅":
                seeds.extend(["台式蛋餅", "蛋餅"])
        seeds.append(name)
    elif wiki_lang == "en":
        if country_cf == "taiwan" and name in ("蛋餅", "台式蛋餅"):
            seeds.extend(["Danbing", "Taiwanese egg crepe"])
        seeds.append(name)
    elif wiki_lang == "ja" and name == "蛋餅":
        seeds.append("蛋餅")
    elif wiki_lang == "ko" and name == "蛋餅":
        seeds.append("단빙")
    return seeds


def _is_overview_title(title: str, dish_name: str) -> bool:
    t = (title or "").strip()
    if not t:
        return True
    dish = (dish_name or "").strip()
    if dish and (t == dish or dish in t or t in dish):
        return False
    markers = (
        "料理", "菜系", "菜餚", "菜肴", "美食", "飲食", "cuisine", "food culture",
        "List of", "列表", "一覽", "一览",
    )
    lower = t.casefold()
    if any(m.casefold() in lower for m in markers):
        # Allow titles that still clearly name the dish (e.g. "蛋餅 (台灣料理)").
        if dish and dish.casefold() in lower:
            return False
        return True
    return False


def _dish_title_score(title: str, country: str, name: str) -> int:
    t = title or ""
    name = (name or "").strip()
    country_cf = (country or "").casefold()
    s = 0
    if t == name:
        s += 20
    if name and name in t:
        s += 10
    if country_cf == "taiwan" and ("台式" in t or "台灣" in t or "台湾" in t or "Taiwan" in t):
        s += 30
    if country_cf == "taiwan" and name in ("蛋餅", "台式蛋餅") and t in ("台式蛋餅", "Danbing", "danbing", "蛋餅"):
        s += 40
    if t == "蛋餅" and country_cf == "taiwan":
        s -= 5
    if _is_overview_title(t, name):
        s -= 50
    return s


def _extract_seems_relevant(extract: str, name: str, title: str) -> bool:
    if _is_overview_title(title, name):
        return False
    blob = extract or ""
    dish = (name or "").strip()
    if not dish:
        return bool(blob)
    if dish in title or dish in blob[:400]:
        return True
    # Romanized / foreign title pages (Danbing) that mention egg pancake.
    markers = ("egg pancake", "danbing", "dan bing", "早餐", "breakfast")
    lower = blob[:500].casefold()
    return any(m in lower for m in markers)


def _looks_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def _search_queries(country: str, name: str, wiki_lang: str, ui_lang: str) -> list[str]:
    country = (country or "").strip()
    name = (name or "").strip()
    queries: list[str] = []

    def add(q: str) -> None:
        q = (q or "").strip()
        if q and q not in queries:
            queries.append(q)

    if wiki_lang == "zh":
        if country.casefold() == "taiwan":
            add(f"台式{name}")
            add(f"{name} 台灣 早餐")
            add(f"台灣 {name}")
        add(name)
        add(f"{country} {name}")
        add(f"{country} {name} 食譜")
        add(f"{name} 食譜")
    elif wiki_lang == "en":
        add(name)
        if country.casefold() == "taiwan":
            add(f"Taiwanese {name}")
            add(f"{name} Taiwan breakfast")
            # Common romanization for 蛋餅
            if name in ("蛋餅", "台式蛋餅"):
                add("danbing")
                add("dan bing")
                add("Taiwanese egg pancake")
        add(f"{name} {country}")
        add(f"{name} {country} recipe")
    else:
        add(name)
        add(f"{country} {name}")
    if ui_lang == "zh" and wiki_lang != "zh":
        add(name)
    return queries


def _rank_wiki_hits(hits: list[str], country: str, name: str) -> list[str]:
    if not hits:
        return []
    return sorted(hits, key=lambda t: (-_dish_title_score(t, country, name), len(t or "")))


def _wiki_langs(lang: str) -> tuple[str, ...]:
    primary = normalize_lang(lang)
    order = [primary]
    for extra in ("zh", "en", "ja", "ko"):
        if extra not in order:
            order.append(extra)
    return tuple(order)


def _http_json(url: str, timeout: float = SEARCH_TIMEOUT_SEC) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {}
        if exc.code >= 500:
            raise TimeoutError("網路搜尋逾時或失敗") from exc
        raise
    except TimeoutError as exc:
        raise TimeoutError("網路搜尋逾時或失敗") from exc
    except Exception as exc:
        raise TimeoutError("網路搜尋逾時或失敗") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("網路搜尋回應無法解析") from exc
    return data if isinstance(data, dict) else {}


def _wiki_search(query: str, wiki_lang: str) -> list[str]:
    params = urllib.parse.urlencode(
        {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": 8,
            "format": "json",
            "utf8": 1,
        }
    )
    url = f"https://{wiki_lang}.wikipedia.org/w/api.php?{params}"
    data = _http_json(url)
    hits = (((data.get("query") or {}).get("search")) or [])
    return [str(item.get("title") or "").strip() for item in hits if item.get("title")]


def _wiki_summary(title: str, wiki_lang: str) -> dict:
    encoded = urllib.parse.quote(title.replace(" ", "_"), safe="")
    url = f"https://{wiki_lang}.wikipedia.org/api/rest_v1/page/summary/{encoded}"
    data = _http_json(url)
    return data


def _wiki_extract(title: str, wiki_lang: str) -> str:
    """Plain-text extract (full intro+body truncated by API), richer than REST summary."""
    params = urllib.parse.urlencode(
        {
            "action": "query",
            "prop": "extracts",
            "exintro": 0,
            "explaintext": 1,
            "redirects": 1,
            "titles": title,
            "format": "json",
            "utf8": 1,
        }
    )
    url = f"https://{wiki_lang}.wikipedia.org/w/api.php?{params}"
    data = _http_json(url)
    pages = ((data.get("query") or {}).get("pages")) or {}
    for page in pages.values():
        extract = str(page.get("extract") or "").strip()
        if extract:
            return extract[:4000]
    return ""


def _wiki_langlinks(title: str, wiki_lang: str) -> dict[str, str]:
    params = urllib.parse.urlencode(
        {
            "action": "query",
            "prop": "langlinks",
            "lllimit": 40,
            "redirects": 1,
            "titles": title,
            "format": "json",
            "utf8": 1,
        }
    )
    url = f"https://{wiki_lang}.wikipedia.org/w/api.php?{params}"
    data = _http_json(url)
    pages = ((data.get("query") or {}).get("pages")) or {}
    out: dict[str, str] = {}
    for page in pages.values():
        for link in page.get("langlinks") or []:
            lang = str(link.get("lang") or "").strip()
            label = str(link.get("*") or "").strip()
            if lang and label:
                out[lang] = label
    return out


def load_food_name_index() -> dict[str, dict[str, str]]:
    """Map 食材中文 / other language names -> food row fields."""
    try:
        from .shared_catalog import fetch_foods_index

        mysql_foods = fetch_foods_index()
        if mysql_foods is not None:
            return mysql_foods
    except Exception:
        pass
    import xlrd

    if not FOODS_PATH.exists():
        raise FileNotFoundError(str(FOODS_PATH))
    sheet = xlrd.open_workbook(str(FOODS_PATH)).sheet_by_index(0)
    headers = [str(sheet.cell_value(0, col)).strip() for col in range(min(sheet.ncols, 7))]
    index = {name: pos for pos, name in enumerate(headers)}

    def cell(row: int, header: str) -> str:
        col = index.get(header)
        if col is None:
            return ""
        return str(sheet.cell_value(row, col)).strip()

    foods: dict[str, dict[str, str]] = {}
    for row in range(1, sheet.nrows):
        zh = cell(row, "食材中文")
        if not zh:
            continue
        item = {
            "name_zh": zh,
            "name_en": cell(row, "食材英文"),
            "name_ja": cell(row, "食材日文"),
            "name_ko": cell(row, "食材韓文"),
            "benefit": cell(row, "益處"),
            "ban": cell(row, "禁忌"),
            "nutrient": cell(row, "元素表"),
        }
        foods[zh] = item
        for key in ("name_en", "name_ja", "name_ko"):
            alias = item[key]
            if alias and alias not in foods:
                foods[alias] = item
    return foods


def _normalize_research_text(text: str) -> str:
    cleaned = _TAG_RE.sub(" ", unescape(text or ""))
    cleaned = _WS_RE.sub(" ", cleaned)
    # Longer ASCII phrases first; use word boundaries so "egg" does not hit "eggplant".
    ascii_rules = sorted(
        ((src, dst) for src, dst in _TEXT_REPLACEMENTS if src.isascii()),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    for src, dst in ascii_rules:
        cleaned = re.sub(rf"\b{re.escape(src)}\b", dst, cleaned, flags=re.IGNORECASE)
    for src, dst in _TEXT_REPLACEMENTS:
        if not src.isascii() and src in cleaned:
            cleaned = cleaned.replace(src, dst)
    cleaned = _SALT_RE.sub("食鹽", cleaned)
    return cleaned


def _primary_research_blob(text: str) -> str:
    """Keep the core description; drop optional-topping / sauce tails."""
    blob = (text or "").strip()
    if not blob:
        return ""
    cut_at = len(blob)
    for marker in ("有時候", "有时侯", "有时", "sometimes", "optional toppings", "optional:"):
        if marker.isascii():
            idx = blob.casefold().find(marker.casefold())
        else:
            idx = blob.find(marker)
        if 40 <= idx < cut_at:
            cut_at = idx
    return blob[:cut_at].strip()


def _cjk_hit_ok(text: str, start: int, name: str) -> bool:
    """Reject sauce compounds like 番茄醬 / 辣椒醬 unless the food itself ends with 醬."""
    end = start + len(name)
    if end < len(text) and text[end] == "醬" and not name.endswith("醬"):
        return False
    return True


def extract_ingredients_from_text(
    text: str,
    food_index: dict[str, dict[str, str]],
) -> list[tuple[str, int]]:
    """Pick known Foods.xls names that appear in fetched text (longest-first, position-ordered)."""
    if not text:
        return []
    cleaned = _normalize_research_text(text)
    alias_to_zh: dict[str, str] = {}
    for item in food_index.values():
        zh = (item.get("name_zh") or "").strip()
        if not zh:
            continue
        alias_to_zh[zh] = zh
        for key in ("name_en", "name_ja", "name_ko"):
            alias = (item.get(key) or "").strip()
            if alias:
                alias_to_zh.setdefault(alias, zh)
    names = sorted(alias_to_zh.keys(), key=len, reverse=True)
    masked = cleaned
    hits: list[tuple[int, str]] = []
    seen_zh: set[str] = set()
    for name in names:
        zh = alias_to_zh[name]
        # Allow canonical 1-char Foods.xls names (蔥/蝦/茶…); skip other short aliases.
        if len(name) < 2 and name != zh:
            continue
        if zh in seen_zh:
            continue
        if name.isascii():
            if len(name) < 3:
                continue
            match = re.search(rf"(?<![A-Za-z]){re.escape(name)}(?![A-Za-z])", masked, flags=re.IGNORECASE)
            if not match:
                continue
            pos = match.start()
            masked = masked[:pos] + (" " * (match.end() - pos)) + masked[match.end():]
        else:
            pos = masked.find(name)
            if pos < 0:
                continue
            if not _cjk_hit_ok(masked, pos, name):
                continue
            masked = masked[:pos] + (" " * len(name)) + masked[pos + len(name):]
        hits.append((pos, zh))
        seen_zh.add(zh)
        if len(hits) >= 12:
            break
    if not hits:
        return []
    hits.sort(key=lambda item: item[0])
    found = [zh for _pos, zh in hits[:8]]
    return _balanced_ingredient_grams(found, total=500)


_SEASONING_GRAMS = {
    "食鹽": 8,
    "鹽": 8,
    "醬油": 25,
    "麻油": 20,
    "花生油": 35,
    "醋": 15,
    "胡椒": 3,
    "糖": 10,
}


def _balanced_ingredient_grams(names: list[str], total: int = 500) -> list[tuple[str, int]]:
    """Assign small fixed grams to seasonings; split the rest across bulk foods."""
    if not names:
        return []
    fixed: dict[str, int] = {}
    bulk: list[str] = []
    for name in names:
        if name in _SEASONING_GRAMS:
            fixed[name] = _SEASONING_GRAMS[name]
        else:
            bulk.append(name)
    fixed_total = sum(fixed.values())
    remain = max(len(bulk), total - fixed_total)
    if not bulk:
        # Only seasonings found — fall back to equal split.
        base = total // len(names)
        rem = total - base * len(names)
        return [(name, base + (1 if i < rem else 0)) for i, name in enumerate(names)]
    base = remain // len(bulk)
    rem = remain - base * len(bulk)
    pairs: list[tuple[str, int]] = []
    bulk_i = 0
    for name in names:
        if name in fixed:
            pairs.append((name, fixed[name]))
        else:
            pairs.append((name, base + (1 if bulk_i < rem else 0)))
            bulk_i += 1
    # Keep teaching total near 500g.
    drift = total - sum(g for _n, g in pairs)
    if pairs and drift:
        # Adjust the largest bulk item.
        idx = max(range(len(pairs)), key=lambda i: pairs[i][1] if pairs[i][0] not in fixed else -1)
        name, gram = pairs[idx]
        pairs[idx] = (name, max(1, gram + drift))
    return pairs


def _augment_cooking_fat(
    pairs: list[tuple[str, int]],
    blob: str,
) -> list[tuple[str, int]]:
    if not pairs:
        return pairs
    oils = {"花生油", "麻油", "豬油", "奶油"}
    if any(name in oils for name, _g in pairs):
        return pairs
    markers = ("煎", "炒", "油炸", "fry", "pan-fry", "griddle")
    raw = blob or ""
    lower = raw.casefold()
    if not any((m.casefold() in lower) if m.isascii() else (m in raw) for m in markers):
        return pairs
    names = [name for name, _gram in pairs] + ["花生油"]
    return _balanced_ingredient_grams(names, total=500)


def _polish_multilingual_names(country: str, name: str, names: dict[str, str]) -> dict[str, str]:
    out = dict(names)
    country_cf = (country or "").casefold()
    dish = (name or "").strip()
    if country_cf == "taiwan" and dish in ("蛋餅", "台式蛋餅"):
        en = (out.get("name_en") or "").strip()
        if not en or en == dish or en == "Danbing":
            out["name_en"] = "Danbing (egg pancake)"
        ja = (out.get("name_ja") or "").strip()
        if not ja or ja == dish:
            out["name_ja"] = "台湾風卵餅"
        ko = (out.get("name_ko") or "").strip()
        if not ko or ko == dish:
            out["name_ko"] = "단빙"
    return out


def _teaching_fallback(country: str, name: str, titles: dict[str, str] | None = None) -> dict | None:
    """Minimal durable row when public pages lack parseable ingredients."""
    country_cf = (country or "").casefold()
    dish = (name or "").strip()
    titles = titles or {}
    if country_cf == "taiwan" and dish in ("蛋餅", "台式蛋餅"):
        pairs = _normalize_grams(
            [
                ("雞蛋", 150),
                ("小麥", 150),
                ("蔥", 40),
                ("韭菜", 40),
                ("食鹽", 10),
                ("花生油", 60),
                ("火腿", 50),
            ],
            total=500,
        )
        names = _polish_multilingual_names(
            country,
            dish,
            {
                "name_zh": dish,
                "name_en": titles.get("name_en") or titles.get("en") or "",
                "name_ja": titles.get("name_ja") or titles.get("ja") or "",
                "name_ko": titles.get("name_ko") or titles.get("ko") or "",
            },
        )
        return {
            **names,
            "country": country or "Global",
            "ingredients": format_ingredients(pairs),
            "method": _simple_method(pairs),
            "benefit": "",
            "ban": "",
            "nutrient": "",
            "allergens": "、".join(n for n, _g in pairs if n in ALLERGEN_FOODS),
            "partial": False,
            "source": "教學備援（公開頁缺少可對應食材表之描述）",
        }
    return None

def _normalize_grams(pairs: list[tuple[str, int]], total: int = 500) -> list[tuple[str, int]]:
    if not pairs:
        return []
    current = sum(g for _n, g in pairs)
    if current == total:
        return pairs
    if current <= 0:
        base = total // len(pairs)
        rem = total - base * len(pairs)
        return [(n, base + (1 if i < rem else 0)) for i, (n, _g) in enumerate(pairs)]
    scaled = [(n, max(1, int(round(g * total / current)))) for n, g in pairs]
    drift = total - sum(g for _n, g in scaled)
    if scaled:
        name, gram = scaled[-1]
        scaled[-1] = (name, max(1, gram + drift))
    return scaled


def _method_from_extract(blob: str, pairs: list[tuple[str, int]]) -> str:
    if not blob:
        return ""
    # Keep a short cooking-oriented slice if the extract mentions preparation words.
    markers = ("作法", "做法", "煮法", "烹調", "烹调", "煎", "炒", "拌", "蒸", "煮", "prepare", "cook", "method", "dough", "batter")
    lower = blob.lower()
    if not any(m.lower() in lower or m in blob for m in markers):
        return ""
    short = blob.strip()
    if len(short) > 400:
        short = short[:400].rstrip() + "…"
    names = "、".join(n for n, _g in pairs[:6])
    return f"依公開資料整理：準備{names}等材料。{short}"


def _simple_method(pairs: list[tuple[str, int]]) -> str:
    names = "、".join(f"{n}{g}克" for n, g in pairs)
    return f"洗淨備料（{names}），依常法加熱至熟透後調味盛盤。教學示範煮法，請依實際食材調整。"


def enrich_from_foods(fields: dict[str, str]) -> dict[str, str]:
    """Fill nutrient/allergens from Foods.xls; write plain 益處／禁忌 from top-4 ingredients."""
    from .recipes import invalidate_foods_cache, simplify_organ_effects

    pairs = parse_ingredient_text(fields.get("recipe") or "")
    if not pairs:
        return fields
    try:
        foods = load_food_name_index()
    except FileNotFoundError:
        return fields

    # Best-effort: fill empty Foods.xls effect tags before translating to Recipe.xls.
    foods = ensure_food_effect_tags(pairs, foods)

    nutrient_parts: list[str] = []
    for name, _gram in pairs:
        item = foods.get(name)
        if not item:
            continue
        if item.get("nutrient"):
            nutrient_parts.append(f"{name}:{item['nutrient']}")
    if nutrient_parts and not fields.get("nutrient"):
        fields["nutrient"] = ";".join(nutrient_parts)
    if not fields.get("allergens"):
        fields["allergens"] = "、".join(n for n, _g in pairs if n in ALLERGEN_FOODS)

    plain_benefit, plain_ban = simplify_organ_effects(
        {"recipe": fields.get("recipe") or "", "benefit": "", "ban": ""},
        foods=foods,
    )
    if plain_benefit:
        fields["benefit"] = plain_benefit
    if plain_ban:
        fields["ban"] = plain_ban
    invalidate_foods_cache()
    return fields


def ensure_food_effect_tags(
    pairs: list[tuple[str, int]],
    foods: dict[str, dict[str, str]] | None = None,
    *,
    use_wiki: bool = True,
) -> dict[str, dict[str, str]]:
    """Ensure Foods.xls rows for recipe ingredients have 益處／禁忌 tags (guess + optional wiki)."""
    index = dict(foods or load_food_name_index())
    # Only invent tags when BOTH 益處 and 禁忌 are blank (avoid polluting half-filled Foods.xls rows).
    missing: list[str] = []
    for name, _gram in pairs:
        item = index.get(name)
        if not item:
            continue
        has_benefit = bool((item.get("benefit") or "").strip())
        has_ban = bool((item.get("ban") or "").strip())
        if has_benefit or has_ban:
            continue
        missing.append(name)
    # Unique preserve order
    seen: set[str] = set()
    todo = []
    for name in missing:
        if name in seen:
            continue
        seen.add(name)
        todo.append(name)
    if not todo:
        return index

    updates: dict[str, dict[str, str]] = {}
    for name in todo:
        item = dict(index.get(name) or {"name_zh": name})
        blob = ""
        if use_wiki:
            try:
                blob = _wiki_food_snippet(name)
            except Exception:
                blob = ""
        benefit, ban = _guess_food_effect_tags(name, blob)
        if not (item.get("benefit") or "").strip() and benefit:
            item["benefit"] = benefit
        if not (item.get("ban") or "").strip() and ban:
            item["ban"] = ban
        if blob and not (item.get("nutrient") or "").strip():
            item["nutrient"] = (blob[:160] + "…") if len(blob) > 160 else blob
        # Multilingual names from wiki langlinks when blank.
        if blob:
            names = _guess_food_names(name, blob)
            for key in ("name_en", "name_ja", "name_ko"):
                if not (item.get(key) or "").strip() and names.get(key):
                    item[key] = names[key]
        updates[name] = item
        index[name] = item

    if updates:
        _patch_foods_rows(updates)
    return index


def _wiki_food_snippet(name: str) -> str:
    for wiki_lang in ("zh", "en"):
        try:
            hits = _wiki_search(name, wiki_lang)
        except Exception:
            continue
        for title in hits[:3]:
            try:
                extract = _wiki_extract(title, wiki_lang) or ""
            except Exception:
                extract = ""
            if extract and (name in extract[:200] or name in title or wiki_lang == "en"):
                return extract
    return ""


def _guess_food_names(name: str, blob: str) -> dict[str, str]:
    del blob
    # Lightweight: keep Chinese name; leave foreign blank unless wiki langlinks filled elsewhere.
    return {"name_zh": name}


def _guess_food_effect_tags(name: str, blob: str = "") -> tuple[str, str]:
    """Teaching-demo 證型 tags when Foods.xls is blank (not a clinical oracle)."""
    text = f"{name}\n{blob}"
    lower = text.casefold()
    warm_markers = ("薑", "葱", "蔥", "蒜", "椒", "羊肉", "韭菜", "肉桂", "胡椒", "咖哩", "酒", "fry", "chili", "ginger")
    cool_markers = ("瓜", "梨", "綠豆", "薄荷", "苦瓜", "黃瓜", "西瓜", "茶", "涼", "cold", "cucumber", "melon")
    damp_markers = ("薏", "赤小豆", "紅豆", "冬瓜", "茯苓", "濕", "damp")
    warm = any(m.casefold() in lower if m.isascii() else m in text for m in warm_markers)
    cool = any(m.casefold() in lower if m.isascii() else m in text for m in cool_markers)
    damp = any(m.casefold() in lower if m.isascii() else m in text for m in damp_markers)

    # Default mild spleen/stomach teaching tags.
    if warm and not cool:
        benefit = "脾虛寒,胃虛寒,腎虛寒"
        ban = "脾實熱,胃實熱,心實熱"
    elif cool and not warm:
        benefit = "脾虛熱,胃虛熱,心虛熱"
        ban = "脾實寒,胃實寒,腎虛寒"
    else:
        benefit = "脾虛熱,脾虛寒,胃虛熱,胃虛寒"
        ban = "脾實熱,脾實寒"
    if damp:
        benefit = f"{benefit},濕" if benefit else "濕"
    return benefit, ban


def _patch_foods_rows(updates: dict[str, dict[str, str]]) -> None:
    """Patch Foods catalog (MySQL) then Excel backup for known 食材中文 rows."""
    if not updates:
        return
    try:
        from .shared_catalog import best_effort_export, fetch_foods_index, patch_foods

        index = fetch_foods_index() or {}
        filtered: dict[str, dict[str, str]] = {}
        for zh, item in updates.items():
            existing = index.get(zh) or {}
            patch: dict[str, str] = {}
            for field in ("benefit", "ban", "nutrient", "name_en", "name_ja", "name_ko"):
                new_val = str(item.get(field) or "").strip()
                if not new_val:
                    continue
                if str(existing.get(field) or "").strip():
                    continue
                patch[field] = new_val
            if patch:
                filtered[zh] = patch
        if filtered:
            patch_foods(filtered)
            best_effort_export("foods")
            return
    except Exception:
        logger = __import__("logging").getLogger(__name__)
        logger.exception("MySQL Foods patch failed; falling back to Excel")

    import xlrd
    import xlwt

    if not FOODS_PATH.exists():
        return
    book = xlrd.open_workbook(str(FOODS_PATH))
    sheet = book.sheet_by_index(0)
    headers = [str(sheet.cell_value(0, col)).strip() for col in range(sheet.ncols)]
    if "食材中文" not in headers:
        return
    zh_col = headers.index("食材中文")
    rows = [[_cell(sheet, row, col) for col in range(sheet.ncols)] for row in range(1, sheet.nrows)]
    changed = False
    field_headers = {
        "benefit": "益處",
        "ban": "禁忌",
        "nutrient": "元素表",
        "name_en": "食材英文",
        "name_ja": "食材日文",
        "name_ko": "食材韓文",
    }
    for values in rows:
        zh = str(values[zh_col]).strip() if zh_col < len(values) else ""
        item = updates.get(zh)
        if not item:
            continue
        for field, header in field_headers.items():
            if header not in headers:
                continue
            col = headers.index(header)
            new_val = str(item.get(field) or "").strip()
            if not new_val:
                continue
            old = str(values[col]).strip() if col < len(values) else ""
            if old:
                continue
            if col >= len(values):
                values.extend([""] * (col + 1 - len(values)))
            values[col] = new_val
            changed = True
    if not changed:
        return
    out = xlwt.Workbook(encoding="utf-8")
    out_sheet = out.add_sheet(sheet.name or "食材")
    header_style, cell_style = _xls_styles()
    for col, header in enumerate(headers):
        out_sheet.write(0, col, header, header_style)
        out_sheet.col(col).width = 256 * (28 if col < 4 else 55)
    for row_index, values in enumerate(rows, start=1):
        for col, value in enumerate(values):
            out_sheet.write(row_index, col, value, cell_style)
    _save_xls(out, FOODS_PATH)


def sync_foods_for_ingredients(recipe_text: str) -> list[str]:
    """Append missing ingredient rows to MySQL Foods (+ Excel backup). Returns new 中文 names."""
    pairs = parse_ingredient_text(recipe_text)
    if not pairs:
        return []
    names = [name for name, _gram in pairs]
    try:
        from .shared_catalog import append_missing_foods, best_effort_export

        added = append_missing_foods(names)
        if added:
            best_effort_export("foods")
        return added
    except Exception:
        logger = __import__("logging").getLogger(__name__)
        logger.exception("MySQL Foods append failed; falling back to Excel")

    import xlrd
    import xlwt

    if not FOODS_PATH.exists():
        raise FileNotFoundError(str(FOODS_PATH))

    book = xlrd.open_workbook(str(FOODS_PATH))
    sheet = book.sheet_by_index(0)
    headers = [str(sheet.cell_value(0, col)).strip() for col in range(sheet.ncols)]
    rows: list[list] = []
    existing_zh: set[str] = set()
    zh_col = headers.index("食材中文") if "食材中文" in headers else 0
    for row in range(1, sheet.nrows):
        values = [_cell(sheet, row, col) for col in range(sheet.ncols)]
        rows.append(values)
        zh = str(values[zh_col]).strip() if zh_col < len(values) else ""
        if zh:
            existing_zh.add(zh)

    added: list[str] = []
    width = max(len(headers), len(FOOD_HEADERS))
    for name, _gram in pairs:
        if name in existing_zh:
            continue
        new_row = [""] * width
        mapping = {
            "食材中文": name,
            "食材英文": "",
            "食材日文": "",
            "食材韓文": "",
            "益處": "",
            "禁忌": "",
            "元素表": "網路搜尋待補（教學示範）",
        }
        for col, header in enumerate(headers):
            if header in mapping:
                new_row[col] = mapping[header]
        if "食材中文" not in headers and width >= 1:
            new_row[0] = name
        rows.append(new_row)
        existing_zh.add(name)
        added.append(name)

    if not added:
        return []

    out = xlwt.Workbook(encoding="utf-8")
    out_sheet = out.add_sheet(sheet.name or "食材")
    header_style, cell_style = _xls_styles()
    for col, header in enumerate(headers):
        out_sheet.write(0, col, header, header_style)
        out_sheet.col(col).width = 256 * (28 if col < 4 else 55)
    for row_index, values in enumerate(rows, start=1):
        for col, value in enumerate(values):
            out_sheet.write(row_index, col, value, cell_style)
    _save_xls(out, FOODS_PATH)
    return added


def append_recipe_row(fields: dict[str, str]) -> dict[str, str]:
    """Append one recipe row to MySQL (+ Excel backup)."""
    return _write_recipe_rows(fields, replace_id=None)


def update_recipe_row(row_id: str, fields: dict[str, str]) -> dict[str, str]:
    """Overwrite fields for an existing recipe id in MySQL (+ Excel backup)."""
    return _write_recipe_rows(fields, replace_id=str(row_id).strip())


def _write_recipe_rows(fields: dict[str, str], replace_id: str | None) -> dict[str, str]:
    try:
        from .shared_catalog import best_effort_export, insert_recipe, update_recipe

        if replace_id:
            item = update_recipe(replace_id, fields)
        else:
            item = insert_recipe(fields)
        best_effort_export("recipes")
        return item
    except Exception as mysql_exc:
        logger = __import__("logging").getLogger(__name__)
        logger.exception("MySQL recipe write failed; falling back to Excel: %s", mysql_exc)

    import xlrd
    import xlwt

    read_path = active_recipe_path()
    if not read_path.exists() and not RECIPE_PATH.exists():
        raise FileNotFoundError(str(RECIPE_PATH))
    if not read_path.exists():
        read_path = RECIPE_PATH

    book = xlrd.open_workbook(str(read_path))
    sheet = book.sheet_by_index(0)
    headers = [str(sheet.cell_value(0, col)).strip() for col in range(sheet.ncols)]
    for _field, header in COLUMN_FIELDS:
        if header not in headers:
            raise RuntimeError(f"Recipe.xls 缺少欄位：{header}")

    existing_rows = [
        [_cell(sheet, row, col) for col in range(sheet.ncols)]
        for row in range(1, sheet.nrows)
    ]
    field_to_header = {field: header for field, header in COLUMN_FIELDS}

    def apply_fields(values: list) -> list:
        out = list(values)
        for field, header in field_to_header.items():
            col = headers.index(header)
            if col >= len(out):
                out.extend([""] * (col + 1 - len(out)))
            out[col] = fields.get(field) or ""
        return out

    if replace_id:
        target = None
        for idx, values in enumerate(existing_rows):
            if str(idx + 1) == replace_id:
                target = idx
                break
        if target is None:
            raise RuntimeError(f"找不到要更新的食譜列：{replace_id}")
        existing_rows[target] = apply_fields(existing_rows[target])
        new_values = existing_rows[target]
        row_id = replace_id
    else:
        new_values = apply_fields([""] * sheet.ncols)
        existing_rows.append(new_values)
        row_id = str(len(existing_rows))

    out = xlwt.Workbook(encoding="utf-8")
    out_sheet = out.add_sheet(sheet.name or "食譜")
    header_style, cell_style = _xls_styles()
    widths = [28, 22, 36, 28, 24, 78, 55, 55, 80, 28, 28]
    for col, header in enumerate(headers):
        out_sheet.write(0, col, header, header_style)
        out_sheet.col(col).width = 256 * (widths[col] if col < len(widths) else 28)
    out_sheet.panes_frozen = True
    out_sheet.horz_split_pos = 1
    for row_index, values in enumerate(existing_rows, start=1):
        for col, value in enumerate(values):
            out_sheet.write(row_index, col, value, cell_style)
    _save_xls(out, RECIPE_PATH)

    item = {"id": row_id, "_headers": "\t".join(headers)}
    for field, header in COLUMN_FIELDS:
        col = headers.index(header)
        item[field] = str(new_values[col]).strip() if col < len(new_values) else ""
    return item


def _cell(sheet, row: int, col: int):
    import xlrd

    cell = sheet.cell(row, col)
    if cell.ctype == xlrd.XL_CELL_NUMBER:
        value = cell.value
        if value == int(value):
            return int(value)
        return value
    if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
        return ""
    return cell.value


def _xls_styles():
    import xlwt

    header_style = xlwt.easyxf(
        "font: name 微軟正黑體, bold on, height 240, colour white;"
        "align: horiz center, vert center, wrap on;"
        "pattern: pattern solid, fore_colour gray80;"
        "borders: left thin, right thin, top thin, bottom thin"
    )
    cell_style = xlwt.easyxf(
        "font: name 微軟正黑體, height 200;"
        "align: vert top, wrap on;"
        "borders: left thin, right thin, top thin, bottom thin"
    )
    return header_style, cell_style


def _save_xls(book, path) -> None:
    tmp_path = str(path) + f".tmp-{os.getpid()}-{int(time.time() * 1000)}"
    book.save(tmp_path)
    try:
        os.replace(tmp_path, str(path))
        return
    except OSError:
        # Windows file lock (e.g. WPS/Excel open): keep a newer .new sibling.
        # Readers prefer .new when it is newer via active_recipe_path().
        fallback = str(path) + ".new"
        try:
            os.replace(tmp_path, fallback)
        except OSError as exc:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise OSError(f"無法寫入 {path}（亦無法寫入 {fallback}）") from exc


# Alias used by /api/recipes/create
create_recipe = ensure_recipe
