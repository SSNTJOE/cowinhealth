# -*- coding: utf-8 -*-
"""One-shot inspector for daily_nutrient.xlsx + Recipe.xls + port 8000."""
from __future__ import annotations

import subprocess
import sys

print("=== daily_nutrient.xlsx (openpyxl data_only=True) ===")
from openpyxl import load_workbook

wb = load_workbook(r"C:\tube\Health-ing\daily_nutrient.xlsx", data_only=True)
print("SHEET NAMES:", wb.sheetnames)
print()
for name in wb.sheetnames:
    ws = wb[name]
    print(f"=== SHEET: {name!r} (max_row={ws.max_row}, max_col={ws.max_column}) ===")
    for i, row in enumerate(ws.iter_rows(values_only=True), start=1):
        print(f"ROW {i}: {list(row)}")
    print()

print("=== Recipe.xls (xlrd) ===")
import xlrd

book = xlrd.open_workbook(r"C:\tube\Health-ing\Recipe.xls")
sheet = book.sheet_by_index(0)
print(f"sheets: {book.sheet_names()}")
print(f"nrows={sheet.nrows}, ncols={sheet.ncols}")
headers = [sheet.cell_value(0, c) for c in range(sheet.ncols)]
print("HEADERS (row 0):")
for i, h in enumerate(headers):
    print(f"  col {i}: {h!r}")

allergy_idx = None
for i, h in enumerate(headers):
    if "過敏原" in str(h):
        allergy_idx = i
        print(f"過敏原 column index: {i}")
        break

print()
if sheet.nrows > 1:
    print("FIRST DATA ROW (row 1):")
    for i in range(sheet.ncols):
        val = sheet.cell_value(1, i)
        print(f"  col {i} ({headers[i]!r}): {val!r}")
    if allergy_idx is not None:
        print()
        print("Nutrient numeric columns after 過敏原:")
        for i in range(allergy_idx + 1, sheet.ncols):
            val = sheet.cell_value(1, i)
            print(f"  col {i} ({headers[i]!r}): {val!r} type={type(val).__name__}")

print()
print("=== Port 8000 ===")
try:
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Format-Table -AutoSize | Out-String -Width 200; netstat -ano | Select-String ':8000'"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    print(r.stdout or "(no stdout)")
    if r.stderr:
        print("stderr:", r.stderr)
    print("exit:", r.returncode)
except Exception as exc:
    print("port check failed:", exc)

print()
print("=== DONE ===")
print("python:", sys.version)
