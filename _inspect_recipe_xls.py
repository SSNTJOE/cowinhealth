# -*- coding: utf-8 -*-
"""Append Recipe.xls nutrient header/sample dump to _nutrient_inspect_out.txt."""
from pathlib import Path
import xlrd

root = Path(r"C:\tube\Health-ing")
out_path = root / "_nutrient_inspect_out.txt"
xls = root / "Recipe.xls"

lines = []
lines.append("")
lines.append("=" * 60)
lines.append(f"FILE: {xls} (xlrd direct)")
lines.append(f"exists: {xls.exists()} size={xls.stat().st_size}")
lines.append("=" * 60)

book = xlrd.open_workbook(str(xls))
lines.append(f"sheets: {book.sheet_names()}")
sheet = book.sheet_by_index(0)
lines.append(f"sheet0 name={sheet.name!r} nrows={sheet.nrows} ncols={sheet.ncols}")

headers = [sheet.cell_value(0, c) for c in range(sheet.ncols)]
lines.append("HEADERS (row 0):")
for i, h in enumerate(headers):
    lines.append(f"  col {i}: {h!r}")

nutrient_kw = [
    "熱量",
    "膳食纖維",
    "纖維",
    "蛋白",
    "脂肪",
    "脂質",
    "碳水",
    "糖",
    "鈉",
    "鈣",
    "鐵",
    "鋅",
    "碘",
    "硒",
    "維生",
    "水分",
    "nutrient",
    "calori",
    "fiber",
    "protein",
    "fat",
    "carb",
    "sodium",
]
nutrient_cols = [
    i for i, h in enumerate(headers) if any(k in str(h) for k in nutrient_kw)
]
lines.append("")
lines.append(
    "NUTRIENT-RELATED COLUMN INDICES: "
    + (
        ", ".join(f"{i}:{headers[i]!r}" for i in nutrient_cols)
        if nutrient_cols
        else "(none matched keywords)"
    )
)

sample_n = min(2, max(0, sheet.nrows - 1))
lines.append(f"\nSample first {sample_n} data rows — nutrient numeric columns:")
for r in range(1, sample_n + 1):
    lines.append(f"--- data row {r} ---")
    # also print identifying cols if present
    for c in range(min(5, sheet.ncols)):
        lines.append(f"  col {c} ({headers[c]!r}): {sheet.cell_value(r, c)!r}")
    if nutrient_cols:
        for c in nutrient_cols:
            val = sheet.cell_value(r, c)
            lines.append(
                f"  NUTRIENT col {c} ({headers[c]!r}): {val!r} "
                f"(type={type(val).__name__})"
            )
    else:
        # fallback: dump all numeric-looking columns after allergy if any
        allergy_idx = next(
            (i for i, h in enumerate(headers) if "過敏原" in str(h)), None
        )
        start = (allergy_idx + 1) if allergy_idx is not None else 0
        lines.append(
            f"(no keyword nutrient cols; dumping cols from {start} onward)"
        )
        for c in range(start, sheet.ncols):
            val = sheet.cell_value(r, c)
            lines.append(
                f"  col {c} ({headers[c]!r}): {val!r} (type={type(val).__name__})"
            )

lines.append("")
lines.append("=" * 60)
lines.append("MEAL FEATURE CODE CHECK (confirmed)")
lines.append("=" * 60)
lines.append("user_meals: NONE")
lines.append("meal_calendar: NONE")
lines.append("nutrient_targets: NONE")
lines.append(
    "Also no *meal* filename matches under workspace; no code refs to those module names."
)

# Rewrite full file: keep existing daily_nutrient dump, replace Recipe section
existing = out_path.read_text(encoding="utf-8", errors="replace")
marker = "FILE: C:\\tube\\Health-ing\\Recipe.xls"
idx = existing.find("=" * 60 + "\n" + marker)
if idx == -1:
    # try alternate marker
    idx = existing.find("FILE: C:\\tube\\Health-ing\\Recipe.xls")
    if idx != -1:
        # back up to previous ==== line
        prev = existing.rfind("=" * 60, 0, idx)
        idx = prev if prev != -1 else idx

if idx != -1:
    daily_part = existing[:idx].rstrip() + "\n"
else:
    daily_part = existing.rstrip() + "\n"

full = daily_part + "\n".join(lines) + "\n"
out_path.write_text(full, encoding="utf-8")
print("Wrote", out_path)
print("nutrient_cols:", nutrient_cols)
print("headers count:", len(headers))
for i in nutrient_cols:
    print(f"  {i}: {headers[i]}")
