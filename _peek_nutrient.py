# -*- coding: utf-8 -*-
import re
import zipfile
import xml.etree.ElementTree as ET

p = r"C:\Tube\Health-ing\daily_nutrient.xlsx"
z = zipfile.ZipFile(p)
ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
root = ET.fromstring(z.read("xl/sharedStrings.xml"))
ss = []
for si in root.findall("m:si", ns):
    texts = [x.text or "" for x in si.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")]
    ss.append("".join(texts))
sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
for row in sheet.findall("m:sheetData/m:row", ns):
    cells = []
    for c in row.findall("m:c", ns):
        v = c.find("m:v", ns)
        val = v.text if v is not None else ""
        if c.attrib.get("t") == "s" and val != "":
            val = ss[int(val)]
        cells.append(f"{c.attrib.get('r')}={val}")
    print(" | ".join(cells))
