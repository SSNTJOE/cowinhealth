# -*- coding: utf-8 -*-
import json
import xlrd
from pathlib import Path

src = Path(r"C:\Tube\Health-ing\Recipe.xls.new")
sh = xlrd.open_workbook(str(src)).sheet_by_index(0)
rows = []
for r in range(1, sh.nrows):
    recipe = str(sh.cell_value(r, 5)).strip()
    pairs = []
    for part in recipe.split("、"):
        piece = part.strip()
        if not piece:
            continue
        name, gram = piece.rsplit(" ", 1)
        pairs.append([name, gram])
    rows.append({
        "i": r,
        "country": str(sh.cell_value(r, 0)).strip(),
        "zh": str(sh.cell_value(r, 1)).strip(),
        "en": str(sh.cell_value(r, 2)).strip(),
        "ings": pairs,
    })
Path(r"C:\Tube\Health-ing\_recipes_dump.json").write_text(
    json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8"
)
print("rows", len(rows))
print("countries", len({row["country"] for row in rows}))
# unique zh names
from collections import Counter
c = Counter(row["zh"] for row in rows)
print("unique zh", len(c))
print("--- names ---")
for name, n in c.most_common():
    print(f"{n}\t{name}")
