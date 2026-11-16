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

_WRITE_LOCK = threading.Lock()
_ING_RE = re.compile(r"^(.+?)\s+(\d+(?:\.\d+)?)\s*克$")
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


ResearchFn = Callable[[str, str, str], dict[str, str | list[tuple[str, int]] | bool]]


def ensure_recipe(
    country: str,
    name: str,
    lang: str = "zh",
    *,
    research_fn: ResearchFn | None = None,
) -> dict:
    """Return existing recipe or append a researched row. Never overwrites same country+name."""
    wanted_country = (country or "").strip()
    wanted_name = (name or "").strip()
    if not wanted_country:
        raise ValueError("請選擇國家")
    if not wanted_name:
        raise ValueError("請輸入食譜名稱")
    lang = normalize_lang(lang)

    existing = _find_existing(wanted_country, wanted_name, lang)
    if existing is not None:
        return {
            "created": False,
            "partial": False,
            "recipe": public_recipe(existing, lang, 0),
            "foods_added": [],
            "note": "",
            "disclaimer": TEACHING_DISCLAIMER,
        }

    if not _WRITE_LOCK.acquire(blocking=False):
        raise RuntimeError("另一筆食譜正在建立中，請稍後再試")
    try:
        # Re-check under lock in case a parallel request just wrote.
        invalidate_recipe_cache()
        existing = _find_existing(wanted_country, wanted_name, lang)
        if existing is not None:
            return {
                "created": False,
                "partial": False,
                "recipe": public_recipe(existing, lang, 0),
                "foods_added": [],
                "note": "",
                "disclaimer": TEACHING_DISCLAIMER,
            }

        research = (research_fn or research_dish)(wanted_country, wanted_name, lang)
        fields = build_row_fields(wanted_country, wanted_name, lang, research)
        foods_added = sync_foods_for_ingredients(fields.get("recipe") or "")
        # Enrich benefit/ban/nutrient from Foods.xls when ingredients matched.
        fields = enrich_from_foods(fields)
        row = append_recipe_row(fields)
        invalidate_recipe_cache()
        partial = bool(research.get("partial")) or _is_partial(fields)
        note_parts = [CREATE_NOTE]
        if partial:
            note_parts.append(PARTIAL_NOTE)
        return {
            "created": True,
            "partial": partial,
            "recipe": public_recipe(row, lang, 0),
            "foods_added": foods_added,
            "note": " ".join(note_parts),
            "disclaimer": TEACHING_DISCLAIMER,
        }
    finally:
        _WRITE_LOCK.release()


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
    """Best-effort Wikipedia / public-page research. Prefer fetched text over invention."""
    query = f"{country} {name} 食譜".strip() if lang == "zh" else f"{name} {country} recipe"
    snippets: list[str] = []
    titles: dict[str, str] = {}
    partial = True
    try:
        for wiki_lang in _wiki_langs(lang):
            hits = _wiki_search(name, wiki_lang)
            if not hits and name != query:
                hits = _wiki_search(query, wiki_lang)
            for title in hits[:2]:
                summary = _wiki_summary(title, wiki_lang)
                if not summary:
                    continue
                extract = str(summary.get("extract") or "").strip()
                display = str(summary.get("title") or title).strip()
                if extract:
                    snippets.append(extract)
                if display:
                    titles[wiki_lang] = display
                if extract:
                    partial = False
                    break
            if snippets:
                break
    except TimeoutError:
        raise
    except Exception:
        # Keep going with whatever we gathered; incomplete is OK.
        pass

    blob = "\n".join(snippets)
    food_index = load_food_name_index()
    pairs = extract_ingredients_from_text(blob, food_index)
    if not pairs:
        # Fall back to a minimal placeholder so the row is usable and Foods sync can skip.
        recipe_text = ""
        method = ""
        partial = True
    else:
        pairs = _normalize_grams(pairs, total=500)
        recipe_text = format_ingredients(pairs)
        method = _method_from_extract(blob, pairs) or _simple_method(pairs)
        partial = False

    benefit = ""
    ban = ""  # Never invent medical contraindications from web blurbs.
    nutrient = ""
    if pairs:
        # Will be filled from Foods.xls after sync in enrich_from_foods.
        pass

    names = {
        "name_zh": titles.get("zh", name if lang == "zh" else ""),
        "name_en": titles.get("en", name if lang == "en" else ""),
        "name_ja": titles.get("ja", name if lang == "ja" else ""),
        "name_ko": titles.get("ko", name if lang == "ko" else ""),
    }
    if lang == "zh" and not names["name_zh"]:
        names["name_zh"] = name
    elif lang == "en" and not names["name_en"]:
        names["name_en"] = name
    elif lang == "ja" and not names["name_ja"]:
        names["name_ja"] = name
    elif lang == "ko" and not names["name_ko"]:
        names["name_ko"] = name

    source_bit = (snippets[0][:180] + "…") if snippets else ""
    if source_bit and not method:
        method = f"參考公開資料摘要：{source_bit}"
        partial = True

    return {
        **names,
        "ingredients": recipe_text,
        "method": method,
        "benefit": benefit,
        "ban": ban,
        "nutrient": nutrient,
        "allergens": "、".join(n for n, _g in pairs if n in ALLERGEN_FOODS) if pairs else "",
        "partial": partial,
        "source": source_bit,
    }


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
    except TimeoutError:
        raise
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
            "srlimit": 5,
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


