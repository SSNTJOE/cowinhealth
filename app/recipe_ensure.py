"""Ensure a recipe exists for country + name: match, research, append Recipe/Foods.xls."""
from __future__ import annotations

import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .config import ROOT
from .recipes import (
    COLUMN_FIELDS,
    RECIPE_PATH,
    TEACHING_DISCLAIMER,
    invalidate_recipe_cache,
    localized_name,
    normalize_lang,
    public_recipe,
    recipe_rows,
)

FOODS_PATH = ROOT / "Foods.xls"
FOOD_HEADERS = ("食材中文", "食材英文", "食材日文", "食材韓文", "益處", "禁忌", "元素表")
RECIPE_HEADERS = tuple(header for _field, header in COLUMN_FIELDS)
PARTIAL_NOTE = "網路資料不足或部分欄位待補。教學示範，非中醫診斷／營養處方。"
RESEARCH_NOTE = "欄位依公開網頁整理，教學示範，非中醫診斷／營養處方。"
UA = "Health-ing-teaching-demo/1.0 (recipe ensure; educational)"
RESEARCH_TIMEOUT_SEC = 8

# Same allergen ingredient tokens used when building Recipe.xls 過敏原.
ALLERGEN_INGREDIENTS = {
    "鯉魚", "鯽魚", "鱸魚", "草魚", "鰱魚", "青魚", "帶魚", "黃魚", "鯖魚", "鮪魚",
    "鮭魚", "鱈魚", "鯛魚", "秋刀魚", "沙丁魚", "鰻魚", "鱔魚", "泥鰍", "虱目魚",
    "石斑魚", "比目魚", "鯊魚", "白鯧", "烏魚", "鰹魚", "吳郭魚", "魚",
    "蝦", "蝦米", "龍蝦", "螃蟹",
    "蛤蜊", "牡蠣", "蜆", "淡菜", "干貝", "鮑魚", "章魚", "魷魚", "烏賊",
    "海蜇", "田螺", "蟶子", "海參", "海膽",
    "雞蛋", "蛋白", "蛋黃", "鴨蛋", "皮蛋", "鵪鶉蛋",
    "牛奶", "羊奶", "奶油", "起司", "優格",
    "小麥", "大麥", "燕麥",
    "黃豆", "黑豆", "豆腐", "豆漿", "豆干", "腐竹", "納豆", "醬油", "毛豆", "黃豆芽", "味噌",
    "花生", "花生油",
    "杏仁果", "腰果", "夏威夷豆", "核桃", "松子", "栗子", "甜杏仁", "北杏仁", "白果",
    "黑芝麻", "白芝麻", "麻油", "南瓜子", "葵花子", "亞麻仁",
    "蕎麥", "芹菜", "西洋芹", "芥末", "芥菜", "山葵", "醋", "黃酒", "葡萄酒",
}

_ensure_lock = threading.Lock()
_inflight: dict[tuple[str, str], threading.Event] = {}
_workbook_lock = threading.Lock()


def _norm_name(text: str | None) -> str:
    return re.sub(r"\s+", "", (text or "").strip()).casefold()


def _ensure_key(country: str, name: str) -> tuple[str, str]:
    return ((country or "").strip().casefold(), _norm_name(name))


def find_recipe_row(country: str, name: str) -> dict[str, str] | None:
    wanted = (country or "").strip()
    needle = _norm_name(name)
    if not wanted or not needle:
        return None
    for row in recipe_rows():
        if (row.get("country") or "").strip() != wanted:
            continue
        for field in ("name_zh", "name_en", "name_ja", "name_ko"):
            if _norm_name(row.get(field)) == needle:
                return row
        if _norm_name(localized_name(row, "zh")) == needle:
            return row
    return None


def _open_sheet(path):
    import xlrd

    if not path.exists():
        raise FileNotFoundError(str(path))
    return xlrd.open_workbook(str(path)).sheet_by_index(0)


