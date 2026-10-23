# -*- coding: utf-8 -*-
import xlrd
from collections import Counter
from pathlib import Path

book = xlrd.open_workbook(r"C:\Tube\Health-ing\Recipe.xls.new")
sh = book.sheet_by_index(0)
lines = [
    f"sheets {book.nsheets} {book.sheet_names()}",
    f"nrows {sh.nrows} ncols {sh.ncols}",
]
countries = Counter()
rows = []
for r in range(1, sh.nrows):
    country = str(sh.cell_value(r, 0)).strip()
    zh = str(sh.cell_value(r, 1)).strip()
    en = str(sh.cell_value(r, 2)).strip()
    recipe = str(sh.cell_value(r, 5)).strip()
    countries[country] += 1
    rows.append(f"{r}\t{country}\t{zh}\t{en}\t{recipe}")
lines.append("countries " + str(len(countries)))
for c, n in countries.most_common():
    lines.append(f"{n}\t{c}")
lines.append("---ROWS---")
lines.extend(rows)
Path(r"C:\Tube\Health-ing\_dish_list.txt").write_text("\n".join(lines), encoding="utf-8")
print("wrote", len(rows))
