"""Shared MySQL catalog for Recipe / Foods / daily_nutrient / deviation.

Excel files remain seed + local backup exports. Runtime truth is MySQL so every
website and Android client sees the same live data.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import ROOT

logger = logging.getLogger(__name__)

RECIPE_XLS = ROOT / "Recipe.xls"
FOODS_XLS = ROOT / "Foods.xls"
DAILY_XLSX = ROOT / "daily_nutrient.xlsx"
DEVIATION_XLS = ROOT / "deviation.xls"
DEVIATION_SQLITE = ROOT / "deviation.db"

# RLock: init_schema() may call seed_from_excel_if_empty while a fetch already
# holds the seed lock via mysql_ready() → ensure_schema() → init_schema().
_SEED_LOCK = threading.RLock()
_seeded = False

# Keep field maps local to avoid circular imports with recipes.py.
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
NUTRIENT_FIELDS = (
    ("kcal", "熱量(大卡)"),
    ("fiber_g", "膳食纖維(克)"),
    ("calcium_g", "鈣(克)"),
    ("iron_g", "鐵(克)"),
    ("zinc_g", "鋅(克)"),
    ("iodine_g", "碘(克)"),
    ("selenium_g", "硒(克)"),
    ("vitamin_b_g", "維生素B(克)"),
    ("vitamin_c_g", "維生素C(克)"),
    ("vitamin_d_g", "維生素D(克)"),
    ("carb_g", "碳水化合物(克)"),
    ("protein_g", "蛋白質(克)"),
    ("fat_g", "脂質(克)"),
    ("water_g", "水分(克)"),
)
RECIPE_NUTRIENT_HEADERS = tuple(h for _f, h in NUTRIENT_FIELDS)
NUTRIENT_KEYS = (
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
RECIPE_TO_TARGET = dict(zip(RECIPE_NUTRIENT_HEADERS, NUTRIENT_KEYS))

RECIPE_HEADERS = [h for _f, h in COLUMN_FIELDS] + [h for _f, h in NUTRIENT_FIELDS]
FOOD_HEADERS = (
    "食材中文",
    "食材英文",
    "食材日文",
    "食材韓文",
    "益處",
    "禁忌",
    "元素表",
) + RECIPE_NUTRIENT_HEADERS
DAILY_HEADERS = ("族群分類", "年齡層", "性別") + NUTRIENT_KEYS


def _empty_totals() -> dict[str, float]:
    return {key: 0.0 for key in NUTRIENT_KEYS}

CATALOG_SCHEMA_SQL = [
    """
    CREATE TABLE IF NOT EXISTS catalog_recipes (
      recipe_id INT AUTO_INCREMENT PRIMARY KEY,
      country VARCHAR(128) NULL,
      name_zh VARCHAR(255) NULL,
      name_en VARCHAR(255) NULL,
      name_ja VARCHAR(255) NULL,
      name_ko VARCHAR(255) NULL,
      recipe MEDIUMTEXT NULL,
      method MEDIUMTEXT NULL,
      benefit TEXT NULL,
      ban TEXT NULL,
      nutrient TEXT NULL,
      allergens TEXT NULL,
      kcal DOUBLE NULL,
      fiber_g DOUBLE NULL,
      calcium_g DOUBLE NULL,
      iron_g DOUBLE NULL,
      zinc_g DOUBLE NULL,
      iodine_g DOUBLE NULL,
      selenium_g DOUBLE NULL,
      vitamin_b_g DOUBLE NULL,
      vitamin_c_g DOUBLE NULL,
      vitamin_d_g DOUBLE NULL,
      carb_g DOUBLE NULL,
      protein_g DOUBLE NULL,
      fat_g DOUBLE NULL,
      water_g DOUBLE NULL,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      INDEX idx_recipes_country (country),
      INDEX idx_recipes_name_zh (name_zh)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS catalog_foods (
      food_id INT AUTO_INCREMENT PRIMARY KEY,
      name_zh VARCHAR(128) NOT NULL,
      name_en VARCHAR(255) NULL,
      name_ja VARCHAR(255) NULL,
      name_ko VARCHAR(255) NULL,
      benefit TEXT NULL,
      ban TEXT NULL,
      nutrient TEXT NULL,
      kcal DOUBLE NULL,
      fiber_g DOUBLE NULL,
      calcium_g DOUBLE NULL,
      iron_g DOUBLE NULL,
      zinc_g DOUBLE NULL,
      iodine_g DOUBLE NULL,
      selenium_g DOUBLE NULL,
      vitamin_b_g DOUBLE NULL,
      vitamin_c_g DOUBLE NULL,
      vitamin_d_g DOUBLE NULL,
      carb_g DOUBLE NULL,
      protein_g DOUBLE NULL,
      fat_g DOUBLE NULL,
      water_g DOUBLE NULL,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      UNIQUE KEY uq_foods_zh (name_zh)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS catalog_daily_nutrient (
      row_id INT AUTO_INCREMENT PRIMARY KEY,
      group_label VARCHAR(64) NULL,
      age_band VARCHAR(64) NOT NULL,
      gender VARCHAR(32) NOT NULL,
      targets_json MEDIUMTEXT NOT NULL,
      ranges_json MEDIUMTEXT NOT NULL,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      UNIQUE KEY uq_daily_band_gender (age_band, gender)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS catalog_deviations (
      id INT AUTO_INCREMENT PRIMARY KEY,
      user_id VARCHAR(32) NULL,
      recorded_at VARCHAR(32) NOT NULL,
      age INT NULL,
      age_band VARCHAR(32) NOT NULL,
      gender VARCHAR(16) NOT NULL,
      complaint TEXT NOT NULL,
      face_de TEXT NOT NULL,
      face_score TEXT NOT NULL,
      tongue_body_de TEXT NOT NULL,
      tongue_body_score TEXT NOT NULL,
      tongue_coat_de TEXT NOT NULL,
      tongue_coat_score TEXT NOT NULL,
      mean_face DOUBLE NULL,
      mean_body DOUBLE NULL,
      mean_coat DOUBLE NULL,
      mean_all DOUBLE NULL,
      learning_mark VARCHAR(64) NOT NULL,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      INDEX idx_dev_age_sex (age_band, gender),
      INDEX idx_dev_user (user_id)
    )
    """,
]


def _connect():
    """Open MySQL without re-entering ensure_schema (avoids seed/init deadlock)."""
    from .db import connect

    return connect(ensure=False)


def _cell_number(raw) -> float | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip().replace(",", "").replace("，", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _xls_cell(sheet, row: int, col: int):
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


def mysql_ready() -> bool:
    try:
        from .db import ensure_schema

        return bool(ensure_schema())
    except Exception:
        return False


def table_count(table: str) -> int:
    from .security import assert_allowed_table

    safe = assert_allowed_table(table)
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM `" + safe + "`")
            return int((cur.fetchone() or {}).get("c") or 0)
    finally:
        conn.close()


def _import_recipes_from_xls(path: Path) -> int:
    import xlrd

    if not path.exists():
        return 0
    sheet = xlrd.open_workbook(str(path)).sheet_by_index(0)
    headers = [str(sheet.cell_value(0, c)).strip() for c in range(sheet.ncols)]
    index = {name: i for i, name in enumerate(headers)}
    rows: list[dict[str, Any]] = []
    for r in range(1, sheet.nrows):
        item: dict[str, Any] = {}
        for field, header in COLUMN_FIELDS:
            col = index.get(header)
            item[field] = "" if col is None else str(_xls_cell(sheet, r, col)).strip()
        for field, header in NUTRIENT_FIELDS:
            col = index.get(header)
            item[field] = None if col is None else _cell_number(_xls_cell(sheet, r, col))
        if not any(item.get(f) for f, _ in COLUMN_FIELDS):
            continue
        rows.append(item)
    if not rows:
        return 0
    conn = _connect()
    try:
        with conn.cursor() as cur:
            for item in rows:
                cur.execute(
                    """
                    INSERT INTO catalog_recipes (
                      country, name_zh, name_en, name_ja, name_ko, recipe, method,
                      benefit, ban, nutrient, allergens,
                      kcal, fiber_g, calcium_g, iron_g, zinc_g, iodine_g, selenium_g,
                      vitamin_b_g, vitamin_c_g, vitamin_d_g, carb_g, protein_g, fat_g, water_g
                    ) VALUES (
                      %(country)s, %(name_zh)s, %(name_en)s, %(name_ja)s, %(name_ko)s,
                      %(recipe)s, %(method)s, %(benefit)s, %(ban)s, %(nutrient)s, %(allergens)s,
                      %(kcal)s, %(fiber_g)s, %(calcium_g)s, %(iron_g)s, %(zinc_g)s,
                      %(iodine_g)s, %(selenium_g)s, %(vitamin_b_g)s, %(vitamin_c_g)s,
                      %(vitamin_d_g)s, %(carb_g)s, %(protein_g)s, %(fat_g)s, %(water_g)s
                    )
                    """,
                    item,
                )
        return len(rows)
    finally:
        conn.close()


def _import_foods_from_xls(path: Path) -> int:
    import xlrd

    if not path.exists():
        return 0
    sheet = xlrd.open_workbook(str(path)).sheet_by_index(0)
    headers = [str(sheet.cell_value(0, c)).strip() for c in range(sheet.ncols)]
    index = {name: i for i, name in enumerate(headers)}
    rows: list[dict[str, Any]] = []
    for r in range(1, sheet.nrows):
        zh_col = index.get("食材中文")
        zh = "" if zh_col is None else str(_xls_cell(sheet, r, zh_col)).strip()
        if not zh:
            continue
        item: dict[str, Any] = {
            "name_zh": zh,
            "name_en": str(_xls_cell(sheet, r, index["食材英文"])).strip() if "食材英文" in index else "",
            "name_ja": str(_xls_cell(sheet, r, index["食材日文"])).strip() if "食材日文" in index else "",
            "name_ko": str(_xls_cell(sheet, r, index["食材韓文"])).strip() if "食材韓文" in index else "",
            "benefit": str(_xls_cell(sheet, r, index["益處"])).strip() if "益處" in index else "",
            "ban": str(_xls_cell(sheet, r, index["禁忌"])).strip() if "禁忌" in index else "",
            "nutrient": str(_xls_cell(sheet, r, index["元素表"])).strip() if "元素表" in index else "",
        }
        for field, header in NUTRIENT_FIELDS:
            col = index.get(header)
            item[field] = None if col is None else _cell_number(_xls_cell(sheet, r, col))
        rows.append(item)
    if not rows:
        return 0
    conn = _connect()
    try:
        with conn.cursor() as cur:
            for item in rows:
                cur.execute(
                    """
                    INSERT INTO catalog_foods (
                      name_zh, name_en, name_ja, name_ko, benefit, ban, nutrient,
                      kcal, fiber_g, calcium_g, iron_g, zinc_g, iodine_g, selenium_g,
                      vitamin_b_g, vitamin_c_g, vitamin_d_g, carb_g, protein_g, fat_g, water_g
                    ) VALUES (
                      %(name_zh)s, %(name_en)s, %(name_ja)s, %(name_ko)s,
                      %(benefit)s, %(ban)s, %(nutrient)s,
                      %(kcal)s, %(fiber_g)s, %(calcium_g)s, %(iron_g)s, %(zinc_g)s,
                      %(iodine_g)s, %(selenium_g)s, %(vitamin_b_g)s, %(vitamin_c_g)s,
                      %(vitamin_d_g)s, %(carb_g)s, %(protein_g)s, %(fat_g)s, %(water_g)s
                    )
                    ON DUPLICATE KEY UPDATE
                      name_en=VALUES(name_en), name_ja=VALUES(name_ja), name_ko=VALUES(name_ko),
                      benefit=VALUES(benefit), ban=VALUES(ban), nutrient=VALUES(nutrient),
                      kcal=VALUES(kcal), fiber_g=VALUES(fiber_g), calcium_g=VALUES(calcium_g),
                      iron_g=VALUES(iron_g), zinc_g=VALUES(zinc_g), iodine_g=VALUES(iodine_g),
                      selenium_g=VALUES(selenium_g), vitamin_b_g=VALUES(vitamin_b_g),
                      vitamin_c_g=VALUES(vitamin_c_g), vitamin_d_g=VALUES(vitamin_d_g),
                      carb_g=VALUES(carb_g), protein_g=VALUES(protein_g), fat_g=VALUES(fat_g),
                      water_g=VALUES(water_g)
                    """,
                    item,
                )
        return len(rows)
    finally:
        conn.close()


def _import_daily_from_xlsx(path: Path) -> int:
    from .nutrient_targets import parse_target_range

    if not path.exists():
        return 0
    try:
        from openpyxl import load_workbook
    except ImportError:
        return 0
    wb = load_workbook(path, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    headers = [str(h).strip() if h is not None else "" for h in next(rows_iter)]
    index = {name: i for i, name in enumerate(headers) if name}
    rows: list[dict[str, Any]] = []
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
        if not band or not gender:
            continue
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
        rows.append(
            {
                "group_label": str(cell("族群分類") or "").strip(),
                "age_band": band,
                "gender": gender,
                "targets_json": json.dumps(targets, ensure_ascii=False),
                "ranges_json": json.dumps(ranges, ensure_ascii=False),
            }
        )
    if not rows:
        return 0
    conn = _connect()
    try:
        with conn.cursor() as cur:
            for item in rows:
                cur.execute(
                    """
                    INSERT INTO catalog_daily_nutrient
                      (group_label, age_band, gender, targets_json, ranges_json)
                    VALUES
                      (%(group_label)s, %(age_band)s, %(gender)s, %(targets_json)s, %(ranges_json)s)
                    ON DUPLICATE KEY UPDATE
                      group_label=VALUES(group_label),
                      targets_json=VALUES(targets_json),
                      ranges_json=VALUES(ranges_json)
                    """,
                    item,
                )
        return len(rows)
    finally:
        conn.close()


def _import_deviations_from_sqlite(path: Path) -> int:
    if not path.exists():
        return 0
    src = sqlite3.connect(str(path))
    src.row_factory = sqlite3.Row
    try:
        items = src.execute("SELECT * FROM deviations ORDER BY id").fetchall()
    except sqlite3.Error:
        return 0
    finally:
        src.close()
    if not items:
        return 0
    conn = _connect()
    try:
        with conn.cursor() as cur:
            for item in items:
                cur.execute(
                    """
                    INSERT INTO catalog_deviations (
                      user_id, recorded_at, age, age_band, gender, complaint,
                      face_de, face_score, tongue_body_de, tongue_body_score,
                      tongue_coat_de, tongue_coat_score,
                      mean_face, mean_body, mean_coat, mean_all, learning_mark
                    ) VALUES (
                      %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                    )
                    """,
                    (
                        item["user_id"],
                        item["recorded_at"],
                        item["age"],
                        item["age_band"],
                        item["gender"],
                        item["complaint"],
                        item["face_de"],
                        item["face_score"],
                        item["tongue_body_de"],
                        item["tongue_body_score"],
                        item["tongue_coat_de"],
                        item["tongue_coat_score"],
                        item["mean_face"],
                        item["mean_body"],
                        item["mean_coat"],
                        item["mean_all"],
                        item["learning_mark"],
                    ),
                )
        return len(items)
    finally:
        conn.close()


def seed_from_excel_if_empty() -> dict[str, int]:
    """Import local Excel/SQLite into MySQL once when catalog tables are empty."""
    global _seeded
    if _seeded:
        return {}
    with _SEED_LOCK:
        if _seeded:
            return {}
        if not mysql_ready():
            return {}
        stats: dict[str, int] = {}
        try:
            if table_count("catalog_recipes") == 0:
                stats["recipes"] = _import_recipes_from_xls(RECIPE_XLS)
            if table_count("catalog_foods") == 0:
                stats["foods"] = _import_foods_from_xls(FOODS_XLS)
            if table_count("catalog_daily_nutrient") == 0:
                stats["daily_nutrient"] = _import_daily_from_xlsx(DAILY_XLSX)
            if table_count("catalog_deviations") == 0:
                stats["deviations"] = _import_deviations_from_sqlite(DEVIATION_SQLITE)
            _seeded = True
            if stats:
                logger.info("MySQL catalog seeded from Excel/SQLite: %s", stats)
            return stats
        except Exception:
            logger.exception("MySQL catalog seed failed")
            return stats


def _recipe_token() -> tuple[int, int]:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS c, COALESCE(MAX(UNIX_TIMESTAMP(updated_at)),0) AS t FROM catalog_recipes"
            )
            row = cur.fetchone() or {}
            return int(row.get("c") or 0), int(row.get("t") or 0)
    finally:
        conn.close()


def _food_token() -> tuple[int, int]:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS c, COALESCE(MAX(UNIX_TIMESTAMP(updated_at)),0) AS t FROM catalog_foods"
            )
            row = cur.fetchone() or {}
            return int(row.get("c") or 0), int(row.get("t") or 0)
    finally:
        conn.close()


def _daily_token() -> tuple[int, int]:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS c, COALESCE(MAX(UNIX_TIMESTAMP(updated_at)),0) AS t FROM catalog_daily_nutrient"
            )
            row = cur.fetchone() or {}
            return int(row.get("c") or 0), int(row.get("t") or 0)
    finally:
        conn.close()


def _row_to_recipe_item(db_row: dict[str, Any]) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": str(db_row["recipe_id"]),
        "_headers": "\t".join(RECIPE_HEADERS),
        "_source": "mysql",
    }
    for field, _header in COLUMN_FIELDS:
        item[field] = str(db_row.get(field) or "").strip()
    nutrients = _empty_totals()
    has_any = False
    for field, recipe_header in NUTRIENT_FIELDS:
        value = db_row.get(field)
        num = _cell_number(value)
        item[field] = num
        if num is not None:
            nutrients[RECIPE_TO_TARGET[recipe_header]] = float(num)
            has_any = True
    item["nutrients"] = nutrients
    item["has_nutrients"] = has_any
    return item


@lru_cache(maxsize=4)
def _fetch_recipes_cached(count: int, token: int) -> tuple[dict, ...]:
    del count, token
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM catalog_recipes ORDER BY recipe_id")
            rows = cur.fetchall() or []
        return tuple(_row_to_recipe_item(r) for r in rows)
    finally:
        conn.close()


def fetch_recipe_rows() -> tuple[dict, ...] | None:
    seed_from_excel_if_empty()
    if not mysql_ready():
        return None
    try:
        if table_count("catalog_recipes") == 0:
            return None
        return _fetch_recipes_cached(*_recipe_token())
    except Exception:
        logger.exception("read catalog_recipes failed")
        return None


@lru_cache(maxsize=64)
def _fetch_recipes_for_country_cached(country: str, count: int, token: int) -> tuple[dict, ...]:
    """Country-scoped catalog rows — avoids rebuilding the full 24k cache for dropdowns."""
    del count, token
    wanted = (country or "").strip()
    if not wanted:
        return ()
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM catalog_recipes WHERE country=%s ORDER BY recipe_id",
                (wanted,),
            )
            rows = cur.fetchall() or []
        return tuple(_row_to_recipe_item(r) for r in rows)
    finally:
        conn.close()


def fetch_recipe_rows_for_country(country: str) -> tuple[dict, ...] | None:
    """Return MySQL recipes for one country, or None to fall back to Excel scan."""
    wanted = (country or "").strip()
    if not wanted:
        return ()
    seed_from_excel_if_empty()
    if not mysql_ready():
        return None
    try:
        if table_count("catalog_recipes") == 0:
            return None
        return _fetch_recipes_for_country_cached(wanted, *_recipe_token())
    except Exception:
        logger.exception("read catalog_recipes by country failed")
        return None


def fetch_recipe_rows_by_names(names: list[str]) -> tuple[dict, ...] | None:
    """Exact zh/en/ja/ko name hits across all countries (ensure global lookup)."""
    needles = [str(n or "").strip() for n in names if str(n or "").strip()]
    if not needles:
        return ()
    seed_from_excel_if_empty()
    if not mysql_ready():
        return None
    try:
        if table_count("catalog_recipes") == 0:
            return None
        conn = _connect()
        try:
            with conn.cursor() as cur:
                clauses = []
                params: list[str] = []
                for needle in needles:
                    clauses.append(
                        "(name_zh=%s OR name_en=%s OR name_ja=%s OR name_ko=%s)"
                    )
                    params.extend([needle, needle, needle, needle])
                sql = (
                    "SELECT * FROM catalog_recipes WHERE "
                    + " OR ".join(clauses)
                    + " ORDER BY recipe_id"
                )
                cur.execute(sql, params)
                rows = cur.fetchall() or []
            return tuple(_row_to_recipe_item(r) for r in rows)
        finally:
            conn.close()
    except Exception:
        logger.exception("read catalog_recipes by name failed")
        return None


def invalidate_recipe_mysql_cache() -> None:
    _fetch_recipes_cached.cache_clear()
    _fetch_recipes_for_country_cached.cache_clear()


def insert_recipe(fields: dict[str, Any]) -> dict[str, Any]:
    payload = {field: (fields.get(field) or "") for field, _ in COLUMN_FIELDS}
    for field, _ in NUTRIENT_FIELDS:
        payload[field] = _cell_number(fields.get(field))
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO catalog_recipes (
                  country, name_zh, name_en, name_ja, name_ko, recipe, method,
                  benefit, ban, nutrient, allergens,
                  kcal, fiber_g, calcium_g, iron_g, zinc_g, iodine_g, selenium_g,
                  vitamin_b_g, vitamin_c_g, vitamin_d_g, carb_g, protein_g, fat_g, water_g
                ) VALUES (
                  %(country)s, %(name_zh)s, %(name_en)s, %(name_ja)s, %(name_ko)s,
                  %(recipe)s, %(method)s, %(benefit)s, %(ban)s, %(nutrient)s, %(allergens)s,
                  %(kcal)s, %(fiber_g)s, %(calcium_g)s, %(iron_g)s, %(zinc_g)s,
                  %(iodine_g)s, %(selenium_g)s, %(vitamin_b_g)s, %(vitamin_c_g)s,
                  %(vitamin_d_g)s, %(carb_g)s, %(protein_g)s, %(fat_g)s, %(water_g)s
                )
                """,
                payload,
            )
            recipe_id = int(cur.lastrowid)
            cur.execute("SELECT * FROM catalog_recipes WHERE recipe_id=%s", (recipe_id,))
            row = cur.fetchone()
    finally:
        conn.close()
    invalidate_recipe_mysql_cache()
    return _row_to_recipe_item(row)


def update_recipe(recipe_id: str | int, fields: dict[str, Any]) -> dict[str, Any]:
    from .security import assert_allowed_columns

    rid = int(str(recipe_id).strip())
    allowed = {field for field, _ in COLUMN_FIELDS} | {field for field, _ in NUTRIENT_FIELDS}
    sets = []
    values: list[Any] = []
    for field, _ in COLUMN_FIELDS:
        if field in fields:
            assert_allowed_columns([field], allowed)
            sets.append("`" + field + "` = %s")
            values.append(fields.get(field) or "")
    for field, _ in NUTRIENT_FIELDS:
        if field in fields:
            assert_allowed_columns([field], allowed)
            sets.append("`" + field + "` = %s")
            values.append(_cell_number(fields.get(field)))
    if not sets:
        raise RuntimeError("沒有可更新的食譜欄位")
    values.append(rid)
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE catalog_recipes SET " + ", ".join(sets) + " WHERE recipe_id = %s",
                values,
            )
            if cur.rowcount == 0:
                raise RuntimeError(f"找不到要更新的食譜列：{recipe_id}")
            cur.execute("SELECT * FROM catalog_recipes WHERE recipe_id=%s", (rid,))
            row = cur.fetchone()
    finally:
        conn.close()
    invalidate_recipe_mysql_cache()
    return _row_to_recipe_item(row)


@lru_cache(maxsize=4)
def _fetch_foods_cached(count: int, token: int) -> dict[str, dict[str, str]]:
    del count, token
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM catalog_foods ORDER BY food_id")
            rows = cur.fetchall() or []
    finally:
        conn.close()
    foods: dict[str, dict[str, str]] = {}
    for db_row in rows:
        zh = str(db_row.get("name_zh") or "").strip()
        if not zh:
            continue
        item = {
            "name_zh": zh,
            "name_en": str(db_row.get("name_en") or "").strip(),
            "name_ja": str(db_row.get("name_ja") or "").strip(),
            "name_ko": str(db_row.get("name_ko") or "").strip(),
            "benefit": str(db_row.get("benefit") or "").strip(),
            "ban": str(db_row.get("ban") or "").strip(),
            "nutrient": str(db_row.get("nutrient") or "").strip(),
            "_id": str(db_row.get("food_id")),
        }
        foods[zh] = item
        for key in ("name_en", "name_ja", "name_ko"):
            alias = item[key]
            if alias and alias not in foods:
                foods[alias] = item
    return foods


def fetch_foods_index() -> dict[str, dict[str, str]] | None:
    seed_from_excel_if_empty()
    if not mysql_ready():
        return None
    try:
        if table_count("catalog_foods") == 0:
            return None
        return _fetch_foods_cached(*_food_token())
    except Exception:
        logger.exception("read catalog_foods failed")
        return None


def invalidate_foods_mysql_cache() -> None:
    _fetch_foods_cached.cache_clear()


def upsert_food(fields: dict[str, Any]) -> None:
    zh = str(fields.get("name_zh") or "").strip()
    if not zh:
        return
    payload = {
        "name_zh": zh,
        "name_en": str(fields.get("name_en") or "").strip(),
        "name_ja": str(fields.get("name_ja") or "").strip(),
        "name_ko": str(fields.get("name_ko") or "").strip(),
        "benefit": str(fields.get("benefit") or "").strip(),
        "ban": str(fields.get("ban") or "").strip(),
        "nutrient": str(fields.get("nutrient") or "").strip(),
    }
    for field, _ in NUTRIENT_FIELDS:
        payload[field] = _cell_number(fields.get(field))
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO catalog_foods (
                  name_zh, name_en, name_ja, name_ko, benefit, ban, nutrient,
                  kcal, fiber_g, calcium_g, iron_g, zinc_g, iodine_g, selenium_g,
                  vitamin_b_g, vitamin_c_g, vitamin_d_g, carb_g, protein_g, fat_g, water_g
                ) VALUES (
                  %(name_zh)s, %(name_en)s, %(name_ja)s, %(name_ko)s,
                  %(benefit)s, %(ban)s, %(nutrient)s,
                  %(kcal)s, %(fiber_g)s, %(calcium_g)s, %(iron_g)s, %(zinc_g)s,
                  %(iodine_g)s, %(selenium_g)s, %(vitamin_b_g)s, %(vitamin_c_g)s,
                  %(vitamin_d_g)s, %(carb_g)s, %(protein_g)s, %(fat_g)s, %(water_g)s
                )
                ON DUPLICATE KEY UPDATE
                  name_en=IF(VALUES(name_en)='', name_en, VALUES(name_en)),
                  name_ja=IF(VALUES(name_ja)='', name_ja, VALUES(name_ja)),
                  name_ko=IF(VALUES(name_ko)='', name_ko, VALUES(name_ko)),
                  benefit=IF(VALUES(benefit)='', benefit, VALUES(benefit)),
                  ban=IF(VALUES(ban)='', ban, VALUES(ban)),
                  nutrient=IF(VALUES(nutrient)='', nutrient, VALUES(nutrient)),
                  kcal=COALESCE(VALUES(kcal), kcal),
                  fiber_g=COALESCE(VALUES(fiber_g), fiber_g),
                  calcium_g=COALESCE(VALUES(calcium_g), calcium_g),
                  iron_g=COALESCE(VALUES(iron_g), iron_g),
                  zinc_g=COALESCE(VALUES(zinc_g), zinc_g),
                  iodine_g=COALESCE(VALUES(iodine_g), iodine_g),
                  selenium_g=COALESCE(VALUES(selenium_g), selenium_g),
                  vitamin_b_g=COALESCE(VALUES(vitamin_b_g), vitamin_b_g),
                  vitamin_c_g=COALESCE(VALUES(vitamin_c_g), vitamin_c_g),
                  vitamin_d_g=COALESCE(VALUES(vitamin_d_g), vitamin_d_g),
                  carb_g=COALESCE(VALUES(carb_g), carb_g),
                  protein_g=COALESCE(VALUES(protein_g), protein_g),
                  fat_g=COALESCE(VALUES(fat_g), fat_g),
                  water_g=COALESCE(VALUES(water_g), water_g)
                """,
                payload,
            )
    finally:
        conn.close()
    invalidate_foods_mysql_cache()


def patch_foods(updates: dict[str, dict[str, str]]) -> int:
    if not updates:
        return 0
    changed = 0
    for zh, item in updates.items():
        name = str(zh or "").strip()
        if not name:
            continue
        payload = {"name_zh": name}
        payload.update({k: v for k, v in item.items() if v})
        upsert_food(payload)
        changed += 1
    return changed


def append_missing_foods(names: list[str]) -> list[str]:
    added: list[str] = []
    index = fetch_foods_index() or {}
    for name in names:
        zh = str(name or "").strip()
        if not zh or zh in index:
            continue
        upsert_food(
            {
                "name_zh": zh,
                "nutrient": "網路搜尋待補（教學示範）",
            }
        )
        added.append(zh)
        index[zh] = {"name_zh": zh}
    return added


@lru_cache(maxsize=2)
def _fetch_daily_cached(count: int, token: int) -> tuple[dict, ...]:
    del count, token
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM catalog_daily_nutrient ORDER BY row_id")
            rows = cur.fetchall() or []
    finally:
        conn.close()
    out: list[dict] = []
    for db_row in rows:
        try:
            targets = json.loads(db_row.get("targets_json") or "{}")
            ranges = json.loads(db_row.get("ranges_json") or "{}")
        except json.JSONDecodeError:
            targets, ranges = {}, {}
        out.append(
            {
                "group": str(db_row.get("group_label") or "").strip(),
                "age_band": str(db_row.get("age_band") or "").strip(),
                "gender": str(db_row.get("gender") or "").strip(),
                "targets": targets,
                "ranges": ranges,
            }
        )
    return tuple(out)


def fetch_daily_rows() -> tuple[dict, ...] | None:
    seed_from_excel_if_empty()
    if not mysql_ready():
        return None
    try:
        if table_count("catalog_daily_nutrient") == 0:
            return None
        return _fetch_daily_cached(*_daily_token())
    except Exception:
        logger.exception("read catalog_daily_nutrient failed")
        return None


def insert_deviation(user_id: str, row: dict[str, Any]) -> None:
    from .deviation import _dump

    seed_from_excel_if_empty()
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO catalog_deviations (
                  user_id, recorded_at, age, age_band, gender, complaint,
                  face_de, face_score, tongue_body_de, tongue_body_score,
                  tongue_coat_de, tongue_coat_score,
                  mean_face, mean_body, mean_coat, mean_all, learning_mark
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    user_id,
                    row["recorded_at"],
                    row["age"],
                    row["age_band"],
                    row["gender"],
                    row["complaint"],
                    _dump(row["face_de"]),
                    _dump(row["face_score"]),
                    _dump(row["tongue_body_de"]),
                    _dump(row["tongue_body_score"]),
                    _dump(row["tongue_coat_de"]),
                    _dump(row["tongue_coat_score"]),
                    row["mean_face"],
                    row["mean_body"],
                    row["mean_coat"],
                    row["mean_all"],
                    row["learning_mark"],
                ),
            )
    finally:
        conn.close()


def fetch_deviation_rows(limit: int = 65000) -> list[dict[str, Any]]:
    seed_from_excel_if_empty()
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM catalog_deviations ORDER BY id DESC LIMIT %s",
                (int(limit),),
            )
            rows = cur.fetchall() or []
        return list(reversed(rows))
    finally:
        conn.close()


def fetch_deviation_cohorts() -> list[dict[str, Any]]:
    from .deviation import QUIET_HIGH, QUIET_LOW, SEVERE_HIGH

    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT age_band, gender,
                       COUNT(*) AS n_all,
                       SUM(CASE WHEN complaint = '無' THEN 1 ELSE 0 END) AS n_quiet,
                       AVG(CASE WHEN complaint = '無' THEN mean_face END) AS face_mean,
                       AVG(CASE WHEN complaint = '無' THEN mean_body END) AS body_mean,
                       AVG(CASE WHEN complaint = '無' THEN mean_coat END) AS coat_mean,
                       AVG(CASE WHEN complaint = '無' THEN mean_all END) AS all_mean
                FROM catalog_deviations
                GROUP BY age_band, gender
                ORDER BY age_band, gender
                """
            )
            rows = cur.fetchall() or []
    finally:
        conn.close()
    cohorts: list[dict[str, Any]] = []
    for item in rows:
        mean_all = None if item["all_mean"] is None else round(float(item["all_mean"]), 1)
        n_quiet = int(item["n_quiet"] or 0)
        if n_quiet < 5:
            verdict = "樣本不足"
        elif mean_all is None:
            verdict = "缺測"
        elif mean_all <= SEVERE_HIGH:
            verdict = "無病者均分落在1–3，視為重症，這個年齡性別的判讀偏嚴"
        elif mean_all < QUIET_LOW:
            verdict = "無病者均分低於4，異常偏低"
        elif mean_all <= QUIET_HIGH:
            verdict = "無病者均分在4–7，符合規格外一般色差參考"
        else:
            verdict = "無病者均分在8–10健康帶"
        cohorts.append(
            {
                "age_band": item["age_band"],
                "gender": item["gender"],
                "n_all": int(item["n_all"]),
                "n_quiet": n_quiet,
                "face_mean": None if item["face_mean"] is None else round(float(item["face_mean"]), 1),
                "body_mean": None if item["body_mean"] is None else round(float(item["body_mean"]), 1),
                "coat_mean": None if item["coat_mean"] is None else round(float(item["coat_mean"]), 1),
                "all_mean": mean_all,
                "verdict": verdict,
            }
        )
    return cohorts


