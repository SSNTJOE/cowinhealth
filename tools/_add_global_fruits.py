# -*- coding: utf-8 -*-
"""Add Global fruit-as-recipe rows to Recipe.xls and sync into catalog_recipes.

Uses Foods.xls fruit metadata + tools/_fill_nutrients per-100g tables.
Skips (country=Global, name_zh) duplicates already in Recipe.xls or MySQL.
"""
from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import _fill_nutrients as fill  # noqa: E402
from app.db import connect  # noqa: E402
from app.recipe_ensure import ALLERGEN_FOODS, format_ingredients  # noqa: E402
from app.recipes import simplify_organ_effects  # noqa: E402
from app.shared_catalog import (  # noqa: E402
    NUTRIENT_FIELDS,
    insert_recipe,
    invalidate_recipe_mysql_cache,
)

RECIPE_PATH = ROOT / "Recipe.xls"
FOODS_PATH = ROOT / "Foods.xls"
BACKUP_DIR = ROOT / "backups"

# Common edible fruits present in Foods.xls (exclude dried/juice/oil/wine).
FRUIT_NAMES = [
    "蘋果",
    "梨",
    "香蕉",
    "大蕉",
    "西瓜",
    "香瓜",
    "哈密瓜",
    "木瓜",
    "鳳梨",
    "芒果",
    "葡萄",
    "草莓",
    "藍莓",
    "桑葚",
    "奇異果",
    "柳橙",
    "橘子",
    "柚子",
    "葡萄柚",
    "檸檬",
    "金桔",
    "枇杷",
    "荔枝",
    "龍眼",
    "櫻桃",
    "桃子",
    "杏子",
    "李子",
    "楊梅",
    "梅子",
    "石榴",
    "柿子",
    "無花果",
    "椰子肉",
    "芭樂",
    "蓮霧",
    "楊桃",
    "火龍果",
    "山竹",
    "榴槤",
    "酪梨",
    "百香果",
    "釋迦",
    "菠蘿蜜",
    "紅毛丹",
    "紅棗",
    "橄欖",
]

