# -*- coding: utf-8 -*-
"""Fill blank Recipe.xls nutrient columns only, then sync blanks into MySQL catalog_recipes.

Uses tools/_fill_nutrients ingredient tables. Does not overwrite non-blank cells/rows.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import _fill_nutrients as fill  # noqa: E402

RECIPE_PATH = ROOT / "Recipe.xls"
HEADERS = fill.HEADERS


def _is_blank_cell(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _row_nutrients_blank(sheet, row: int, start: int) -> bool:
    for offset in range(len(HEADERS)):
        col = start + offset
        if col >= sheet.ncols:
            return True
        if not _is_blank_cell(sheet.cell_value(row, col)):
            return False
    return True


def fill_xls_blanks() -> dict:
    fill.ensure_deps()
    import xlrd
    import xlwt

    rb = xlrd.open_workbook(str(RECIPE_PATH))
    sheet = rb.sheet_by_index(0)
    headers = fill.existing_headers(sheet)
    start = fill.nutrient_start(headers)
    recipe_col = headers.index("食譜") if "食譜" in headers else 5
    name_col = headers.index("中文食譜") if "中文食譜" in headers else 1

    # Prefer xlutils to keep formatting; fall back to full xlwt rewrite.
    try:
        from xlutils.copy import copy as xl_copy

        rb_fmt = xlrd.open_workbook(str(RECIPE_PATH), formatting_info=True)
        sheet = rb_fmt.sheet_by_index(0)
        wb = xl_copy(rb_fmt)
        dest = wb.get_sheet(0)
        used = "xlutils"
        for offset, header in enumerate(HEADERS):
            dest.write(0, start + offset, header)
    except Exception:
        wb = xlwt.Workbook(encoding="utf-8")
        dest = wb.add_sheet(sheet.name or "Recipe")
        used = "xlwt"
        width = max(sheet.ncols, start + len(HEADERS))
        for col in range(width):
            dest.col(col).width = 256 * 18
        for col in range(sheet.ncols):
            dest.write(0, col, sheet.cell_value(0, col))
        for offset, header in enumerate(HEADERS):
            dest.write(0, start + offset, header)
        for row in range(1, sheet.nrows):
            for col in range(sheet.ncols):
                if start <= col < start + len(HEADERS):
                    continue
                value = fill.cell_write_value(sheet, row, col)
                if value is not None:
                    dest.write(row, col, value)
            # Preserve already-filled nutrient cells.
            if not _row_nutrients_blank(sheet, row, start):
                for offset in range(len(HEADERS)):
                    col = start + offset
                    if col < sheet.ncols:
                        value = fill.cell_write_value(sheet, row, col)
                        if value is not None:
                            dest.write(row, col, value)

    already = 0
    filled = 0
    unmatched = 0
    for row in range(1, sheet.nrows):
        if not _row_nutrients_blank(sheet, row, start):
            already += 1
            continue
        nums = fill.recipe_nutrients(
            str(sheet.cell_value(row, recipe_col)),
            str(sheet.cell_value(row, name_col)).strip(),
        )
        if nums is None:
            unmatched += 1
            continue
        filled += 1
        for offset, value in enumerate(nums):
            dest.write(row, start + offset, value)

    tmp = str(RECIPE_PATH) + f".tmp-{os.getpid()}"
    wb.save(tmp)
    os.replace(tmp, str(RECIPE_PATH))
    return {
        "total_rows": sheet.nrows - 1,
        "already_filled": already,
        "newly_filled": filled,
        "unmatched_blank": unmatched,
        "dict_size": len(fill.PER100G),
        "writer": used,
    }


def sync_mysql_blanks() -> dict:
    """Push nutrient values from Recipe.xls into catalog_recipes where MySQL nutrients are NULL."""
    import xlrd
    from app.db import connect
    from app.shared_catalog import NUTRIENT_FIELDS, _cell_number, _xls_cell, invalidate_recipe_mysql_cache

    sheet = xlrd.open_workbook(str(RECIPE_PATH)).sheet_by_index(0)
    headers = [str(sheet.cell_value(0, c)).strip() for c in range(sheet.ncols)]
    index = {name: i for i, name in enumerate(headers)}

    updates = 0
    skipped_no_match = 0
    skipped_already = 0
    skipped_blank_xls = 0

    set_clause = ", ".join(f"{field}=%s" for field, _ in NUTRIENT_FIELDS)
    # Prefer country+name_zh; fall back to name_zh only.
    sql_both = (
        f"UPDATE catalog_recipes SET {set_clause} "
        "WHERE country=%s AND name_zh=%s AND kcal IS NULL"
    )
    sql_name = (
        f"UPDATE catalog_recipes SET {set_clause} "
        "WHERE name_zh=%s AND (country IS NULL OR country='') AND kcal IS NULL"
    )

    conn = connect()
    try:
        with conn.cursor() as cur:
            for r in range(1, sheet.nrows):
                country = (
                    str(_xls_cell(sheet, r, index["國家"])).strip()
                    if "國家" in index
                    else ""
                )
                name_zh = (
                    str(_xls_cell(sheet, r, index["中文食譜"])).strip()
                    if "中文食譜" in index
                    else ""
                )
                if not name_zh:
                    continue
                nutrient_vals = []
                blank = True
                for field, header in NUTRIENT_FIELDS:
                    col = index.get(header)
                    val = None if col is None else _cell_number(_xls_cell(sheet, r, col))
                    nutrient_vals.append(val)
                    if val is not None:
                        blank = False
                if blank:
                    skipped_blank_xls += 1
                    continue
                if country:
                    cur.execute(sql_both, (*nutrient_vals, country, name_zh))
                else:
                    cur.execute(sql_name, (*nutrient_vals, name_zh))
                if cur.rowcount and cur.rowcount > 0:
                    updates += cur.rowcount
                else:
                    # Check whether row exists but already has kcal.
                    if country:
                        cur.execute(
                            "SELECT kcal FROM catalog_recipes WHERE country=%s AND name_zh=%s LIMIT 1",
                            (country, name_zh),
                        )
                    else:
                        cur.execute(
                            "SELECT kcal FROM catalog_recipes WHERE name_zh=%s LIMIT 1",
                            (name_zh,),
                        )
                    row = cur.fetchone()
                    if not row:
                        skipped_no_match += 1
                    elif row.get("kcal") is not None:
                        skipped_already += 1
                    else:
                        skipped_no_match += 1
        conn.commit()
    finally:
        conn.close()

    # Counts after sync
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM catalog_recipes")
            total = int((cur.fetchone() or {}).get("c") or 0)
            cur.execute("SELECT COUNT(*) AS c FROM catalog_recipes WHERE kcal IS NULL")
            null_kcal = int((cur.fetchone() or {}).get("c") or 0)
            cur.execute("SELECT COUNT(*) AS c FROM catalog_recipes WHERE kcal IS NOT NULL")
            with_kcal = int((cur.fetchone() or {}).get("c") or 0)
    finally:
        conn.close()

    invalidate_recipe_mysql_cache()
    return {
        "mysql_updated": updates,
        "mysql_skipped_already": skipped_already,
        "mysql_skipped_no_match": skipped_no_match,
        "mysql_skipped_blank_xls": skipped_blank_xls,
        "mysql_total": total,
        "mysql_with_kcal": with_kcal,
        "mysql_null_kcal": null_kcal,
    }


def main() -> None:
    print("=== fill Recipe.xls blanks ===")
    xls_stats = fill_xls_blanks()
    for k, v in xls_stats.items():
        print(f"xls {k}: {v}")
    print("=== sync MySQL blanks ===")
    db_stats = sync_mysql_blanks()
    for k, v in db_stats.items():
        print(f"db {k}: {v}")


if __name__ == "__main__":
    main()