def _save_xls_book(book, path: Path) -> Path:
    tmp_path = str(path) + f".tmp-{os.getpid()}-{int(datetime.now().timestamp() * 1000)}"
    book.save(tmp_path)
    try:
        os.replace(tmp_path, str(path))
        return path
    except OSError:
        fallback = Path(str(path) + ".new")
        os.replace(tmp_path, str(fallback))
        return fallback


def export_recipes_xls(path: Path | None = None) -> Path:
    import xlwt

    dest = path or RECIPE_XLS
    rows = fetch_recipe_rows() or ()
    book = xlwt.Workbook(encoding="utf-8")
    sheet = book.add_sheet("食譜")
    for col, header in enumerate(RECIPE_HEADERS):
        sheet.write(0, col, header)
    for row_index, item in enumerate(rows, start=1):
        values = [item.get(field) or "" for field, _ in COLUMN_FIELDS]
        values += [
            "" if item.get(field) is None else item.get(field) for field, _ in NUTRIENT_FIELDS
        ]
        for col, value in enumerate(values):
            sheet.write(row_index, col, value)
    return _save_xls_book(book, dest)


def export_foods_xls(path: Path | None = None) -> Path:
    import xlwt

    dest = path or FOODS_XLS
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM catalog_foods ORDER BY food_id")
            rows = cur.fetchall() or []
    finally:
        conn.close()
    book = xlwt.Workbook(encoding="utf-8")
    sheet = book.add_sheet("食材")
    for col, header in enumerate(FOOD_HEADERS):
        sheet.write(0, col, header)
    for row_index, item in enumerate(rows, start=1):
        values = [
            item.get("name_zh") or "",
            item.get("name_en") or "",
            item.get("name_ja") or "",
            item.get("name_ko") or "",
            item.get("benefit") or "",
            item.get("ban") or "",
            item.get("nutrient") or "",
        ]
        for field, _ in NUTRIENT_FIELDS:
            val = item.get(field)
            values.append("" if val is None else val)
        for col, value in enumerate(values):
            sheet.write(row_index, col, value)
    return _save_xls_book(book, dest)


