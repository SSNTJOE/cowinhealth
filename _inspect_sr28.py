# -*- coding: utf-8 -*-
import openpyxl

wb = openpyxl.load_workbook(
    r"C:\Tube\Health-ing\_tmp_sr28\ABBREV.xlsx", read_only=True, data_only=True
)
ws = wb.active
it = ws.iter_rows(max_row=3, values_only=True)
header = next(it)
print("NCOLS", len(header))
for i, name in enumerate(header):
    print(i, name)
print("ROW1", next(it)[:20])
print("MAX_ROW", ws.max_row)
