# -*- coding: utf-8 -*-
import xlrd
from pathlib import Path

root = Path(r"C:\Tube\Health-ing")
watch = ["鷹嘴豆", "橄欖油", "味噌", "木薯", "木薯葉", "兵豆", "紅腰豆", "番紅花", "冬粉", "大蕉", "麵包果", "可可", "葡萄酒", "火雞"]
for name in ["Recipe.xls", "Recipe.xls.new"]:
    p = root / name
    st = p.stat()
    print("===", name, "size", st.st_size, "mtime", st.st_mtime)
    sh = xlrd.open_workbook(str(p)).sheet_by_index(0)
    headers = [str(sh.cell_value(0, c)).strip() for c in range(sh.ncols)]
    print("sheet", sh.name, "rows", sh.nrows, "cols", sh.ncols)
    print("headers", " | ".join(headers))
    tokens = set()
    for r in range(1, sh.nrows):
        recipe = str(sh.cell_value(r, 5)).strip()
        for part in recipe.split("、"):
            piece = part.strip()
            if " " in piece:
                tokens.add(piece.rsplit(" ", 1)[0])
    print("watch", {w: (w in tokens) for w in watch})
    print("row1", [str(sh.cell_value(1, c)).strip()[:40] for c in range(min(6, sh.ncols))])