def export_daily_xlsx(path: Path | None = None) -> Path:
    from openpyxl import Workbook

    dest = path or DAILY_XLSX
    rows = fetch_daily_rows() or ()
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(list(DAILY_HEADERS))
    for item in rows:
        ranges = item.get("ranges") or {}
        line = [item.get("group") or "", item.get("age_band") or "", item.get("gender") or ""]
        for key in NUTRIENT_KEYS:
            raw = (ranges.get(key) or {}).get("raw")
            if raw is None:
                mid = (item.get("targets") or {}).get(key)
                raw = "" if mid is None else mid
            line.append(raw)
        ws.append(line)
    tmp = Path(str(dest) + f".tmp-{os.getpid()}")
    wb.save(tmp)
    try:
        os.replace(tmp, dest)
        return dest
    except OSError:
        fallback = Path(str(dest) + ".new")
        os.replace(tmp, fallback)
        return fallback


def export_deviation_xls(path: Path | None = None) -> Path:
    """Rebuild colored deviation.xls from MySQL (same layout as deviation.export_workbook)."""
    import xlwt

    from .deviation import (
        HEADER,
        _delta_style,
        _load,
        _styles,
        _write_pair,
    )

    dest = path or DEVIATION_XLS
    rows = fetch_deviation_rows()
    book = xlwt.Workbook(encoding="utf-8")
    sheet = book.add_sheet("檢測差異")
    green, red, plain = _styles()
    for col, title in enumerate(HEADER):
        sheet.write(0, col, title, plain)
        sheet.col(col).width = 256 * (22 if col >= 2 else 14)
    for row_index, item in enumerate(rows, start=1):
        face_de = _load(item["face_de"], 12)
        body_de = _load(item["tongue_body_de"], 5)
        coat_de = _load(item["tongue_coat_de"], 5)
        values = [
            "" if item["age"] is None else int(item["age"]),
            item["gender"],
            item["complaint"],
        ]
        for col, value in enumerate(values):
            sheet.write(row_index, col, value, plain)
        for offset, value in enumerate(face_de):
            style = _delta_style(value, green, red, plain)
            sheet.write(row_index, 3 + offset, "" if value is None else value, style)
        for offset, (body, coat) in enumerate(zip(body_de, coat_de)):
            _write_pair(sheet, row_index, 15 + offset, body, coat)
        tail = [
            item["recorded_at"],
            item["age_band"],
            item["mean_face"],
            item["mean_body"],
            item["mean_coat"],
            item["mean_all"],
            item["learning_mark"],
        ]
        for offset, value in enumerate(tail):
            sheet.write(row_index, 20 + offset, "" if value is None else value, plain)
    learning = book.add_sheet("年齡性別學習")
    note = (
        "差異值是與教學正常色的ΔE。ΔE在3以內為綠色，超過為紅色。"
        "沒有特殊疾病、也沒有不舒服的人，臉色、舌色、舌苔平均健康分應在4到7（規格外一般色差；健康帶為8–10）；"
        "平均1到3視為重症（不應在無嚴重門時出現）。"
        "同一年齡區塊、同一性別累積至少5次無不適紀錄後，用這個範圍核對判讀偏鬆或偏嚴。"
        "完整每次紀錄在 MySQL catalog_deviations；本表只顯示最近65000列。"
    )
    learning.write_merge(0, 0, 0, 8, note, plain)
    learning_header = ["年齡區塊", "性別", "全部次數", "無不適次數", "臉色均分", "舌色均分", "舌苔均分", "三者均分", "對照"]
    for col, title in enumerate(learning_header):
        learning.write(1, col, title, plain)
        learning.col(col).width = 256 * (18 if col < 8 else 42)
    for row_index, cohort in enumerate(fetch_deviation_cohorts(), start=2):
        learning.write(row_index, 0, cohort["age_band"], plain)
        learning.write(row_index, 1, cohort["gender"], plain)
        learning.write(row_index, 2, cohort["n_all"], plain)
        learning.write(row_index, 3, cohort["n_quiet"], plain)
        learning.write(row_index, 4, "" if cohort["face_mean"] is None else cohort["face_mean"], plain)
        learning.write(row_index, 5, "" if cohort["body_mean"] is None else cohort["body_mean"], plain)
        learning.write(row_index, 6, "" if cohort["coat_mean"] is None else cohort["coat_mean"], plain)
        learning.write(row_index, 7, "" if cohort["all_mean"] is None else cohort["all_mean"], plain)
        learning.write(row_index, 8, cohort["verdict"], plain)
    return _save_xls_book(book, dest)


def export_all_backups(dest_dir: Path | None = None) -> dict[str, str]:
    """Write live MySQL catalog back to Excel files for local backup."""
    folder = dest_dir or ROOT
    folder.mkdir(parents=True, exist_ok=True)
    out = {
        "Recipe.xls": str(export_recipes_xls(folder / "Recipe.xls")),
        "Foods.xls": str(export_foods_xls(folder / "Foods.xls")),
        "daily_nutrient.xlsx": str(export_daily_xlsx(folder / "daily_nutrient.xlsx")),
        "deviation.xls": str(export_deviation_xls(folder / "deviation.xls")),
    }
    return out


def best_effort_export(kind: str) -> None:
    try:
        if kind == "recipes":
            export_recipes_xls()
        elif kind == "foods":
            export_foods_xls()
        elif kind == "daily":
            export_daily_xlsx()
        elif kind == "deviation":
            export_deviation_xls()
        elif kind == "all":
            export_all_backups()
    except Exception:
        logger.warning("Excel backup export failed for %s", kind, exc_info=True)
