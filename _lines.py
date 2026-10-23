# -*- coding: utf-8 -*-
import json
from pathlib import Path
rows = json.loads(Path(r"C:\Tube\Health-ing\_recipes_dump.json").read_text(encoding="utf-8"))
lines = []
for row in rows:
    ings = "、".join(f"{n}{g}" for n, g in row["ings"])
    lines.append(f"{row['i']}\t{row['country']}\t{row['zh']}\t{row['en']}\t{ings}")
Path(r"C:\Tube\Health-ing\_recipes_lines.txt").write_text("\n".join(lines), encoding="utf-8")
print(len(lines), "chars", sum(len(x) for x in lines))
