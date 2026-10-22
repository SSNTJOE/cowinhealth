# -*- coding: utf-8 -*-
"""Add ingredients that recipes had to substitute, using sourced fields."""
from __future__ import annotations

import os
import re

import xlrd
import xlwt

FOODS_PATH = r"C:\Tube\Health-ing\Foods.xls"
RECIPE_PATH = r"C:\Tube\Health-ing\Recipe.xls"
ORGANS = ["肝", "心", "脾", "肺", "腎", "膽", "小腸", "大腸", "膀胱"]
KINDS = ["實熱", "實寒", "虛熱", "虛寒"]

FISH = {
    "鯉魚", "鯽魚", "鱸魚", "草魚", "鰱魚", "青魚", "帶魚", "黃魚", "鯖魚", "鮪魚",
    "鮭魚", "鱈魚", "鯛魚", "秋刀魚", "沙丁魚", "鰻魚", "鱔魚", "泥鰍", "虱目魚",
    "石斑魚", "比目魚", "鯊魚", "白鯧", "烏魚", "鰹魚", "吳郭魚",
}
CRUSTACEAN = {"蝦", "蝦米", "龍蝦", "螃蟹"}
MOLLUSC = {
    "蛤蜊", "牡蠣", "蜆", "淡菜", "干貝", "鮑魚", "章魚", "魷魚", "烏賊",
    "海蜇", "田螺", "蟶子", "海參", "海膽",
}
EGG = {"雞蛋", "蛋白", "蛋黃", "鴨蛋", "皮蛋", "鵪鶉蛋"}
MILK = {"牛奶", "羊奶", "奶油", "起司", "優格"}
GLUTEN = {"小麥", "大麥", "燕麥"}
SOY = {"黃豆", "黑豆", "豆腐", "豆漿", "豆干", "腐竹", "納豆", "醬油", "毛豆", "黃豆芽", "味噌"}
PEANUT = {"花生", "花生油"}
NUT = {"杏仁果", "腰果", "夏威夷豆", "核桃", "松子", "栗子", "甜杏仁", "北杏仁", "白果"}
SEED = {"黑芝麻", "白芝麻", "麻油", "南瓜子", "葵花子", "亞麻仁"}
OTHER = {"蕎麥", "芹菜", "西洋芹", "芥末", "芥菜", "山葵", "醋", "黃酒", "葡萄酒"}
ALLERGENS = FISH | CRUSTACEAN | MOLLUSC | EGG | MILK | GLUTEN | SOY | PEANUT | NUT | SEED | OTHER


def syndromes(organs, benefit_kinds, ban_kinds):
    benefit, ban = [], []
    for organ in ORGANS:
        if organ not in organs:
            continue
        for kind in KINDS:
            token = organ + kind
            if kind in benefit_kinds:
                benefit.append(token)
            if kind in ban_kinds:
                ban.append(token)
    return ",".join(benefit), ",".join(ban)


def patterned(organs, code):
    if code == "N":
        return syndromes(organs, ["虛熱", "虛寒"], [])
    if code == "L":
        return syndromes(organs, ["實熱", "虛熱"], ["實寒", "虛寒"])
    if code == "C":
        return syndromes(organs, ["實熱"], ["實寒", "虛寒"])
    if code == "W":
        return syndromes(organs, ["虛寒"], ["實熱", "虛熱"])
    if code == "P":
        return syndromes(organs, ["實寒", "虛寒"], ["實熱", "虛熱"])
    raise ValueError(code)


