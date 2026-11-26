# -*- coding: utf-8 -*-
"""Fill blank Foods.xls nutrient columns only, then sync blanks into MySQL catalog_foods.

Uses tools/_fill_nutrients PER100G tables. Does not overwrite non-blank nutrient rows.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import _fill_nutrients as fill  # noqa: E402

FOODS_PATH = ROOT / "Foods.xls"
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

    rb = xlrd.open_workbook(str(FOODS_PATH))
    sheet = rb.sheet_by_index(0)
    headers = fill.existing_headers(sheet)
    start = fill.nutrient_start(headers)
    zh_col = headers.index("食材中文") if "食材中文" in headers else 0

    try:
        from xlutils.copy import copy as xl_copy

        rb_fmt = xlrd.open_workbook(str(FOODS_PATH), formatting_info=True)
        sheet = rb_fmt.sheet_by_index(0)
        wb = xl_copy(rb_fmt)
        dest = wb.get_sheet(0)
        used = "xlutils"
        for offset, header in enumerate(HEADERS):
            dest.write(0, start + offset, header)
    except Exception:
        wb = xlwt.Workbook(encoding="utf-8")
        dest = wb.add_sheet(sheet.name or "Foods")
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
        nums = fill.foods_nutrients(str(sheet.cell_value(row, zh_col)).strip())
        if nums is None:
            unmatched += 1
            continue
        filled += 1
        for offset, value in enumerate(nums):
            dest.write(row, start + offset, value)

    tmp = str(FOODS_PATH) + f".tmp-{os.getpid()}"
    wb.save(tmp)
    os.replace(tmp, str(FOODS_PATH))
    return {
        "total_rows": sheet.nrows - 1,
        "already_filled": already,
        "newly_filled": filled,
        "unmatched_blank": unmatched,
        "dict_size": len(fill.PER100G),
        "writer": used,
    }


def sync_mysql_blanks() -> dict:
    """Push nutrient values from Foods.xls into catalog_foods where MySQL kcal is NULL."""
    import xlrd
    from app.db import connect
    from app.shared_catalog import NUTRIENT_FIELDS, _cell_number, _xls_cell, invalidate_foods_mysql_cache

    sheet = xlrd.open_workbook(str(FOODS_PATH)).sheet_by_index(0)
    headers = [str(sheet.cell_value(0, c)).strip() for c in range(sheet.ncols)]
    index = {name: i for i, name in enumerate(headers)}

    updates = 0
    skipped_no_match = 0
    skipped_already = 0
    skipped_blank_xls = 0

    set_clause = ", ".join(f"{field}=%s" for field, _ in NUTRIENT_FIELDS)
    sql = (
        f"UPDATE catalog_foods SET {set_clause} "
        "WHERE name_zh=%s AND kcal IS NULL"
    )

    conn = connect()
    try:
        with conn.cursor() as cur:
            for r in range(1, sheet.nrows):
                name_zh = (
                    str(_xls_cell(sheet, r, index["食材中文"])).strip()
                    if "食材中文" in index
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
                cur.execute(sql, (*nutrient_vals, name_zh))
                if cur.rowcount and cur.rowcount > 0:
                    updates += cur.rowcount
                else:
                    cur.execute(
                        "SELECT kcal FROM catalog_foods WHERE name_zh=%s LIMIT 1",
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

    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM catalog_foods")
            total = int((cur.fetchone() or {}).get("c") or 0)
            cur.execute("SELECT COUNT(*) AS c FROM catalog_foods WHERE kcal IS NULL")
            null_kcal = int((cur.fetchone() or {}).get("c") or 0)
            cur.execute("SELECT COUNT(*) AS c FROM catalog_foods WHERE kcal IS NOT NULL")
            with_kcal = int((cur.fetchone() or {}).get("c") or 0)
    finally:
        conn.close()

    invalidate_foods_mysql_cache()
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
    print("=== fill Foods.xls blanks ===")
    xls_stats = fill_xls_blanks()
    for k, v in xls_stats.items():
        print(f"xls {k}: {v}")
    print("=== sync MySQL blanks ===")
    db_stats = sync_mysql_blanks()
    for k, v in db_stats.items():
        print(f"db {k}: {v}")


if __name__ == "__main__":
    main()