def load_food_name_index() -> dict[str, dict[str, str]]:
    """Map 食材中文 / other language names -> food row fields."""
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


def extract_ingredients_from_text(
    text: str,
    food_index: dict[str, dict[str, str]],
) -> list[tuple[str, int]]:
    """Pick known Foods.xls names that appear in fetched text (longest-first)."""
    if not text:
        return []
    cleaned = _TAG_RE.sub(" ", unescape(text))
    cleaned = _WS_RE.sub(" ", cleaned)
    # Prefer Chinese canonical names; longest match wins.
    names = sorted(
        {item["name_zh"] for item in food_index.values() if item.get("name_zh")},
        key=len,
        reverse=True,
    )
    found: list[str] = []
    remaining = cleaned
    for name in names:
        if len(name) < 2:
            continue
        if name in remaining:
            found.append(name)
            remaining = remaining.replace(name, " ", 1)
        if len(found) >= 8:
            break
    if not found:
        return []
    # Equal split toward 500g teaching total.
    base = 500 // len(found)
    rem = 500 - base * len(found)
    pairs: list[tuple[str, int]] = []
    for i, name in enumerate(found):
        pairs.append((name, base + (1 if i < rem else 0)))
    return pairs


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
    markers = ("作法", "做法", "煮法", "烹調", "烹调", "prepare", "cook", "method")
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
    pairs = parse_ingredient_text(fields.get("recipe") or "")
    if not pairs:
        return fields
    try:
        foods = load_food_name_index()
    except FileNotFoundError:
        return fields
    benefit_parts: list[str] = []
    ban_parts: list[str] = []
    nutrient_parts: list[str] = []
    for name, _gram in pairs:
        item = foods.get(name)
        if not item:
            continue
        if item.get("benefit"):
            benefit_parts.append(f"{name}:{item['benefit']}")
        if item.get("ban"):
            ban_parts.append(f"{name}:{item['ban']}")
        if item.get("nutrient"):
            nutrient_parts.append(f"{name}:{item['nutrient']}")
    if benefit_parts and not fields.get("benefit"):
        fields["benefit"] = ";".join(benefit_parts)
    if ban_parts and not fields.get("ban"):
        fields["ban"] = ";".join(ban_parts)
    if nutrient_parts and not fields.get("nutrient"):
        fields["nutrient"] = ";".join(nutrient_parts)
    if not fields.get("allergens"):
        fields["allergens"] = "、".join(n for n, _g in pairs if n in ALLERGEN_FOODS)
    return fields


def sync_foods_for_ingredients(recipe_text: str) -> list[str]:
    """Append missing ingredient rows to Foods.xls. Returns newly added 中文 names."""
    pairs = parse_ingredient_text(recipe_text)
    if not pairs:
        return []
    import xlrd
    import xlwt

    if not FOODS_PATH.exists():
        raise FileNotFoundError(str(FOODS_PATH))

    book = xlrd.open_workbook(str(FOODS_PATH))
    sheet = book.sheet_by_index(0)
    headers = [str(sheet.cell_value(0, col)).strip() for col in range(sheet.ncols)]
    # Preserve whatever columns exist; we only require the standard 7 when appending.
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
    """Append one Recipe.xls row and return the in-memory row dict recipes() can read."""
    import xlrd
    import xlwt

    if not RECIPE_PATH.exists():
        raise FileNotFoundError(str(RECIPE_PATH))

    book = xlrd.open_workbook(str(RECIPE_PATH))
    sheet = book.sheet_by_index(0)
    headers = [str(sheet.cell_value(0, col)).strip() for col in range(sheet.ncols)]
    for _field, header in COLUMN_FIELDS:
        if header not in headers:
            raise RuntimeError(f"Recipe.xls 缺少欄位：{header}")

    existing_rows = [
        [_cell(sheet, row, col) for col in range(sheet.ncols)]
        for row in range(1, sheet.nrows)
    ]
    new_values = [""] * sheet.ncols
    field_to_header = {field: header for field, header in COLUMN_FIELDS}
    for field, header in field_to_header.items():
        col = headers.index(header)
        new_values[col] = fields.get(field) or ""
    existing_rows.append(new_values)

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

    row_id = str(len(existing_rows))  # 1-based data row index matches recipe_rows ids
    item = {"id": row_id, "_headers": "\t".join(headers)}
    for field, header in COLUMN_FIELDS:
        col = headers.index(header)
        item[field] = str(new_values[col]).strip()
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
    except OSError:
        # Windows file lock: leave .new sibling rather than failing hard mid-request.
        fallback = str(path) + ".new"
        try:
            os.replace(tmp_path, fallback)
        except OSError as exc:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise OSError(f"無法寫入 {path}（亦無法寫入 {fallback}）") from exc
        raise OSError(f"無法覆寫 {path}，已寫入 {fallback}") from None


# Alias used by /api/recipes/create
create_recipe = ensure_recipe