NEW_FOODS = [
    ("鷹嘴豆", "chickpea", "ひよこ豆", "병아리콩", "N", ["脾", "腎"],
     "vitamins folate 172ug B6 0.1mg, enzymes none significant, fiber high 7.6g cooked, other protein 9g iron potassium"),
    ("紅腰豆", "kidney bean", "いんげん豆", "강낭콩", "N", ["脾", "腎"],
     "vitamins folate 130ug, enzymes none significant, fiber high 6.4g cooked, other protein 9g iron potassium"),
    ("大蕉", "plantain", "プランテン", "플랜틴", "L", ["脾", "肺"],
     "vitamins C 18mg A 56ug B6 0.3mg, enzymes none significant, fiber moderate 2.3g, other potassium 499mg starch"),
    ("麵包果", "breadfruit", "パンノキの実", "빵나무열매", "N", ["脾", "肝", "腎"],
     "vitamins C 29mg, enzymes none significant, fiber moderate 4.9g, other potassium starch"),
    ("可可", "cocoa", "ココア", "코코아", "N", ["肝", "脾", "膀胱"],
     "vitamins low, enzymes none significant, fiber high 37g powder, other protein 20g iron magnesium flavanols theobromine per 100g powder"),
    ("味噌", "miso", "味噌", "미소", "N", ["脾"],
     "vitamins K present B present, enzymes proteases, fiber moderate 5g, other protein 13g sodium isoflavones per 100g"),
    ("番紅花", "saffron", "サフラン", "사프란", "N", ["心", "肝"],
     "vitamins C present manganese present per 100g dried, enzymes none significant, fiber moderate, other crocin safranal"),
    ("橄欖油", "olive oil", "オリーブオイル", "올리브유", "N", ["心", "脾", "腎"],
     "vitamins E 14mg K 60ug, enzymes none significant, fiber none, other monounsaturated fat"),
    ("葡萄酒", "grape wine", "ワイン", "와인", "W", ["心", "肝"],
     "vitamins low, enzymes none significant, fiber none, other ethanol polyphenols"),
    ("火雞", "turkey", "七面鳥", "칠면조", "W", ["脾"],
     "vitamins B3 8mg B6 0.6mg B12 present, enzymes none significant, fiber none, other complete protein selenium phosphorus"),
    ("冬粉", "sweet potato glass noodle", "はるさめ", "당면", "N", ["脾", "腎"],
     "vitamins low, enzymes none significant, fiber low, other starch"),
    ("木薯葉", "cassava leaf", "キャッサバの葉", "카사바잎", "C", ["心"],
     "vitamins A present C present, enzymes none significant, fiber present, other protein"),
    ("兵豆", "lentil", "レンズ豆", "렌틸콩", "", [],
     "vitamins folate 181ug, enzymes none significant, fiber high 7.9g cooked, other protein 9g iron potassium"),
    ("木薯", "cassava", "キャッサバ", "카사바", "", [],
     "vitamins C 35mg B3 1.2mg B2 0.09mg, enzymes none significant, fiber 1.6g, other starch potassium 764mg protein 2.1g per 100g"),
]