# Extra per-100g rows for fruits not yet in _fill_nutrients.
# (kcal, fiber, ca_mg, fe_mg, zn_mg, i_ug, se_ug, b_mg, c_mg, d_ug, carb, protein, fat, water)
EXTRA_PER100G: dict[str, tuple] = {
    "大蕉": (122, 2.3, 3, 0.6, 0.1, 0, 1.5, 0.6, 18, 0, 32, 1.3, 0.4, 65),
    "香瓜": (34, 0.9, 9, 0.2, 0.2, 0, 0.4, 0.5, 37, 0, 8.2, 0.8, 0.2, 90),
    "哈密瓜": (34, 0.9, 9, 0.2, 0.2, 0, 0.4, 0.5, 37, 0, 8.2, 0.8, 0.2, 90),
    "鳳梨": (50, 1.4, 13, 0.3, 0.1, 0, 0.1, 0.5, 48, 0, 13, 0.5, 0.1, 86),
    "藍莓": (57, 2.4, 6, 0.3, 0.2, 0, 0.1, 0.4, 10, 0, 14, 0.7, 0.3, 84),
    "桑葚": (43, 1.7, 39, 1.9, 0.1, 0, 0.6, 0.5, 36, 0, 10, 1.4, 0.4, 88),
    "橘子": (53, 1.8, 37, 0.2, 0.1, 0, 0.1, 0.3, 27, 0, 13, 0.8, 0.3, 85),
    "柚子": (38, 1.0, 4, 0.1, 0.1, 0, 0, 0.2, 61, 0, 10, 0.8, 0.04, 89),
    "葡萄柚": (42, 1.6, 22, 0.1, 0.1, 0, 0.1, 0.3, 31, 0, 11, 0.8, 0.1, 88),
    "金桔": (71, 6.5, 62, 0.9, 0.2, 0, 0, 0.5, 44, 0, 16, 1.9, 0.9, 81),
    "枇杷": (47, 1.7, 16, 0.3, 0.1, 0, 0, 0.3, 1, 0, 12, 0.4, 0.2, 87),
    "櫻桃": (63, 2.1, 13, 0.4, 0.1, 0, 0, 0.3, 7, 0, 16, 1.1, 0.2, 82),
    "桃子": (39, 1.5, 6, 0.3, 0.2, 0, 0.1, 0.3, 7, 0, 10, 0.9, 0.3, 89),
    "杏子": (48, 2.0, 13, 0.4, 0.2, 0, 0.1, 0.7, 10, 0, 11, 1.4, 0.4, 86),
    "李子": (46, 1.4, 6, 0.2, 0.1, 0, 0, 0.3, 10, 0, 11, 0.7, 0.3, 87),
    "楊梅": (28, 1.0, 14, 1.2, 0.1, 0, 0, 0.2, 9, 0, 6.5, 0.8, 0.2, 92),
    "梅子": (46, 1.4, 6, 0.2, 0.1, 0, 0, 0.4, 9.5, 0, 11, 0.7, 0.3, 87),
    "石榴": (83, 4.0, 10, 0.3, 0.4, 0, 0.5, 0.6, 10, 0, 19, 1.7, 1.2, 78),
    "柿子": (70, 3.6, 8, 0.2, 0.1, 0, 0.6, 0.3, 7.5, 0, 19, 0.6, 0.2, 80),
    "無花果": (74, 2.9, 35, 0.4, 0.2, 0, 0.2, 0.4, 2, 0, 19, 0.8, 0.3, 79),
    "椰子肉": (354, 9.0, 14, 2.4, 1.1, 0, 10, 0.8, 3.3, 0, 15, 3.3, 33, 47),
    "芭樂": (68, 5.4, 18, 0.3, 0.2, 0, 0.6, 0.6, 228, 0, 14, 2.6, 1.0, 81),
    "蓮霧": (25, 0.9, 8, 0.2, 0.1, 0, 0, 0.2, 7, 0, 6, 0.6, 0.1, 93),
    "楊桃": (31, 2.8, 3, 0.1, 0.1, 0, 0.6, 0.4, 34, 0, 7, 1.0, 0.3, 91),
    "火龍果": (60, 3.0, 9, 0.7, 0.1, 0, 0, 0.3, 3, 0, 13, 1.2, 0.4, 84),
    "山竹": (73, 1.8, 12, 0.3, 0.2, 0, 0, 0.3, 3, 0, 18, 0.4, 0.6, 81),
    "榴槤": (147, 3.8, 6, 0.4, 0.3, 0, 0, 1.5, 20, 0, 27, 1.5, 5.3, 65),
    "酪梨": (160, 6.7, 12, 0.6, 0.6, 0, 0.4, 2.0, 10, 0, 8.5, 2.0, 15, 73),
    "百香果": (97, 10, 12, 1.6, 0.1, 0, 0.6, 0.5, 30, 0, 23, 2.2, 0.7, 73),
    "釋迦": (94, 4.4, 24, 0.6, 0.2, 0, 0, 0.5, 36, 0, 24, 2.1, 0.3, 73),
    "菠蘿蜜": (95, 1.5, 24, 0.2, 0.1, 0, 0.5, 0.6, 14, 0, 23, 1.7, 0.6, 73),
    "紅毛丹": (82, 0.9, 22, 0.4, 0.2, 0, 0, 0.3, 5, 0, 21, 0.9, 0.2, 78),
    "橄欖": (80, 3.0, 50, 0.8, 0.2, 0, 0.9, 0.3, 5, 0, 15, 0.8, 1.0, 80),
}

PORTION_G = 150


def _title_en(name: str) -> str:
    text = (name or "").strip()
    if not text:
        return ""
    return " ".join(part.capitalize() for part in text.replace("-", " ").split())


def _register_extra_nutrients() -> None:
    # Prefer exact fruit rows over fuzzy substring hits (e.g. 梨 inside 鳳梨).
    for name, row in EXTRA_PER100G.items():
        fill.PER100G[name] = row


def _load_foods() -> dict[str, dict[str, str]]:
    import xlrd

    sheet = xlrd.open_workbook(str(FOODS_PATH)).sheet_by_index(0)
    headers = [str(sheet.cell_value(0, c)).strip() for c in range(sheet.ncols)]
    index = {h: i for i, h in enumerate(headers)}
    foods: dict[str, dict[str, str]] = {}
    for r in range(1, sheet.nrows):
        zh = str(sheet.cell_value(r, index.get("食材中文", 0))).strip()
        if not zh:
            continue
        foods[zh] = {
            "name_zh": zh,
            "name_en": str(sheet.cell_value(r, index.get("食材英文", 1)) or "").strip(),
            "name_ja": str(sheet.cell_value(r, index.get("食材日文", 2)) or "").strip(),
            "name_ko": str(sheet.cell_value(r, index.get("食材韓文", 3)) or "").strip(),
            "benefit": str(sheet.cell_value(r, index.get("益處", 4)) or "").strip(),
            "ban": str(sheet.cell_value(r, index.get("禁忌", 5)) or "").strip(),
            "nutrient": str(sheet.cell_value(r, index.get("元素表", 6)) or "").strip(),
        }
    return foods