def _sheet_matrix(path) -> tuple[list[str], list[list[str]]]:
    sheet = _open_sheet(path)
    headers = [str(sheet.cell_value(0, col)).strip() for col in range(sheet.ncols)]
    rows: list[list[str]] = []
    for row in range(1, sheet.nrows):
        rows.append([str(sheet.cell_value(row, col)).strip() for col in range(sheet.ncols)])
    return headers, rows


def _header_style():
    import xlwt

    return xlwt.easyxf(
        "font: name 微軟正黑體, bold on, height 240, colour white;"
        "align: horiz center, vert center, wrap on;"
        "pattern: pattern solid, fore_colour gray80;"
        "borders: left thin, right thin, top thin, bottom thin"
    )


def _cell_style():
    import xlwt

    return xlwt.easyxf(
        "font: name 微軟正黑體, height 200;"
        "align: vert top, wrap on;"
        "borders: left thin, right thin, top thin, bottom thin"
    )


def _safe_replace(tmp_path, final_path) -> str:
    new_path = str(final_path) + ".new"
    os.replace(tmp_path, new_path)
    try:
        os.replace(new_path, str(final_path))
        return str(final_path)
    except OSError:
        # Leave .new beside the locked workbook so data is not lost.
        return new_path


def _write_xls(path, sheet_name: str, headers: list[str], rows: list[list[str]], widths: list[int]) -> str:
    import xlwt

    book = xlwt.Workbook(encoding="utf-8")
    sheet = book.add_sheet(sheet_name)
    header_style = _header_style()
    cell_style = _cell_style()
    for col, header in enumerate(headers):
        sheet.write(0, col, header, header_style)
        width = widths[col] if col < len(widths) else 28
        sheet.col(col).width = 256 * width
    sheet.panes_frozen = True
    sheet.horz_split_pos = 1
    for row_index, values in enumerate(rows, start=1):
        for col, value in enumerate(values):
            sheet.write(row_index, col, value if value is not None else "", cell_style)
    tmp_path = str(path) + ".writing"
    book.save(tmp_path)
    return _safe_replace(tmp_path, path)


def _http_json(url: str, timeout: float = RESEARCH_TIMEOUT_SEC) -> Any | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, ValueError, OSError):
        return None


def _wiki_opensearch(lang: str, query: str) -> str | None:
    params = urllib.parse.urlencode(
        {
            "action": "opensearch",
            "search": query,
            "limit": 1,
            "namespace": 0,
            "format": "json",
        }
    )
    data = _http_json(f"https://{lang}.wikipedia.org/w/api.php?{params}")
    if not isinstance(data, list) or len(data) < 2:
        return None
    titles = data[1]
    if not isinstance(titles, list) or not titles:
        return None
    title = str(titles[0] or "").strip()
    return title or None