RENAME = {
    ("Brunei", "樹薯粥"): {"芋頭": "木薯"},
    ("Central African Republic", "木薯泥配青菜"): {"芋頭": "木薯"},
    ("Ivory Coast", "木薯蒸粒"): {"芋頭": "木薯"},
    ("Liberia", "木薯糊"): {"芋頭": "木薯"},
    ("Togo", "木薯糊"): {"芋頭": "木薯"},
    ("Sierra Leone", "木薯葉燉"): {"地瓜葉": "木薯葉"},
    ("Niger", "木薯葉燉"): {"菠菜": "木薯葉"},
    ("Rwanda", "木薯葉燉"): {"菠菜": "木薯葉"},
    ("Saint Vincent and the Grenadines", "烤麵包果配魚"): {"地瓜": "麵包果"},
    ("Lebanon", "豌豆泥"): {"豌豆": "鷹嘴豆", "花生油": "橄欖油"},
    ("Israel", "鷹嘴豆泥球"): {"蠶豆": "鷹嘴豆"},
    ("Algeria", "古斯米雞肉"): {"豌豆": "鷹嘴豆"},
    ("Iran", "波斯燉菜"): {"扁豆": "紅腰豆"},
    ("Ethiopia", "扁豆辣醬"): {"扁豆": "兵豆"},
    ("India", "扁豆糊"): {"扁豆": "兵豆"},
    ("India", "豆泥拌飯"): {"扁豆": "兵豆"},
    ("Nepal", "扁豆配飯"): {"扁豆": "兵豆"},
    ("Egypt", "埃及雜炊"): {"扁豆": "兵豆"},
    ("Morocco", "扁豆湯"): {"扁豆": "兵豆"},
    ("Sri Lanka", "米飯咖哩"): {"扁豆": "兵豆"},
    ("Mauritius", "扁豆薄餅"): {"扁豆": "豌豆"},
    ("Japan", "味噌湯"): {"黃豆": "味噌"},
    ("South Korea", "雜菜"): {"地瓜": "冬粉"},
    ("Spain", "海鮮飯"): {"薑黃": "番紅花"},
    ("Greece", "優格黃瓜"): {"花生油": "橄欖油"},
    ("Greece", "烤魚"): {"花生油": "橄欖油"},
    ("Italy", "卡布里沙拉"): {"花生油": "橄欖油"},
    ("Italy", "海鮮麵"): {"花生油": "橄欖油"},
    ("Italy", "瑪格麗特披薩"): {"花生油": "橄欖油"},
    ("Italy", "青醬麵"): {"花生油": "橄欖油"},
    ("Spain", "冷湯"): {"花生油": "橄欖油"},
    ("Spain", "烤章魚"): {"花生油": "橄欖油"},
    ("Spain", "番茄麵包"): {"花生油": "橄欖油"},
    ("Spain", "蒜香蝦"): {"花生油": "橄欖油"},
    ("Spain", "西班牙蛋餅"): {"花生油": "橄欖油"},
    ("Portugal", "烤沙丁魚"): {"花生油": "橄欖油"},
    ("Portugal", "青菜湯"): {"花生油": "橄欖油"},
    ("Portugal", "鹽漬鱈魚"): {"花生油": "橄欖油"},
    ("Egypt", "蠶豆泥"): {"花生油": "橄欖油"},
    ("North Macedonia", "烤豆"): {"花生油": "橄欖油"},
    ("France", "紅酒燉雞"): {"黃酒": "葡萄酒"},
    ("France", "法式燉牛肉"): {"黃酒": "葡萄酒"},
    ("Italy", "米蘭燉飯"): {"黃酒": "葡萄酒"},
    ("Saint Lucia", "青香蕉鹹魚"): {"香蕉": "大蕉"},
    ("Costa Rica", "家常配餐"): {"香蕉": "大蕉"},
    ("Papua New Guinea", "地坑烤"): {"香蕉": "大蕉"},
}


def parse_recipe(text):
    pairs = []
    for part in str(text).split("、"):
        match = re.fullmatch(r"(.+) (\d+)克", part.strip())
        if not match:
            raise SystemExit("bad ingredient: " + part)
        pairs.append((match.group(1), int(match.group(2))))
    return pairs


def join_lookup(pairs, foods, field):
    parts = []
    for name, _gram in pairs:
        text = foods[name][field]
        if text:
            parts.append(f"{name}:{text}")
    return ";".join(parts)


def load_foods(sheet):
    foods = {}
    rows = []
    for row in range(1, sheet.nrows):
        values = [str(sheet.cell_value(row, col)).strip() for col in range(7)]
        rows.append(values)
        foods[values[0]] = {"benefit": values[4], "ban": values[5], "nutrient": values[6]}
    return foods, rows