def _existing_global_names_xls() -> set[str]:
    import xlrd

    sheet = xlrd.open_workbook(str(RECIPE_PATH)).sheet_by_index(0)
    headers = [str(sheet.cell_value(0, c)).strip() for c in range(sheet.ncols)]
    country_col = headers.index("國家")
    name_col = headers.index("中文食譜")
    names: set[str] = set()
    for r in range(1, sheet.nrows):
        if str(sheet.cell_value(r, country_col)).strip() == "Global":
            names.add(str(sheet.cell_value(r, name_col)).strip())
    return names


def _existing_global_names_mysql() -> set[str]:
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name_zh FROM catalog_recipes WHERE country=%s",
                ("Global",),
            )
            rows = cur.fetchall() or []
    finally:
        conn.close()
    return {str(r.get("name_zh") or "").strip() for r in rows if r.get("name_zh")}


def _fruit_method(name_zh: str) -> str:
    special = {
        "椰子肉": f"取成熟椰子肉；洗淨切塊，可直接生食或輕蒸；即成{name_zh}",
        "紅棗": f"紅棗洗淨去核；可直接食用或溫水稍泡軟後食用；即成{name_zh}",
        "大蕉": f"大蕉去皮；可蒸熟或煎熟後食用（未熟者不宜直接生食）；即成{name_zh}",
        "榴槤": f"切開榴槤取果肉；可直接生食；即成{name_zh}",
        "鳳梨": f"鳳梨去皮去芯切片；可直接生食；即成{name_zh}",
        "菠蘿蜜": f"菠蘿蜜去皮取果瓣；可直接生食；即成{name_zh}",
        "酪梨": f"酪梨對半切開去核；可直接生食或壓泥；即成{name_zh}",
        "柿子": f"選軟熟柿子洗淨；可去皮後生食；即成{name_zh}",
        "橄欖": f"食用橄欖洗淨；可直接食用；即成{name_zh}",
    }
    if name_zh in special:
        return special[name_zh]
    return f"{name_zh}洗淨；可去皮去核後切片，直接生食；即成{name_zh}"


def _build_row(food: dict[str, str]) -> dict:
    zh = food["name_zh"]
    pairs = [(zh, PORTION_G)]
    recipe = format_ingredients(pairs)
    plain_benefit, plain_ban = simplify_organ_effects(
        {"recipe": recipe, "benefit": food.get("benefit") or "", "ban": food.get("ban") or ""},
        foods={zh: food},
    )
    nums = fill.recipe_nutrients(recipe, zh)
    if nums is None:
        raw = fill.lookup(zh)
        if raw is None:
            raise RuntimeError(f"missing nutrient table for {zh}")
        nums = fill.scale_row(raw, float(PORTION_G))
    fields = {
        "country": "Global",
        "name_zh": zh,
        "name_en": _title_en(food.get("name_en") or zh),
        "name_ja": food.get("name_ja") or "",
        "name_ko": food.get("name_ko") or "",
        "recipe": recipe,
        "method": _fruit_method(zh),
        "benefit": plain_benefit or "",
        "ban": plain_ban or "",
        "nutrient": food.get("nutrient") or "",
        "allergens": "、".join(n for n, _g in pairs if n in ALLERGEN_FOODS),
    }
    for offset, (field, _header) in enumerate(NUTRIENT_FIELDS):
        fields[field] = nums[offset]
    return fields


def _backup_recipe() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = BACKUP_DIR / f"Recipe.xls.bak-{stamp}-global-fruits"
    shutil.copy2(RECIPE_PATH, dest)
    return dest


