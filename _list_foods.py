# -*- coding: utf-8 -*-
import xlrd
from pathlib import Path

p = Path(r"C:\Tube\Health-ing\Foods.xls")
s = xlrd.open_workbook(str(p)).sheet_by_index(0)
headers = [str(s.cell_value(0, c)).strip() for c in range(s.ncols)]
print("ncols", s.ncols, "nrows", s.nrows)
print("HEADERS:", headers)
zh = headers.index("食材中文") if "食材中文" in headers else 0
kcal = headers.index("熱量(大卡)") if "熱量(大卡)" in headers else None
print("zh_col", zh, "kcal_col", kcal)
filled = blank = 0
lines = []
for r in range(1, s.nrows):
    name = str(s.cell_value(r, zh)).strip()
    if kcal is None:
        has = False
    else:
        v = s.cell_value(r, kcal)
        has = v != "" and v is not None
    mark = "F" if has else "B"
    if has:
        filled += 1
    else:
        blank += 1
    lines.append(f"{r:03d} {mark} {name}")
print("filled", filled, "blank", blank)
print("--- ALL NAMES ---")
print("\n".join(lines))