def _wiki_summary(lang: str, title: str) -> dict[str, str]:
    encoded = urllib.parse.quote(title.replace(" ", "_"), safe="")
    data = _http_json(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{encoded}")
    if not isinstance(data, dict):
        return {}
    extract = str(data.get("extract") or "").strip()
    display = str(data.get("title") or title).strip()
    desc = str(data.get("description") or "").strip()
    return {"title": display, "extract": extract, "description": desc, "lang": lang}


def research_dish(country: str, name: str, lang: str) -> dict[str, Any]:
    """Best-effort public-web research. Never invent medical / TCM claims."""
    lang = normalize_lang(lang)
    queries = [
        f"{name} {country}",
        f"{name} 食譜",
        f"{name} recipe",
        name,
    ]
    summaries: list[dict[str, str]] = []
    for wiki_lang in ("zh", "en", "ja", "ko"):
        for query in queries:
            title = _wiki_opensearch(wiki_lang, query)
            if not title:
                continue
            summary = _wiki_summary(wiki_lang, title)
            if summary.get("extract") or summary.get("title"):
                summaries.append(summary)
                break
        if len(summaries) >= 2:
            break

    names = {"zh": "", "en": "", "ja": "", "ko": ""}
    names[lang] = name.strip()
    for summary in summaries:
        wlang = summary.get("lang") or ""
        title = summary.get("title") or ""
        if wlang in names and title and not names[wlang]:
            names[wlang] = title
    if not names["zh"]:
        names["zh"] = name.strip() if lang == "zh" else (summaries[0].get("title") if summaries else name.strip())
    if not names["en"] and summaries:
        for summary in summaries:
            if summary.get("lang") == "en" and summary.get("title"):
                names["en"] = summary["title"]
                break
    if not names["en"]:
        names["en"] = name.strip() if lang == "en" else ""

    extract = ""
    for summary in summaries:
        if summary.get("extract"):
            extract = summary["extract"]
            break

    ingredients = _guess_ingredients(extract, name)
    method = _guess_method(extract, ingredients)
    researched = bool(summaries) or bool(ingredients)
    return {
        "names": names,
        "extract": extract,
        "ingredients": ingredients,
        "method": method,
        "researched": researched,
        "note": RESEARCH_NOTE if researched else PARTIAL_NOTE,
    }


def _guess_ingredients(extract: str, dish_name: str) -> list[tuple[str, int]]:
    """Parse light ingredient hints; fall back to empty rather than inventing TCM data."""
    del dish_name
    text = extract or ""
    found: list[str] = []
    # Common Chinese food tokens already in Foods.xls / recipes.
    candidates = [
        "粳米", "糙米", "糯米", "小米", "麵粉", "雞蛋", "雞肉", "豬肉", "牛肉", "羊肉",
        "洋蔥", "大蒜", "生薑", "蔥", "番茄", "胡蘿蔔", "馬鈴薯", "地瓜", "高麗菜",
        "菠菜", "豆腐", "黃豆", "花生", "食鹽", "醬油", "麻油", "花生油", "橄欖油",
        "牛奶", "奶油", "起司", "優格", "魚", "蝦", "螃蟹", "白米", "米飯",
    ]
    for token in candidates:
        if token in text and token not in found:
            found.append(token)
    if not found:
        return []
    # Teaching demo portioning toward ~500 g when possible.
    base = max(40, 500 // max(1, len(found)))
    pairs = [(name, base) for name in found]
    total = sum(gram for _, gram in pairs)
    if pairs and total != 500:
        name, gram = pairs[0]
        pairs[0] = (name, max(1, gram + (500 - total)))
    return pairs


def _guess_method(extract: str, ingredients: list[tuple[str, int]]) -> str:
    if ingredients:
        joined = "、".join(f"{name}{gram}克" for name, gram in ingredients)
        tip = (extract or "").strip().replace("\n", " ")
        if tip:
            tip = tip[:180] + ("…" if len(tip) > 180 else "")
            return f"教學示範煮法：備齊{joined}。參考公開介紹：{tip}（非中醫診斷）"
        return f"教學示範煮法：備齊{joined}，依慣常方式烹調至熟。（非中醫診斷）"
    tip = (extract or "").strip().replace("\n", " ")
    if tip:
        return f"教學示範煮法（待補克數）：{tip[:220]}{'…' if len(tip) > 220 else ''}（非中醫診斷）"
    return ""


def _format_recipe_cell(ingredients: list[tuple[str, int]]) -> str:
    if not ingredients:
        return ""
    return "、".join(f"{name} {gram}克" for name, gram in ingredients)


def _load_foods_index() -> tuple[list[str], list[list[str]], dict[str, dict[str, str]]]:
    headers, rows = _sheet_matrix(FOODS_PATH)
    # Expect first 7 columns as FOOD_HEADERS; keep extra columns if any.
    foods: dict[str, dict[str, str]] = {}
    for values in rows:
        padded = list(values) + [""] * max(0, 7 - len(values))
        zh = padded[0]
        if not zh:
            continue
        foods[zh] = {
            "en": padded[1],
            "ja": padded[2],
            "ko": padded[3],
            "benefit": padded[4],
            "ban": padded[5],
            "nutrient": padded[6],
        }
    return headers, rows, foods


def _join_food_field(ingredients: list[tuple[str, int]], foods: dict[str, dict[str, str]], field: str) -> str:
    parts: list[str] = []
    for name, _gram in ingredients:
        text = (foods.get(name) or {}).get(field) or ""
        if text:
            parts.append(f"{name}:{text}")
    return ";".join(parts)


def _allergen_cell(ingredients: list[tuple[str, int]]) -> str:
    labels = [name for name, _gram in ingredients if name in ALLERGEN_INGREDIENTS]
    return "、".join(labels)


def _append_missing_foods(
    headers: list[str],
    rows: list[list[str]],
    foods: dict[str, dict[str, str]],
    ingredients: list[tuple[str, int]],
) -> list[str]:
    added: list[str] = []
    for name, _gram in ingredients:
        if name in foods:
            continue
        row = [name, "", "", "", "", "", f"待補；{PARTIAL_NOTE}"]
        # Pad to header width.
        if len(headers) > len(row):
            row.extend([""] * (len(headers) - len(row)))
        rows.append(row[: len(headers)])
        foods[name] = {
            "en": "",
            "ja": "",
            "ko": "",
            "benefit": "",
            "ban": "",
            "nutrient": row[6],
        }
        added.append(name)
    return added


def _build_recipe_values(
    country: str,
    names: dict[str, str],
    ingredients: list[tuple[str, int]],
    method: str,
    foods: dict[str, dict[str, str]],
    note: str,
) -> list[str]:
    recipe_cell = _format_recipe_cell(ingredients)
    benefit = _join_food_field(ingredients, foods, "benefit")
    ban = _join_food_field(ingredients, foods, "ban")
    nutrient = _join_food_field(ingredients, foods, "nutrient")
    if not nutrient:
        nutrient = note
    elif note and note not in nutrient:
        nutrient = nutrient + "；" + note
    if not method:
        method = note
    allergens = _allergen_cell(ingredients)
    return [
        country.strip(),
        names.get("zh") or "",
        names.get("en") or "",
        names.get("ja") or "",
        names.get("ko") or "",
        recipe_cell,
        method,
        benefit,
        ban,
        nutrient,
        allergens,
    ]


def _append_recipe_and_foods(
    country: str,
    names: dict[str, str],
    ingredients: list[tuple[str, int]],
    method: str,
    note: str,
) -> dict[str, Any]:
    with _workbook_lock:
        # Re-check after lock in case a waiter raced us.
        existing = find_recipe_row(country, names.get("zh") or names.get("en") or "")
        if existing is None:
            for value in names.values():
                if value:
                    existing = find_recipe_row(country, value)
                    if existing:
                        break
        if existing:
            return {"row": existing, "created": False, "foods_added": [], "partial": False}

        food_headers, food_rows, foods = _load_foods_index()
        if not food_headers:
            food_headers = list(FOOD_HEADERS)
        foods_added = _append_missing_foods(food_headers, food_rows, foods, ingredients)
        if foods_added:
            widths = [28, 28, 28, 28, 55, 55, 55] + [28] * max(0, len(food_headers) - 7)
            _write_xls(FOODS_PATH, "食材", food_headers, food_rows, widths)

        recipe_headers, recipe_rows_data = _sheet_matrix(RECIPE_PATH)
        if not recipe_headers:
            recipe_headers = list(RECIPE_HEADERS)
        header_index = {header: pos for pos, header in enumerate(recipe_headers)}
        ordered = _build_recipe_values(country, names, ingredients, method, foods, note)
        values_by_header = {
            header: ordered[idx] for idx, (_field, header) in enumerate(COLUMN_FIELDS)
        }
        if list(recipe_headers) == list(RECIPE_HEADERS):
            new_row = ordered
        else:
            new_row = [""] * len(recipe_headers)
            for header, value in values_by_header.items():
                col = header_index.get(header)
                if col is not None:
                    new_row[col] = value

        recipe_rows_data.append(new_row)
        widths = [28, 22, 36, 28, 24, 78, 72, 55, 55, 80, 28]
        _write_xls(RECIPE_PATH, "食譜", recipe_headers, recipe_rows_data, widths)
        invalidate_recipe_cache()

        # New row id is 1-based sheet row index (= len after append).
        new_id = str(len(recipe_rows_data))
        row = {
            "id": new_id,
            "country": values_by_header.get("國家", ""),
            "name_zh": values_by_header.get("中文食譜", ""),
            "name_en": values_by_header.get("英文食譜", ""),
            "name_ja": values_by_header.get("日文食譜", ""),
            "name_ko": values_by_header.get("韓文食譜", ""),
            "recipe": values_by_header.get("食譜", ""),
            "method": values_by_header.get("煮法", ""),
            "benefit": values_by_header.get("益處", ""),
            "ban": values_by_header.get("禁忌", ""),
            "nutrient": values_by_header.get("元素", ""),
            "allergens": values_by_header.get("過敏原", ""),
        }
        partial = not bool(ingredients) or not bool(row["recipe"])
        return {
            "row": row,
            "created": True,
            "foods_added": foods_added,
            "partial": partial,
        }


def ensure_recipe(country: str, name: str, lang: str = "zh") -> dict[str, Any]:
    """Return existing or newly created recipe payload. Concurrent same key waits once."""
    country = (country or "").strip()
    name = (name or "").strip()
    lang = normalize_lang(lang)
    if not country:
        raise ValueError("請選擇國家")
    if not name:
        raise ValueError("請輸入食譜名稱")

    existing = find_recipe_row(country, name)
    if existing:
        return {
            "status": "existing",
            "created": False,
            "partial": False,
            "foods_added": [],
            "note": "",
            "recipe": public_recipe(existing, lang, 0),
            "disclaimer": TEACHING_DISCLAIMER,
        }

    key = _ensure_key(country, name)
    waiter = False
    event: threading.Event | None = None
    with _ensure_lock:
        existing = find_recipe_row(country, name)
        if existing:
            return {
                "status": "existing",
                "created": False,
                "partial": False,
                "foods_added": [],
                "note": "",
                "recipe": public_recipe(existing, lang, 0),
                "disclaimer": TEACHING_DISCLAIMER,
            }
        if key in _inflight:
            event = _inflight[key]
            waiter = True
        else:
            event = threading.Event()
            _inflight[key] = event

    if waiter and event is not None:
        event.wait(timeout=120)
        existing = find_recipe_row(country, name)
        if existing:
            return {
                "status": "existing",
                "created": False,
                "partial": False,
                "foods_added": [],
                "note": "",
                "recipe": public_recipe(existing, lang, 0),
                "disclaimer": TEACHING_DISCLAIMER,
            }
        raise TimeoutError("食譜建立逾時，請稍後再試")

    try:
        try:
            researched = research_dish(country, name, lang)
        except Exception:
            researched = {
                "names": {"zh": name, "en": "", "ja": "", "ko": ""},
                "extract": "",
                "ingredients": [],
                "method": "",
                "researched": False,
                "note": PARTIAL_NOTE,
            }
        names = dict(researched.get("names") or {})
        names[lang] = names.get(lang) or name
        names["zh"] = names.get("zh") or name
        result = _append_recipe_and_foods(
            country=country,
            names=names,
            ingredients=list(researched.get("ingredients") or []),
            method=str(researched.get("method") or ""),
            note=str(researched.get("note") or PARTIAL_NOTE),
        )
        row = result["row"]
        status = "created"
        if result.get("partial") or not researched.get("researched"):
            status = "partial"
        return {
            "status": status,
            "created": bool(result.get("created")),
            "partial": bool(result.get("partial")) or status == "partial",
            "foods_added": result.get("foods_added") or [],
            "note": researched.get("note") or PARTIAL_NOTE,
            "recipe": public_recipe(row, lang, 0),
            "disclaimer": TEACHING_DISCLAIMER,
        }
    finally:
        with _ensure_lock:
            if event is not None:
                event.set()
            _inflight.pop(key, None)