def _append_xls(rows: list[dict]) -> None:
    import xlrd
    import xlwt

    rb = xlrd.open_workbook(str(RECIPE_PATH))
    sheet = rb.sheet_by_index(0)
    headers = [str(sheet.cell_value(0, c)).strip() for c in range(sheet.ncols)]
    header_to_field = {h: f for f, h in __import__("app.shared_catalog", fromlist=["COLUMN_FIELDS"]).COLUMN_FIELDS}
    header_to_field.update({h: f for f, h in NUTRIENT_FIELDS})

    try:
        from xlutils.copy import copy as xl_copy

        rb_fmt = xlrd.open_workbook(str(RECIPE_PATH), formatting_info=True)
        wb = xl_copy(rb_fmt)
        dest = wb.get_sheet(0)
        used = "xlutils"
        start_row = sheet.nrows
    except Exception:
        wb = xlwt.Workbook(encoding="utf-8")
        dest = wb.add_sheet(sheet.name or "Recipe")
        used = "xlwt"
        for c in range(sheet.ncols):
            dest.write(0, c, sheet.cell_value(0, c))
        for r in range(1, sheet.nrows):
            for c in range(sheet.ncols):
                value = fill.cell_write_value(sheet, r, c)
                if value is not None:
                    dest.write(r, c, value)
        start_row = sheet.nrows

    for i, fields in enumerate(rows):
        row_idx = start_row + i
        for c, header in enumerate(headers):
            field = header_to_field.get(header)
            if not field:
                continue
            value = fields.get(field)
            if value is None or value == "":
                continue
            dest.write(row_idx, c, value)

    tmp = str(RECIPE_PATH) + f".tmp-{os.getpid()}"
    wb.save(tmp)
    os.replace(tmp, str(RECIPE_PATH))
    print(f"xls writer={used} appended={len(rows)} total_rows={start_row + len(rows) - 1}")


def main() -> int:
    fill.ensure_deps()
    _register_extra_nutrients()

    foods = _load_foods()
    existing = _existing_global_names_xls() | _existing_global_names_mysql()
    missing_foods = [n for n in FRUIT_NAMES if n not in foods]
    if missing_foods:
        print("WARNING missing from Foods.xls:", missing_foods)

    to_add: list[dict] = []
    skipped = []
    for name in FRUIT_NAMES:
        if name in existing:
            skipped.append(name)
            continue
        food = foods.get(name)
        if not food:
            continue
        to_add.append(_build_row(food))

    print(f"planned={len(to_add)} skipped_dup={len(skipped)} fruit_list={len(FRUIT_NAMES)}")
    if skipped:
        print("skipped:", "、".join(skipped))
    if not to_add:
        print("nothing to add")
        return 0

    backup = _backup_recipe()
    print("backup:", backup)

    mysql_ok = 0
    mysql_fail = 0
    for fields in to_add:
        try:
            insert_recipe(fields)
            mysql_ok += 1
        except Exception as exc:  # noqa: BLE001
            mysql_fail += 1
            print(f"mysql insert fail {fields['name_zh']}: {exc}")

    invalidate_recipe_mysql_cache()
    _append_xls(to_add)

    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM catalog_recipes WHERE country=%s", ("Global",))
            global_count = int((cur.fetchone() or {}).get("c") or 0)
            cur.execute(
                "SELECT COUNT(*) AS c FROM catalog_recipes WHERE country=%s AND kcal IS NOT NULL",
                ("Global",),
            )
            global_with_kcal = int((cur.fetchone() or {}).get("c") or 0)
            cur.execute("SELECT COUNT(*) AS c FROM catalog_recipes")
            total = int((cur.fetchone() or {}).get("c") or 0)
    finally:
        conn.close()

    import xlrd

    sheet = xlrd.open_workbook(str(RECIPE_PATH)).sheet_by_index(0)
    xls_global = sum(
        1
        for r in range(1, sheet.nrows)
        if str(sheet.cell_value(r, 0)).strip() == "Global"
    )

    sample = to_add[0]
    print("=== RESULT ===")
    print(f"added_xls={len(to_add)}")
    print(f"mysql_inserted={mysql_ok} mysql_fail={mysql_fail}")
    print(f"xls_global_rows={xls_global} mysql_global={global_count} mysql_global_kcal={global_with_kcal} mysql_total={total}")
    print(f"sample={sample['name_zh']} kcal={sample['kcal']} recipe={sample['recipe']!r}")
    print(f"benefit={sample['benefit'][:80]!r}")
    print(f"method={sample['method']!r}")
    return 0 if mysql_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
