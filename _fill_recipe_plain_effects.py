"""Rewrite Recipe.xls 益處／禁忌 into plain teaching copy from Foods.xls (top-4 by grams).

Run:  python _fill_recipe_plain_effects.py
Safe to re-run. Organ-pattern filters still use Foods.xls tags via recipe ingredients.
"""

from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.recipe_ensure import FOODS_PATH, RECIPE_PATH, _cell, _save_xls, _xls_styles, active_recipe_path
from app.recipes import (
    COLUMN_FIELDS,
    invalidate_foods_cache,
    invalidate_recipe_cache,
    simplify_organ_effects,
)


def main() -> int:
    import xlrd
    import xlwt

    from app.recipe_ensure import ensure_food_effect_tags, load_food_name_index, parse_ingredient_text

    read_path = active_recipe_path()
    if not read_path.exists():
        print("missing Recipe.xls", file=sys.stderr)
        return 1
    if not FOODS_PATH.exists():
        print("missing Foods.xls", file=sys.stderr)
        return 1

    foods = load_food_name_index()
    book = xlrd.open_workbook(str(read_path))
    sheet = book.sheet_by_index(0)
    headers = [str(sheet.cell_value(0, col)).strip() for col in range(sheet.ncols)]
    header_to_field = {header: field for field, header in COLUMN_FIELDS}
    for _field, header in COLUMN_FIELDS:
        if header not in headers:
            print(f"missing column {header}", file=sys.stderr)
            return 1

    benefit_col = headers.index("益處")
    ban_col = headers.index("禁忌")
    recipe_col = headers.index("食譜")
    rows = [[_cell(sheet, row, col) for col in range(sheet.ncols)] for row in range(1, sheet.nrows)]

    # Prefill any blank Foods.xls tags used by recipes (guess + light wiki).
    all_pairs: list[tuple[str, int]] = []
    for values in rows:
        recipe_text = str(values[recipe_col] or "")
        all_pairs.extend(parse_ingredient_text(recipe_text))
    # Batch: guess missing Foods.xls tags without per-food wiki (create-on-miss still uses wiki).
    foods = ensure_food_effect_tags(all_pairs, foods, use_wiki=False)
    invalidate_foods_cache()

    changed = 0
    for values in rows:
        recipe_text = str(values[recipe_col] or "")
        plain_benefit, plain_ban = simplify_organ_effects(
            {"recipe": recipe_text, "benefit": "", "ban": ""},
            foods=foods,
        )
        if not plain_benefit and not plain_ban:
            continue
        before_b = str(values[benefit_col] or "").strip()
        before_n = str(values[ban_col] or "").strip()
        if plain_benefit and before_b != plain_benefit:
            values[benefit_col] = plain_benefit
            changed += 1
        if plain_ban and before_n != plain_ban:
            values[ban_col] = plain_ban
            changed += 1

    out = xlwt.Workbook(encoding="utf-8")
    out_sheet = out.add_sheet(sheet.name or "食譜")
    header_style, cell_style = _xls_styles()
    widths = [28, 22, 36, 28, 24, 78, 55, 55, 80, 28, 28]
    for col, header in enumerate(headers):
        out_sheet.write(0, col, header, header_style)
        out_sheet.col(col).width = 256 * (widths[col] if col < len(widths) else 28)
    out_sheet.panes_frozen = True
    out_sheet.horz_split_pos = 1
    for row_index, values in enumerate(rows, start=1):
        for col, value in enumerate(values):
            out_sheet.write(row_index, col, value, cell_style)

    _save_xls(out, RECIPE_PATH)
    invalidate_recipe_cache()
    invalidate_foods_cache()
    print(f"updated cells={changed} rows={len(rows)} path={active_recipe_path()}")
    # Show one sample
    sample = next((r for r in rows if "蛋餅" in str(r[headers.index("中文食譜")])), None)
    if sample is not None:
        print("sample 蛋餅 benefit:", sample[benefit_col])
        print("sample 蛋餅 ban:", sample[ban_col])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