def main():
    food_book = xlrd.open_workbook(FOODS_PATH)
    food_sheet = food_book.sheet_by_index(0)
    foods, food_rows = load_foods(food_sheet)
    added = 0
    for zh, en, ja, ko, code, organs, nutrient in NEW_FOODS:
        if zh in foods:
            continue
        if code:
            benefit, ban = patterned(organs, code)
        else:
            benefit, ban = "", ""
        food_rows.append([zh, en, ja, ko, benefit, ban, nutrient])
        foods[zh] = {"benefit": benefit, "ban": ban, "nutrient": nutrient}
        added += 1

    recipe_sheet = xlrd.open_workbook(RECIPE_PATH).sheet_by_index(0)
    headers = [recipe_sheet.cell_value(0, col) for col in range(10)]
    updated = 0
    out_rows = []
    seen = set()
    for row in range(1, recipe_sheet.nrows):
        values = [str(recipe_sheet.cell_value(row, col)).strip() for col in range(10)]
        key = (values[0], values[1])
        pairs = parse_recipe(values[5])
        changed = False
        if key in RENAME:
            mapping = RENAME[key]
            new_pairs = [(mapping.get(name, name), gram) for name, gram in pairs]
            if new_pairs != pairs:
                pairs = new_pairs
                changed = True
            seen.add(key)
        if key == ("Iran", "藏紅花烤肉飯") and not any(name == "番紅花" for name, _gram in pairs):
            pairs = [(name, gram - 8 if name == "粳米" else gram) for name, gram in pairs]
            pairs.append(("番紅花", 8))
            changed = True
            seen.add(key)
        if sum(gram for _, gram in pairs) != 500:
            raise SystemExit(f"sum {key} {sum(gram for _, gram in pairs)}")
        for name, _gram in pairs:
            if name not in foods:
                raise SystemExit(f"missing food {key} {name}")
        if changed:
            values[5] = "、".join(f"{name} {gram}克" for name, gram in pairs)
            values[6] = join_lookup(pairs, foods, "benefit")
            values[7] = join_lookup(pairs, foods, "ban")
            values[8] = join_lookup(pairs, foods, "nutrient")
            values[9] = "、".join(name for name, _gram in pairs if name in ALLERGENS)
            updated += 1
        out_rows.append(values)
    missing_keys = set(RENAME) - seen
    if missing_keys:
        raise SystemExit("unmatched dishes " + str(missing_keys))

    header_style = xlwt.easyxf(
        "font: name 微軟正黑體, bold on, height 240, colour white;"
        "align: horiz center, vert center, wrap on;"
        "pattern: pattern solid, fore_colour gray80;"
        "borders: left thin, right thin, top thin, bottom thin"
    )
    cell_style = xlwt.easyxf(
        "font: name 微軟正黑體, height 200;"
        "align: vert top, wrap on;"
        "borders: left thin, right thin, top thin, bottom thin"
    )
    food_out = xlwt.Workbook(encoding="utf-8")
    sheet = food_out.add_sheet("食材")
    food_headers = ["食材中文", "食材英文", "食材日文", "食材韓文", "益處", "禁忌", "元素表"]
    for col, header in enumerate(food_headers):
        sheet.write(0, col, header, header_style)
        sheet.col(col).width = 256 * (28 if col < 4 else 55)
    for row_index, values in enumerate(food_rows, start=1):
        for col, value in enumerate(values):
            sheet.write(row_index, col, value, cell_style)
    save_workbook(food_out, FOODS_PATH)

    recipe_out = xlwt.Workbook(encoding="utf-8")
    recipe = recipe_out.add_sheet("食譜")
    widths = [28, 22, 36, 28, 24, 78, 55, 55, 80, 28]
    for col, (header, width) in enumerate(zip(headers, widths)):
        recipe.write(0, col, header, header_style)
        recipe.col(col).width = 256 * width
    recipe.panes_frozen = True
    recipe.horz_split_pos = 1
    for row_index, values in enumerate(out_rows, start=1):
        for col, value in enumerate(values):
            recipe.write(row_index, col, value, cell_style)
    recipe_saved = save_workbook(recipe_out, RECIPE_PATH)
    print("foods", len(food_rows), "added", added, "recipes", len(out_rows), "updated", updated, "recipe", recipe_saved)


def save_workbook(book, path):
    tmp_path = path + ".new"
    book.save(tmp_path)
    try:
        os.replace(tmp_path, path)
        return path
    except OSError:
        return tmp_path


if __name__ == "__main__":
    main()
