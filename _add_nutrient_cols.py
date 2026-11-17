# -*- coding: utf-8 -*-
"""Append 14 nutrient columns to Recipe.xls and Foods.xls; fill ~30 中文 matches."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
HEADERS = [
    "熱量(大卡)",
    "膳食纖維(克)",
    "鈣(克)",
    "鐵(克)",
    "鋅(克)",
    "碘(克)",
    "硒(克)",
    "維生素B(克)",
    "維生素C(克)",
    "維生素D(克)",
    "碳水化合物(克)",
    "蛋白質(克)",
    "脂質(克)",
    "水分(克)",
]
# Per 100 g: kcal, fiber g, Ca mg, Fe mg, Zn mg, I ug, Se ug, B mg, C mg, D ug, carb, protein, fat, water
RAW = {
    "白米": (360, 1.3, 9, 0.8, 1.1, 0, 15, 3.2, 0, 0, 79, 6.7, 0.6, 12),
    "糙米": (362, 3.5, 23, 1.5, 2.0, 0, 23, 6.5, 0, 0, 76, 7.5, 2.7, 12),
    "白飯": (130, 0.4, 3, 0.2, 0.4, 0, 8, 0.4, 0, 0, 28, 2.4, 0.3, 69),
    "雞蛋": (143, 0, 56, 1.8, 1.3, 50, 30, 2.2, 0, 2.0, 0.7, 13, 9.5, 76),
    "牛奶": (61, 0, 113, 0.03, 0.4, 20, 3.7, 0.5, 0, 0.1, 4.8, 3.2, 3.3, 88),
    "雞肉": (165, 0, 11, 0.9, 1.3, 6, 16, 8.0, 1.6, 0.2, 0, 20, 9, 70),
    "豬肉": (242, 0, 19, 0.9, 2.4, 1, 35, 6.5, 0.7, 0.6, 0, 17, 20, 62),
    "牛肉": (250, 0, 18, 2.6, 6.3, 2, 21, 6.0, 0, 0.1, 0, 26, 15, 58),
    "豆腐": (76, 0.3, 350, 1.6, 0.8, 0, 9, 0.5, 0.2, 0, 1.9, 8, 4.8, 85),
    "豆漿": (33, 0.4, 25, 0.5, 0.2, 0, 2, 0.3, 0, 0, 1.8, 3.3, 1.8, 93),
    "黃豆": (446, 9.3, 277, 16, 4.9, 0, 18, 6.5, 6, 0, 30, 36, 20, 8),
    "菠菜": (23, 2.2, 99, 2.7, 0.5, 0, 1.0, 1.2, 28, 0, 3.6, 2.9, 0.4, 91),
    "胡蘿蔔": (41, 2.8, 33, 0.3, 0.2, 0, 0.1, 0.8, 5.9, 0, 9.6, 0.9, 0.2, 88),
    "番茄": (18, 1.2, 10, 0.3, 0.2, 0, 0, 0.8, 14, 0, 3.9, 0.9, 0.2, 95),
    "洋蔥": (40, 1.7, 23, 0.2, 0.2, 0, 0.5, 0.3, 7.4, 0, 9.3, 1.1, 0.1, 89),
    "高麗菜": (25, 2.5, 40, 0.5, 0.2, 0, 0.3, 0.4, 37, 0, 5.8, 1.3, 0.1, 92),
    "大蒜": (149, 2.1, 181, 1.7, 1.2, 0, 14, 1.6, 31, 0, 33, 6.4, 0.5, 59),
    "香菇": (34, 2.5, 2, 0.4, 1.0, 0, 5.7, 4.0, 0, 0.4, 6.8, 2.2, 0.5, 90),
    "鮭魚": (208, 0, 12, 0.3, 0.6, 15, 36, 9.0, 0, 11, 0, 20, 13, 64),
    "蝦": (99, 0, 70, 0.5, 1.6, 35, 38, 2.5, 0, 0.1, 0.9, 24, 0.3, 75),
    "蘋果": (52, 2.4, 6, 0.1, 0.04, 0, 0, 0.2, 4.6, 0, 14, 0.3, 0.2, 86),
    "香蕉": (89, 2.6, 5, 0.3, 0.2, 0, 1.0, 0.7, 8.7, 0, 23, 1.1, 0.3, 75),
    "花生": (567, 8.5, 92, 4.6, 3.3, 0, 7.2, 14, 0, 0, 16, 26, 49, 7),
    "食鹽": (0, 0, 24, 0.3, 0.1, 4500, 0.1, 0, 0, 0, 0, 0, 0, 0),
    "醬油": (53, 0.8, 20, 1.4, 0.4, 2, 0.5, 2.5, 0, 0, 4.9, 8.1, 0.1, 71),
    "麻油": (884, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 100, 0),
    "白糖": (387, 0, 1, 0.05, 0.01, 0, 0.6, 0, 0, 0, 100, 0, 0, 0.2),
    "優格": (61, 0, 121, 0.05, 0.6, 15, 3.0, 0.4, 0.5, 0.1, 4.7, 3.5, 3.3, 88),
    "海帶": (43, 1.3, 168, 2.8, 1.2, 24000, 0.5, 0.5, 3, 0, 9, 1.7, 0.6, 82),
    "麵粉": (340, 12, 34, 3.6, 2.6, 0, 70, 6.0, 0, 0, 72, 13, 2.5, 11),
}
ALIASES = {
    "粳米": "白米",
    "白米飯": "白米",
    "米飯": "白米",
    "米": "白米",
    "飯": "白飯",
    "蛋": "雞蛋",
    "鮮奶": "牛奶",
    "牛乳": "牛奶",
    "雞胸": "雞肉",
    "雞腿": "雞肉",
    "里肌": "豬肉",
    "絞肉": "豬肉",
    "嫩豆腐": "豆腐",
    "板豆腐": "豆腐",
    "紅蘿蔔": "胡蘿蔔",
    "鮭": "鮭魚",
    "草蝦": "蝦",
    "白蝦": "蝦",
    "蝦仁": "蝦",
    "鹽": "食鹽",
    "鹽巴": "食鹽",
    "香油": "麻油",
    "糖": "白糖",
    "砂糖": "白糖",
    "小麥": "麵粉",
    "大豆": "黃豆",
    "昆布": "海帶",
}
TO_G = (1, 1, 1 / 1000, 1 / 1000, 1 / 1000, 1 / 1_000_000, 1 / 1_000_000, 1 / 1000, 1 / 1000, 1 / 1_000_000, 1, 1, 1, 1)
DIGITS = (1, 2, 4, 4, 4, 7, 7, 6, 4, 8, 2, 2, 2, 2)


def to_grams(raw):
    return [round(raw[i] * TO_G[i], DIGITS[i]) for i in range(14)]


def lookup(name: str):
    key = (name or "").strip()
    if not key:
        return None
    if key in RAW:
        return to_grams(RAW[key])
    mapped = ALIASES.get(key)
    if mapped:
        return to_grams(RAW[mapped])
    return None


def zh_col(headers):
    for cand in ("食材中文", "中文", "中文食譜"):
        if cand in headers:
            return headers.index(cand)
    return 0


def print_book(path, n=3):
    import xlrd

    sheet = xlrd.open_workbook(path).sheet_by_index(0)
    headers = [str(sheet.cell_value(0, c)).strip() for c in range(sheet.ncols)]
    print(f"=== {os.path.basename(path)} nrows={sheet.nrows} ncols={sheet.ncols} ===")
    print("HEADERS:", headers)
    for r in range(1, min(sheet.nrows, n + 1)):
        row = [sheet.cell_value(r, c) for c in range(sheet.ncols)]
        print(f"ROW{r}:", row)


def rewrite(path):
    import xlrd
    import xlwt

    book = xlrd.open_workbook(path)
    sheet = book.sheet_by_index(0)
    headers = [str(sheet.cell_value(0, c)).strip() for c in range(sheet.ncols)]
    name_i = zh_col(headers)
    if HEADERS[0] in headers:
        start = headers.index(HEADERS[0])
        keep = start
    else:
        start = sheet.ncols
        keep = sheet.ncols
    used = "xlwt"
    try:
        from xlutils.copy import copy as xl_copy

        rb = xlrd.open_workbook(path, formatting_info=True)
        src = rb.sheet_by_index(0)
        wb = xl_copy(rb)
        dest = wb.get_sheet(0)
        for offset, header in enumerate(HEADERS):
            dest.write(0, start + offset, header)
        filled = 0
        blank = 0
        for row in range(1, src.nrows):
            nums = lookup(str(src.cell_value(row, name_i)))
            if nums is None:
                blank += 1
                continue
            filled += 1
            for offset, value in enumerate(nums):
                dest.write(row, start + offset, value)
        used = "xlutils"
        tmp = path + ".tmp"
        wb.save(tmp)
        os.replace(tmp, path)
        return filled, blank, used, start
    except Exception as exc:
        print("xlutils fallback:", type(exc).__name__, exc)
        out = xlwt.Workbook(encoding="utf-8")
        dest = out.add_sheet(sheet.name or "Sheet1")
        for col in range(keep):
            dest.write(0, col, sheet.cell_value(0, col))
        for offset, header in enumerate(HEADERS):
            dest.write(0, start + offset, header)
        filled = 0
        blank = 0
        for row in range(1, sheet.nrows):
            for col in range(keep):
                dest.write(row, col, sheet.cell_value(row, col))
            nums = lookup(str(sheet.cell_value(row, name_i)))
            if nums is None:
                blank += 1
                continue
            filled += 1
            for offset, value in enumerate(nums):
                dest.write(row, start + offset, value)
        tmp = path + ".tmp"
        out.save(tmp)
        os.replace(tmp, path)
        return filled, blank, used, start


def main():
    try:
        import xlrd  # noqa: F401
        import xlwt  # noqa: F401
    except ImportError:
        import subprocess

        subprocess.check_call([sys.executable, "-m", "pip", "install", "xlrd==1.2.0", "xlwt", "xlutils"])

    for name in ("Recipe.xls", "Foods.xls"):
        path = os.path.join(ROOT, name)
        print_book(path, 1)
        filled, blank, used, start = rewrite(path)
        print(f"{name}: filled={filled} blank={blank} via={used} start_col={start}")
        print_book(path, 3)


if __name__ == "__main__":
    main()
