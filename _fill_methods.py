# -*- coding: utf-8 -*-
"""Add a 煮法 column to Recipe.xls from the newer ingredient workbook."""
from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path

import xlrd
import xlwt

ROOT = Path(r"C:\Tube\Health-ing")
WATCH = ("鷹嘴豆", "橄欖油", "味噌", "木薯")
TARGET_HEADERS = [
    "國家",
    "中文食譜",
    "英文食譜",
    "日文食譜",
    "韓文食譜",
    "食譜",
    "煮法",
    "益處",
    "禁忌",
    "元素",
    "過敏原",
]

OIL = {"花生油", "麻油", "橄欖油"}
SALTY = {"食鹽", "醬油"}
SWEET = {"白糖", "冰糖", "黑糖", "蜂蜜"}
ACID = {"醋", "檸檬", "柳橙"}
HEAT = {"胡椒", "辣椒", "花椒", "芥末", "山葵"}
SPICE = {"肉桂", "豆蔻", "薑黃", "八角", "月桂葉", "小茴香", "番紅花", "香茅", "百里香", "迷迭香"}
AROMATIC = {"洋蔥", "大蒜", "蔥", "生薑", "芹菜", "韭菜"}
HERB = {"香菜", "羅勒", "薄荷", "魚腥草"}
LIQUID = {"牛奶", "椰子汁", "優格", "葡萄酒", "黃酒", "味噌", "紅茶", "綠茶"}
DAIRY = {"奶油", "起司"}
LEGUME = {"鷹嘴豆", "紅豆", "黑豆", "菜豆", "豌豆", "蠶豆", "扁豆", "紅腰豆", "兵豆", "黃豆", "花生"}
GARNISH = {
    "葡萄乾", "松子", "杏仁果", "核桃", "白芝麻", "南瓜子", "夏威夷豆",
    "紫菜", "芒果", "草莓", "奇異果", "蘋果", "梅子", "杏子", "石榴", "紅棗",
    "栗子", "人參", "枸杞", "橄欖", "油橄欖", "椰子肉", "蝦米",
}
FLOUR = {"小麥"}
GRAIN = {"粳米", "糯米", "糙米", "小米", "玉米", "燕麥", "大麥", "高粱", "冬粉", "蕎麥", "麵包果"}
ROOT_VEG = {"馬鈴薯", "地瓜", "芋頭", "木薯", "大蕉", "香蕉"}
PROTEIN_BITS = (
    "肉", "魚", "蝦", "蟹", "蛋", "豆腐", "雞", "鴨", "肝", "腸", "蹄",
    "火腿", "豆干", "牡蠣", "魷", "章", "鮭", "鱈", "鯛", "鯉", "鱸", "鮪",
    "石斑", "沙丁", "虱目", "龍蝦", "淡菜", "蛤", "貝",
)


def choose_source() -> Path:
    new_path = ROOT / "Recipe.xls.new"
    old_path = ROOT / "Recipe.xls"

    def has_watch(path: Path) -> bool:
        if not path.exists():
            return False
        sheet = xlrd.open_workbook(str(path)).sheet_by_index(0)
        recipe_col = 5
        headers = [str(sheet.cell_value(0, col)).strip() for col in range(sheet.ncols)]
        if "食譜" in headers:
            recipe_col = headers.index("食譜")
        blob = "\n".join(str(sheet.cell_value(row, recipe_col)) for row in range(1, sheet.nrows))
        return all(token in blob for token in WATCH)

    if has_watch(new_path) and not has_watch(old_path):
        return new_path
    if old_path.exists() and has_watch(old_path):
        return old_path
    if new_path.exists():
        return new_path
    return old_path


def parse_recipe(text: str) -> list[tuple[str, int]]:
    items: list[tuple[str, int]] = []
    for part in (text or "").split("、"):
        piece = part.strip()
        if not piece:
            continue
        name, amount = piece.rsplit(" ", 1)
        items.append((name.strip(), int(amount.replace("克", "").strip())))
    return items


def role_of(name: str) -> str:
    if name in OIL:
        return "oil"
    if name in SALTY:
        return "salty"
    if name in SWEET:
        return "sweet"
    if name in ACID:
        return "acid"
    if name in HEAT:
        return "heat"
    if name in SPICE:
        return "spice"
    if name in AROMATIC:
        return "aromatic"
    if name in HERB:
        return "herb"
    if name in LIQUID or name == "茶":
        return "liquid"
    if name in DAIRY:
        return "dairy"
    if name in LEGUME:
        return "legume"
    if name in GARNISH:
        return "garnish"
    if name in FLOUR:
        return "flour"
    if name in GRAIN:
        return "grain"
    if name in ROOT_VEG:
        return "root"
    if name == "木薯葉":
        return "veg"
    if any(bit in name for bit in PROTEIN_BITS):
        return "protein"
    return "veg"


def group_items(items: list[tuple[str, int]]) -> dict[str, list[tuple[str, int]]]:
    groups: dict[str, list[tuple[str, int]]] = {}
    for name, amount in items:
        groups.setdefault(role_of(name), []).append((name, amount))
    return groups


def grams(items: list[tuple[str, int]]) -> str:
    return "、".join(f"{name}{amount}克" for name, amount in items)


class Bag:
    def __init__(self, groups: dict[str, list[tuple[str, int]]]):
        self.groups = {key: list(value) for key, value in groups.items()}

    def pull_items(self, *roles: str) -> list[tuple[str, int]]:
        items: list[tuple[str, int]] = []
        for role in roles:
            items.extend(self.groups.get(role) or [])
            self.groups[role] = []
        return items

    def pull(self, *roles: str) -> str:
        return grams(self.pull_items(*roles))

    def leftover(self) -> str:
        items: list[tuple[str, int]] = []
        for role in list(self.groups):
            items.extend(self.groups[role])
            self.groups[role] = []
        return grams(items)


def join_steps(parts: list[str], zh: str, bag: Bag) -> str:
    steps = [part for part in parts if part]
    extra_items: list[tuple[str, int]] = []
    for role in list(bag.groups):
        extra_items.extend(bag.groups[role])
        bag.groups[role] = []
    if extra_items:
        text = grams(extra_items)
        roles = {role_of(name) for name, _amount in extra_items}
        if roles <= {"acid"} or roles <= {"acid", "herb"}:
            steps.append(f"最後淋上{text}")
        elif roles <= {"herb", "garnish"}:
            steps.append(f"最後撒上{text}")
        else:
            steps.append(f"最後加入{text}")
    steps.append(f"即成{zh}")
    return "；".join(steps)


def has_any(text: str, *keys: str) -> bool:
    lowered = text.lower()
    for key in keys:
        token = key.lower()
        if any(ord(ch) > 127 for ch in token):
            if token in lowered:
                return True
            continue
        if re.search(rf"(?<![a-z]){re.escape(token)}(?![a-z])", lowered):
            return True
    return False


def technique_for(zh: str, en: str) -> str:
    text = f"{zh} {en}"
    if has_any(text, "奶茶", "milk tea"):
        return "drink"
    if has_any(text, "冷湯", "gazpacho", "cold beet"):
        return "cold_soup"
    if has_any(text, "醃魚", "ceviche", "酸魚", "kokoda", "ota ika"):
        return "raw_fish"
    if has_any(text, "火鍋", "壽喜燒", "sukiyaki", "hot pot"):
        return "hotpot"
    if has_any(text, "fondue", "起司火鍋"):
        return "fondue"
    if has_any(text, "糯米飯", "sticky rice"):
        return "sticky_sweet"
    if has_any(text, "茶泡飯"):
        return "tea_rice"
    if has_any(text, "壽司", "飯糰", "紫菜飯包", "sushi", "kimbap"):
        return "sushi"
    if has_any(text, "肉粽", "粽"):
        return "zongzi"
    if has_any(text, "蘿蔔糕"):
        return "steam_cake"
    if has_any(text, "春捲", "spring roll"):
        return "spring_roll"
    if has_any(text, "煎餃"):
        return "dumpling_pan"
    if has_any(text, "雲吞麵", "wonton noodle"):
        return "wonton_noodle"
    if has_any(text, "餡餅", "empanada", "pasty", "samosa", "炸餃"):
        return "filled_pastry"
    if has_any(text, "餃", "雲吞", "燒賣", "小籠", "wonton", "dumpling", "pierogi", "pelmeni", "varenyky", "buuz"):
        return "dumpling"
    if has_any(text, "沙拉", "涼拌", "salad"):
        return "salad"
    if has_any(text, "泥", "guacamole", "酪梨醬", "優格黃瓜"):
        return "mash"
    if has_any(text, "蛋餅", "烘蛋", "shakshuka", "北非蛋", "蚵仔煎", "雞蛋薯條", "chipsi"):
        return "egg_pan"
    if has_any(text, "煎餅", "可麗", "華夫", "鬆餅", "薄餅", "crepe", "waffle", "pancake", "blini", "okonomiyaki", "大阪燒"):
        return "griddle"
    if has_any(text, "炒飯", "fried rice", "nasi goreng"):
        return "fried_rice"
    if has_any(text, "燉飯", "risotto"):
        return "risotto"
    if has_any(text, "海鮮飯", "paella"):
        return "paella"
    if has_any(text, "古斯米", "couscous"):
        return "couscous"
    if has_any(text, "麵包", "bread") and has_any(text, "烤", "腸", "三明治"):
        return "sandwich"
    if has_any(text, "麵包", "麵團", "bread"):
        return "bake"
    if has_any(text, "麵", "河粉", "米粉", "冬粉", "粿條", "雜菜", "noodle", "pasta", "ramen", "udon", "soba", "pho", "pad thai", "pancit", "laksa", "叻沙", "mohinga", "炸醬", "卡波納拉", "carbonara"):
        return "noodle"
    if has_any(text, "粥", "congee", "porridge"):
        return "porridge"
    if has_any(text, "扁豆糊", "dal"):
        return "braise"
    if has_any(text, "玉米糊", "木薯糊", "木薯泥", "高粱糊", "ugali", "fufu", "nsima", "sadza", "papa", "dhido", "asida"):
        return "swallow"
    if has_any(text, "湯", "羹", "soup", "sinigang", "tom yum", "冬蔭功", "borscht", "gumbo", "chowder", "巧達"):
        return "soup"
    if has_any(text, "咖哩", "curry"):
        return "curry"
    if has_any(text, "糖醋"):
        return "sweet_sour"
    if has_any(text, "麻婆"):
        return "mapo"
    if has_any(text, "白切", "海南") and not has_any(text, "飯", "丼", "rice"):
        return "poach"
    if has_any(text, "飯", "丼", "rice") and has_any(text, "炸"):
        return "fry_bowl"
    if has_any(text, "飯", "丼", "rice") and has_any(text, "叉燒", "燒味", "烤", "滷", "海南", "白切"):
        return "rice_top"
    if has_any(text, "茶葉蛋"):
        return "simmer_egg"
    if has_any(text, "皮蛋豆腐", "穀片", "muesli", "醃鯡", "kama"):
        return "cold_plate"
    if has_any(text, "茶碗蒸"):
        return "steam_egg"
    if has_any(text, "蒸"):
        return "steam"
    if has_any(text, "淡菜", "moules"):
        return "mussels"
    if has_any(text, "薯條", "poutine", "frites"):
        return "fries"
    if has_any(text, "炸", "鹽酥", "天婦羅", "tempura", "schnitzel", "豬排", "breaded", "肉丸", "meatball"):
        return "deep_fry"
    if has_any(text, "串", "satay", "沙嗲", "kebab", "kebap", "souvlaki", "yakitori", "cevapi", "切瓦皮"):
        return "skewer"
    if has_any(text, "紅燒"):
        return "braise"
    if has_any(text, "烤", "roast", "roasted", "grill", "grilled", "asado", "braai", "jerk", "lechon", "mechoui", "shuwa", "kleftiko", "bulgogi", "叉燒", "燒味", "香腸", "sausage", "bratwurst"):
        return "roast"
    if has_any(text, "抓飯", "pulao", "plov", "palaw", "biryani", "kabsa", "machboos", "jollof", "手抓飯", "香料飯", "卡布薩", "油米飯"):
        return "pilaf"
    if has_any(text, "慕沙卡", "moussaka"):
        return "bake"
    if has_any(text, "三明治", "漢堡", "豬扒包", "刈包", "banh mi", "burger", "sandwich", "shawarma", "烤肉捲", "taco", "夾餅", "quesadilla", "pupusa", "baleada", "皮塔", "pita"):
        return "sandwich"
    if has_any(text, "肉餅", "餡餅", "empanada", "pasty", "samosa", "炸餃"):
        return "filled_pastry"
    if has_any(text, "派", "撻", "pizza", "披薩", "quiche", "pie", "tart", "蛋糕", "cake", "pavlova", "蛋白霜", "strudel", "蘋果卷", "麵包", "khachapuri"):
        return "bake"
    if has_any(text, "飯", "rice", "丼"):
        return "rice_top"
    if has_any(text, "泡菜", "kimchi") and not has_any(text, "鍋", "stew", "湯"):
        return "ferment"
    if has_any(text, "豆餅", "patty", "patties"):
        return "griddle"
    if has_any(text, "雜炊", "koshari"):
        return "pilaf"
    if has_any(text, "肉骨茶", "bak kut teh"):
        return "soup"
    if has_any(text, "照燒", "teriyaki"):
        return "roast"
    if has_any(text, "早餐", "breakfast"):
        return "egg_pan"
    if has_any(text, "紅椒雞", "paprikash", "牛腩"):
        return "braise"
    if has_any(text, "炒", "煸", "煎", "回鍋", "宮保", "魚香", "木須", "打拋", "羅勒", "basil", "青椒", "蒜蓉", "肉絲", "西西格", "sisig", "蒜香"):
        return "stir"
    if has_any(text, "燉", "滷", "煲", "燜", "stew", "rendang", "仁當", "tagine", "goulash", "adobo", "wat", "feijoada", "carbonade", "三杯", "薑母", "鍋", "肉卷", "sarmale"):
        return "braise"
    return "fallback"


def method_for(zh: str, en: str, items: list[tuple[str, int]]) -> str:
    tech = technique_for(zh, en)
    if tech == "fallback":
        tech = fallback_technique(zh, en, items)
    bag = Bag(group_items(items))
    builders = {
        "drink": drink,
        "cold_soup": cold_soup,
        "raw_fish": raw_fish,
        "hotpot": hotpot,
        "fondue": fondue,
        "sticky_sweet": sticky_sweet,
        "tea_rice": tea_rice,
        "sushi": sushi,
        "zongzi": zongzi,
        "steam_cake": steam_cake,
        "spring_roll": spring_roll,
        "dumpling_pan": lambda bag, zh: dumpling(bag, zh, "平鍋少油煎至底面金黃"),
        "wonton_noodle": wonton_noodle,
        "dumpling": lambda bag, zh: dumpling(bag, zh, "包好後蒸或煮至浮起"),
        "salad": salad,
        "mash": mash,
        "egg_pan": egg_pan,
        "griddle": griddle,
        "fried_rice": fried_rice,
        "risotto": risotto,
        "paella": paella,
        "couscous": couscous,
        "noodle": noodle,
        "porridge": porridge,
        "swallow": swallow,
        "soup": soup,
        "curry": curry,
        "sweet_sour": sweet_sour,
        "mapo": mapo,
        "poach": poach,
        "simmer_egg": simmer_egg,
        "cold_plate": cold_plate,
        "steam_egg": steam_egg,
        "steam": steam,
        "deep_fry": deep_fry,
        "fry_bowl": fry_bowl,
        "mussels": mussels,
        "fries": fries,
        "skewer": skewer,
        "roast": roast,
        "pilaf": pilaf,
        "sandwich": sandwich,
        "filled_pastry": filled_pastry,
        "bake": bake,
        "rice_top": rice_top,
        "ferment": ferment,
        "stir": stir,
        "braise": braise,
    }
    return builders[tech](bag, zh)


def fallback_technique(zh: str, en: str, items: list[tuple[str, int]]) -> str:
    groups = group_items(items)
    flour_g = sum(amount for _name, amount in groups.get("flour") or [])
    protein_g = sum(amount for _name, amount in groups.get("protein") or [])
    peanut_g = sum(amount for name, amount in items if name == "花生")
    if groups.get("grain") and groups.get("protein"):
        return "rice_top"
    if peanut_g >= 50 and groups.get("protein"):
        return "braise"
    if flour_g >= 120 and flour_g >= protein_g and not has_any(f"{zh} {en}", "派", "餅", "撻", "蛋糕"):
        return "noodle"
    if groups.get("protein") and groups.get("root"):
        return "braise"
    if groups.get("dairy") and groups.get("veg") and not groups.get("protein"):
        return "braise"
    if groups.get("protein") and (groups.get("veg") or groups.get("aromatic")) and not groups.get("liquid"):
        return "stir"
    if groups.get("protein") and (groups.get("veg") or groups.get("aromatic")):
        return "braise"
    if groups.get("legume"):
        return "braise"
    if groups.get("veg"):
        return "stir"
    if groups.get("protein"):
        return "roast"
    return "stir"


def drink(bag: Bag, zh: str) -> str:
    liquids = bag.pull_items("liquid")
    tea = grams([item for item in liquids if "茶" in item[0]])
    milk = grams([item for item in liquids if "茶" not in item[0]])
    sweet = bag.pull("sweet")
    dairy = bag.pull("dairy")
    steps = []
    if tea:
        steps.append(f"{tea}以熱水沖開")
    rest = "、".join(part for part in (milk, dairy, sweet) if part)
    if rest:
        steps.append(("沖入" if tea else "加熱拌入") + rest)
    return join_steps(steps, zh, bag)


def cold_soup(bag: Bag, zh: str) -> str:
    body = bag.pull("veg", "garnish", "acid", "oil", "aromatic")
    season = bag.pull("salty", "heat", "spice", "liquid", "dairy", "sweet")
    steps = []
    if body:
        steps.append(f"{body}打勻後冰鎮")
    if season:
        steps.append(f"以{season}調味")
    return join_steps(steps, zh, bag)


def raw_fish(bag: Bag, zh: str) -> str:
    fish = bag.pull("protein")
    acid = bag.pull("acid")
    mix = bag.pull("aromatic", "heat", "veg", "liquid", "oil", "salty", "spice")
    steps = []
    if fish:
        steps.append(f"{fish}切塊" + (f"，以{acid}醃至表面轉色" if acid else "拌勻"))
    elif acid:
        steps.append(f"以{acid}醃拌")
    if mix:
        steps.append(f"拌入{mix}")
    return join_steps(steps, zh, bag)


def hotpot(bag: Bag, zh: str) -> str:
    base = bag.pull("liquid", "salty", "spice", "heat", "aromatic")
    body = bag.pull("protein", "veg", "legume", "grain", "root", "flour")
    steps = [f"{base or '清水'}煮滾"]
    if body:
        steps.append(f"{body}分次涮至剛熟")
    return join_steps(steps, zh, bag)


def fondue(bag: Bag, zh: str) -> str:
    cheese = bag.pull("dairy", "liquid")
    season = bag.pull("aromatic", "salty", "acid", "heat", "spice")
    dip = bag.pull("flour", "grain", "protein", "veg", "root")
    steps = []
    if cheese:
        steps.append(f"{cheese}小火融成醬" + (f"，以{season}調味" if season else ""))
    elif season:
        steps.append(f"以{season}調味")
    if dip:
        steps.append(f"{dip}蘸熱醬食用")
    return join_steps(steps, zh, bag)


def sticky_sweet(bag: Bag, zh: str) -> str:
    grain = bag.pull("grain")
    liquid = bag.pull("liquid")
    sweet = bag.pull("sweet", "salty")
    fruit = bag.pull("garnish")
    steps = []
    if grain:
        cook = "、".join(part for part in (liquid, sweet) if part)
        steps.append(f"{grain}蒸熟" + (f"，拌入{cook}" if cook else ""))
    if fruit:
        steps.append(f"配{fruit}一起食用")
    return join_steps(steps, zh, bag)


def tea_rice(bag: Bag, zh: str) -> str:
    grain = bag.pull("grain")
    tea = bag.pull("liquid")
    top = bag.pull("protein", "salty")
    steps = []
    if grain:
        steps.append(f"{grain}蒸熟撥散")
    if tea or top:
        steps.append("淋上" + "、".join(part for part in (tea, top) if part))
    return join_steps(steps, zh, bag)


def sushi(bag: Bag, zh: str) -> str:
    grain = bag.pull("grain")
    season = bag.pull("acid", "salty", "sweet")
    top = bag.pull("protein", "veg", "garnish")
    steps = []
    if grain:
        steps.append(f"{grain}煮熟晾涼" + (f"，以{season}拌勻" if season else ""))
    elif season:
        steps.append(f"以{season}調味")
    if top:
        steps.append(f"配{top}捏合或捲起")
    return join_steps(steps, zh, bag)


def zongzi(bag: Bag, zh: str) -> str:
    grain = bag.pull("grain")
    filling = bag.pull("protein", "veg", "garnish", "aromatic", "salty", "oil", "sweet", "legume")
    steps = []
    if grain or filling:
        steps.append("、".join(part for part in (grain, filling) if part) + "包好蒸熟")
    return join_steps(steps, zh, bag)


def steam_cake(bag: Bag, zh: str) -> str:
    body = bag.pull("veg", "grain", "flour", "root")
    mix = bag.pull("protein", "garnish", "aromatic", "salty", "oil")
    steps = []
    batter = "、".join(part for part in (body, mix) if part)
    if batter:
        steps.append(f"{batter}調成糕漿，蒸熟後切塊")
    return join_steps(steps, zh, bag)


def spring_roll(bag: Bag, zh: str) -> str:
    filling = bag.pull("protein", "veg", "aromatic", "salty", "spice", "oil", "garnish")
    wrap = bag.pull("flour", "grain")
    steps = []
    if filling:
        steps.append(f"{filling}拌成餡")
    if wrap:
        steps.append(f"以{wrap}皮包起，炸至酥黃")
    elif filling:
        steps.append("包起後炸至酥黃")
    return join_steps(steps, zh, bag)


def dumpling(bag: Bag, zh: str, cook: str) -> str:
    filling = bag.pull("protein", "veg", "aromatic", "salty", "oil", "spice", "heat", "garnish")
    wrap = bag.pull("flour", "grain", "root")
    steps = []
    if filling:
        steps.append(f"{filling}拌成餡")
    if wrap:
        steps.append(f"{wrap}擀皮包餡，{cook}")
    else:
        steps.append(cook)
    return join_steps(steps, zh, bag)


def wonton_noodle(bag: Bag, zh: str) -> str:
    filling = bag.pull("protein", "aromatic", "salty", "oil", "spice", "heat")
    noodle = bag.pull("flour", "grain")
    soup = bag.pull("liquid", "veg")
    steps = []
    if filling:
        steps.append(f"{filling}調成餡，包成雲吞")
    if noodle:
        steps.append(f"{noodle}煮熟，雲吞一起煮至浮起")
    if soup:
        steps.append(f"盛入{soup}調成的湯")
    return join_steps(steps, zh, bag)


def salad(bag: Bag, zh: str) -> str:
    body = bag.pull("veg", "protein", "grain", "root", "legume", "garnish", "flour")
    dress = bag.pull("oil", "acid", "salty", "sweet", "heat", "spice", "liquid", "dairy", "aromatic")
    herb = bag.pull("herb")
    steps = []
    if body:
        steps.append(f"{body}洗切")
    if dress:
        steps.append(f"以{dress}拌勻")
    if herb:
        steps.append(f"撒{herb}")
    return join_steps(steps, zh, bag)


def mash(bag: Bag, zh: str) -> str:
    base = bag.pull("legume", "veg", "root", "protein")
    dress = bag.pull("oil", "acid", "aromatic", "salty", "heat", "spice", "liquid", "dairy", "herb")
    steps = []
    if base:
        steps.append(f"{base}煮軟或壓成泥")
    if dress:
        steps.append(f"拌入{dress}")
    return join_steps(steps, zh, bag)


def egg_pan(bag: Bag, zh: str) -> str:
    bread = bag.pull("flour", "grain") if "早餐" in zh else ""
    aroma = bag.pull("oil", "aromatic", "veg")
    eggs = bag.pull("protein")
    season = bag.pull("salty", "heat", "spice", "sweet", "liquid", "dairy")
    steps = []
    if bread:
        steps.append(f"{bread}烤成吐司")
    if aroma:
        steps.append(f"{aroma}先炒軟")
    if eggs:
        steps.append(f"倒入{eggs}煎至凝固" + (f"，以{season}調味" if season else ""))
    elif season:
        steps.append(f"以{season}調味")
    return join_steps(steps, zh, bag)


def griddle(bag: Bag, zh: str) -> str:
    batter = bag.pull("flour", "protein", "liquid", "dairy", "sweet", "salty", "grain")
    mix = bag.pull("veg", "aromatic", "oil")
    steps = []
    body = "、".join(part for part in (batter, mix) if part)
    if body:
        steps.append(f"{body}拌成糊，平鍋煎至兩面熟")
    return join_steps(steps, zh, bag)


def fried_rice(bag: Bag, zh: str) -> str:
    grain = bag.pull("grain")
    aroma = bag.pull("oil", "aromatic")
    eggs, meat = split_eggs(bag.pull_items("protein"))
    veg = bag.pull("veg", "legume", "root")
    season = bag.pull("salty", "sweet", "heat", "spice", "liquid")
    steps = []
    if grain:
        steps.append(f"{grain}蒸熟撥散")
    first = "、".join(part for part in (grams(eggs), grams(meat), aroma) if part)
    if first:
        steps.append(f"{first}先炒散" + (f"，再下{veg}" if veg else ""))
    elif veg:
        steps.append(f"{veg}炒勻")
    if grain:
        steps.append("倒回飯中" + (f"，以{season}調味" if season else "炒勻"))
    elif season:
        steps.append(f"以{season}調味")
    return join_steps(steps, zh, bag)


def split_eggs(items: list[tuple[str, int]]) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    eggs = [item for item in items if "蛋" in item[0]]
    meat = [item for item in items if "蛋" not in item[0]]
    return eggs, meat


def risotto(bag: Bag, zh: str) -> str:
    aroma = bag.pull("aromatic", "oil")
    grain = bag.pull("grain")
    liquid = bag.pull("liquid", "dairy")
    extra = bag.pull("protein", "veg", "spice")
    season = bag.pull("salty", "sweet", "heat")
    steps = []
    if aroma or grain:
        steps.append("、".join(part for part in (aroma, grain) if part) + "拌炒至米粒透亮")
    if liquid or extra:
        steps.append("分次加入" + "、".join(part for part in (liquid, extra) if part) + "，煮至軟而帶黏")
    if season:
        steps.append(f"以{season}調味")
    return join_steps(steps, zh, bag)


def paella(bag: Bag, zh: str) -> str:
    base = bag.pull("oil", "aromatic", "protein", "spice")
    veg = bag.pull("veg")
    grain = bag.pull("grain", "salty", "liquid")
    steps = []
    if base:
        steps.append(f"{base}煸香" + (f"，加入{veg}" if veg else ""))
    elif veg:
        steps.append(f"{veg}炒軟")
    if grain:
        steps.append(f"鋪入{grain}，平鍋煮至收乾")
    return join_steps(steps, zh, bag)


def couscous(bag: Bag, zh: str) -> str:
    stew = bag.pull("protein", "aromatic", "oil", "veg", "legume", "spice", "heat", "salty", "sweet", "liquid", "root")
    grain = bag.pull("flour", "grain")
    steps = []
    if stew:
        steps.append(f"{stew}燉至軟爛")
    if grain:
        steps.append(f"{grain}蒸散後與燉菜拌勻")
    return join_steps(steps, zh, bag)


def noodle(bag: Bag, zh: str) -> str:
    sauce = bag.pull("protein", "aromatic", "oil", "liquid", "spice", "salty", "sweet", "heat", "dairy")
    noodle_body = bag.pull("flour", "grain")
    veg = bag.pull("veg", "legume", "root")
    steps = []
    if sauce:
        steps.append(f"{sauce}先做成湯或醬")
    if noodle_body:
        steps.append(f"{noodle_body}煮熟撈起")
    if veg:
        steps.append(f"拌入{veg}")
    return join_steps(steps, zh, bag)


def porridge(bag: Bag, zh: str) -> str:
    grain = bag.pull("grain", "flour", "legume", "liquid")
    body = bag.pull("protein", "veg", "root", "aromatic", "spice")
    season = bag.pull("salty", "sweet", "oil", "heat")
    steps = []
    if grain:
        steps.append(f"{grain}加水煮成粥")
    if body:
        steps.append(f"{body}煮至軟")
    if season:
        steps.append(f"以{season}調味")
    return join_steps(steps, zh, bag)


def swallow(bag: Bag, zh: str) -> str:
    staple = bag.pull("grain", "flour", "root")
    side = bag.pull("veg", "protein", "legume", "aromatic", "oil", "spice", "heat")
    season = bag.pull("salty")
    steps = []
    if staple:
        steps.append(f"{staple}加水攪成稠糊")
    if side:
        steps.append(f"{side}煮成配菜" + (f"，以{season}調味" if season else ""))
    elif season:
        steps.append(f"以{season}調味")
    return join_steps(steps, zh, bag)


def soup(bag: Bag, zh: str) -> str:
    base = bag.pull("aromatic", "protein", "spice", "liquid")
    body = bag.pull("veg", "legume", "grain", "root", "flour")
    season = bag.pull("salty", "sweet", "heat", "oil", "dairy")
    steps = []
    if base:
        steps.append(f"{base}先滾出味")
    if body:
        steps.append(f"放入{body}煮熟")
    if season:
        steps.append(f"以{season}調味")
    return join_steps(steps, zh, bag)


def curry(bag: Bag, zh: str) -> str:
    base = bag.pull("oil", "aromatic", "spice", "heat")
    body = bag.pull("protein", "liquid", "veg", "legume", "root", "sweet")
    season = bag.pull("salty", "acid", "dairy")
    side = bag.pull("grain", "flour")
    steps = []
    if base:
        steps.append(f"{base}炒香")
    if body:
        steps.append(f"加入{body}小火煮入味")
    if season:
        steps.append(f"以{season}調味")
    if side:
        steps.append(f"配{side}")
    return join_steps(steps, zh, bag)


def sweet_sour(bag: Bag, zh: str) -> str:
    meat = bag.pull("protein")
    flour = bag.pull("flour")
    oil = bag.pull("oil")
    sauce = bag.pull("sweet", "acid", "salty", "aromatic", "heat")
    steps = []
    if meat or flour:
        steps.append("、".join(part for part in (meat, flour) if part) + "抓勻後煎或炸至上色")
    if oil and not meat:
        steps.append(f"下{oil}")
    elif oil:
        steps.append(f"用{oil}起鍋")
    if sauce:
        steps.append(f"以{sauce}收成糖醋汁")
    return join_steps(steps, zh, bag)


def mapo(bag: Bag, zh: str) -> str:
    aroma = bag.pull("oil", "aromatic", "heat", "spice")
    meat, tofu = split_named(bag.pull_items("protein"), "豆腐")
    season = bag.pull("salty", "sweet", "liquid")
    steps = []
    if aroma or meat:
        steps.append("、".join(part for part in (aroma, grams(meat)) if part) + "炒散")
    if tofu:
        steps.append(f"放入{grams(tofu)}煮至入味" + (f"，以{season}調味" if season else ""))
    elif season:
        steps.append(f"以{season}調味")
    return join_steps(steps, zh, bag)


def split_named(items: list[tuple[str, int]], token: str) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    hit = [item for item in items if token in item[0]]
    rest = [item for item in items if token not in item[0]]
    return rest, hit


def poach(bag: Bag, zh: str) -> str:
    water = bag.pull("aromatic", "salty", "spice")
    meat = bag.pull("protein")
    grain = bag.pull("grain")
    steps = []
    if water or meat:
        steps.append("、".join(part for part in (water, meat) if part) + "加水煮至剛熟，撈起")
    if grain:
        steps.append(f"{grain}蒸熟，鋪上切好的肉")
    return join_steps(steps, zh, bag)


def simmer_egg(bag: Bag, zh: str) -> str:
    eggs = bag.pull("protein")
    bath = bag.pull("liquid", "salty", "spice", "aromatic", "sweet")
    steps = []
    if eggs:
        steps.append(f"{eggs}加" + (bath or "水") + "小火煮後燜入味")
    elif bath:
        steps.append(f"{bath}煮開")
    return join_steps(steps, zh, bag)


def cold_plate(bag: Bag, zh: str) -> str:
    body = bag.pull("protein", "veg", "grain", "root", "legume", "garnish", "flour", "dairy")
    dress = bag.pull("oil", "salty", "acid", "sweet", "heat", "liquid", "aromatic", "herb", "spice")
    steps = []
    if body:
        steps.append(f"{body}擺盤或拌勻")
    if dress:
        steps.append(f"淋上{dress}")
    return join_steps(steps, zh, bag)


def steam_egg(bag: Bag, zh: str) -> str:
    eggs = bag.pull("protein", "liquid", "salty")
    top = bag.pull("veg", "aromatic", "garnish")
    steps = []
    if eggs:
        steps.append(f"{eggs}濾勻，蒸至凝固")
    if top:
        steps.append(f"表面放{top}")
    return join_steps(steps, zh, bag)


def steam(bag: Bag, zh: str) -> str:
    body = bag.pull("protein", "veg", "grain", "flour", "root", "legume")
    top = bag.pull("aromatic", "spice")
    sauce = bag.pull("salty", "sweet", "oil", "liquid", "acid")
    steps = []
    if body or top:
        steps.append("、".join(part for part in (body, top) if part) + "大火蒸熟")
    if sauce:
        steps.append(f"淋{sauce}")
    return join_steps(steps, zh, bag)


def deep_fry(bag: Bag, zh: str) -> str:
    grain = bag.pull("grain")
    body = bag.pull("protein", "root", "veg")
    coat = bag.pull("flour", "liquid", "dairy")
    season = bag.pull("salty", "spice", "heat")
    steps = []
    if grain:
        steps.append(f"{grain}蒸熟墊底")
    main = "、".join(part for part in (body, coat) if part)
    if main:
        steps.append(f"{main}裹勻" + (f"，抹{season}" if season else "") + "，油熱後炸至金黃")
    elif season:
        steps.append(f"抹{season}後炸熟")
    return join_steps(steps, zh, bag)


def fry_bowl(bag: Bag, zh: str) -> str:
    return deep_fry(bag, zh)


def skewer(bag: Bag, zh: str) -> str:
    meat = bag.pull("protein", "aromatic")
    season = bag.pull("salty", "spice", "oil", "sweet", "heat")
    steps = []
    if meat and season:
        steps.append(f"{meat}以{season}拌勻後穿串，烤至焦香")
    elif meat:
        steps.append(f"{meat}穿串烤至焦香")
    elif season:
        steps.append(f"以{season}調味後烤熟")
    return join_steps(steps, zh, bag)


def roast(bag: Bag, zh: str) -> str:
    meat = bag.pull("protein")
    season = bag.pull("salty", "spice", "aromatic", "oil", "sweet", "heat")
    side = bag.pull("root", "veg", "grain", "legume", "flour")
    steps = []
    if meat:
        steps.append(f"{meat}" + (f"抹上{season}" if season else "") + "，烤至上色熟透")
    elif season:
        steps.append(f"以{season}調味後烤熟")
    if side:
        steps.append(f"{side}烤或煮熟一起上")
    return join_steps(steps, zh, bag)


def pilaf(bag: Bag, zh: str) -> str:
    aroma = bag.pull("oil", "aromatic")
    meat = bag.pull("protein")
    veg = bag.pull("veg", "legume", "root", "spice")
    grain = bag.pull("grain", "flour")
    season = bag.pull("salty", "sweet", "heat", "liquid")
    steps = []
    first = "、".join(part for part in (aroma, meat) if part)
    if first:
        steps.append(f"{first}炒至上色" + (f"，加入{veg}" if veg else ""))
    elif veg:
        steps.append(f"{veg}炒香")
    if grain:
        steps.append(f"拌入{grain}" + (f"與{season}" if season else "") + "，加水小火燜熟")
    elif season:
        steps.append(f"以{season}調味")
    return join_steps(steps, zh, bag)


def sandwich(bag: Bag, zh: str) -> str:
    bread = bag.pull("flour", "grain")
    meat = bag.pull("protein")
    season = bag.pull("aromatic", "oil", "salty", "spice", "heat", "sweet")
    veg = bag.pull("veg", "legume", "garnish", "dairy", "acid")
    steps = []
    if bread:
        steps.append(f"{bread}做成餅或麵包")
    if meat:
        steps.append(f"{meat}" + (f"以{season}烹熟" if season else "烹熟"))
    elif season:
        steps.append(f"以{season}調味")
    if veg:
        steps.append(f"夾入{veg}")
    return join_steps(steps, zh, bag)


def filled_pastry(bag: Bag, zh: str) -> str:
    dough = bag.pull("flour")
    filling = bag.pull("protein", "veg", "root", "legume", "aromatic", "salty", "spice", "oil", "garnish", "heat")
    steps = []
    if dough or filling:
        steps.append("、".join(part for part in (dough, filling) if part) + "包成餅，烤或炸至酥黃")
    return join_steps(steps, zh, bag)


def bake(bag: Bag, zh: str) -> str:
    batter = bag.pull("flour", "grain", "dairy", "liquid", "sweet", "salty", "oil")
    eggs, other = split_eggs(bag.pull_items("protein"))
    filling = "、".join(part for part in (grams(eggs), grams(other), bag.pull("veg", "root", "legume", "spice", "garnish")) if part)
    steps = []
    if batter and filling:
        steps.append(f"{batter}做皮或麵糊，填入{filling}，烘至金黃")
    elif batter:
        steps.append(f"{batter}拌勻後烘或烤至金黃")
    elif filling:
        steps.append(f"{filling}拌勻後烘熟")
    return join_steps(steps, zh, bag)


def rice_top(bag: Bag, zh: str) -> str:
    grain = bag.pull("grain")
    liquid = bag.pull("liquid")
    meat = bag.pull("protein")
    season = bag.pull("oil", "aromatic", "spice", "sweet", "heat", "salty")
    side = bag.pull("veg", "legume", "root", "flour")
    steps = []
    if grain:
        steps.append(f"{grain}" + (f"加{liquid}" if liquid else "") + "蒸熟")
    elif liquid:
        steps.append(f"{liquid}煮開")
    meat_verb = "烹熟"
    if any(token in zh for token in ("滷", "紅燒")):
        meat_verb = "滷至入味"
    elif any(token in zh for token in ("烤", "叉燒", "燒味")):
        meat_verb = "烤至上色"
    elif "炸" in zh:
        meat_verb = "炸至金黃"
    elif any(token in zh for token in ("海南", "白切")):
        meat_verb = "加水煮至剛熟"
    if meat:
        steps.append(f"{meat}" + (f"以{season}{meat_verb}" if season else meat_verb))
    elif season:
        steps.append(f"以{season}調味後{meat_verb}")
    if side:
        steps.append(f"配{side}")
    return join_steps(steps, zh, bag)


def ferment(bag: Bag, zh: str) -> str:
    veg = bag.pull("veg", "root")
    salty = bag.pull("salty")
    mix = bag.pull("aromatic", "heat", "spice", "sweet", "garnish", "oil")
    steps = []
    if veg:
        steps.append(f"{veg}" + (f"以{salty}抓醃出水" if salty else "鹽醃"))
    if mix:
        steps.append(f"拌入{mix}，醃至入味")
    return join_steps(steps, zh, bag)


def stir(bag: Bag, zh: str) -> str:
    aroma = bag.pull("oil", "aromatic", "heat", "spice")
    meat = bag.pull("protein")
    veg = bag.pull("veg", "legume", "root")
    season = bag.pull("salty", "sweet", "acid", "liquid", "dairy")
    grain = bag.pull("grain", "flour")
    herb = bag.pull("herb")
    steps = []
    if aroma:
        steps.append(f"熱鍋下{aroma}爆香")
    if meat:
        steps.append(f"{meat}快炒至變色" + (f"，下{veg}" if veg else "") + (f"，拌入{herb}" if herb else ""))
    elif veg:
        steps.append(f"{veg}炒至斷生" + (f"，拌入{herb}" if herb else ""))
    elif herb:
        steps.append(f"拌入{herb}")
    if season:
        steps.append(f"以{season}調味")
    if grain:
        steps.append(f"{grain}蒸熟後盛在一起")
    return join_steps(steps, zh, bag)


def mussels(bag: Bag, zh: str) -> str:
    base = bag.pull("aromatic", "spice", "herb", "liquid", "dairy", "salty", "heat", "oil")
    seafood = bag.pull("protein")
    potatoes = bag.pull("root")
    steps = []
    if seafood:
        steps.append(f"{seafood}" + (f"加{base}" if base else "") + "蓋煮至開口")
    elif base:
        steps.append(f"{base}煮開")
    if potatoes:
        steps.append(f"{potatoes}炸或烤至外酥")
    return join_steps(steps, zh, bag)


def fries(bag: Bag, zh: str) -> str:
    potatoes = bag.pull("root")
    top = bag.pull("protein", "dairy", "salty", "aromatic", "spice", "oil")
    steps = []
    if potatoes:
        steps.append(f"{potatoes}炸至酥")
    if top:
        steps.append(f"淋上{top}")
    return join_steps(steps, zh, bag)


def braise(bag: Bag, zh: str) -> str:
    aroma = bag.pull("oil", "aromatic")
    meat = bag.pull("protein")
    body = bag.pull("veg", "legume", "root", "grain", "flour", "spice", "liquid")
    season = bag.pull("salty", "sweet", "heat", "dairy", "acid")
    steps = []
    first = "、".join(part for part in (aroma, meat) if part)
    if first:
        steps.append(f"{first}炒至上色")
    if body:
        steps.append(f"加入{body}，加水小火燜軟")
    if season:
        steps.append(f"以{season}調味")
    return join_steps(steps, zh, bag)


def cell_value(sheet, row: int, col: int):
    cell = sheet.cell(row, col)
    if cell.ctype == xlrd.XL_CELL_NUMBER:
        value = cell.value
        if value == int(value):
            return int(value)
        return value
    if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
        return ""
    return cell.value


def load_rows(path: Path):
    book = xlrd.open_workbook(str(path))
    sheet = book.sheet_by_index(0)
    headers = [str(sheet.cell_value(0, col)).strip() for col in range(sheet.ncols)]
    rows = []
    for row in range(1, sheet.nrows):
        rows.append([cell_value(sheet, row, col) for col in range(sheet.ncols)])
    return headers, rows


def insert_methods(headers: list[str], rows: list[list]) -> tuple[list[str], list[list], list[str]]:
    if "煮法" in headers:
        method_at = headers.index("煮法")
        headers = headers[:method_at] + headers[method_at + 1 :]
        rows = [row[:method_at] + row[method_at + 1 :] for row in rows]
    if "食譜" not in headers:
        raise SystemExit("找不到食譜欄")
    recipe_at = headers.index("食譜")
    name_at = headers.index("中文食譜")
    en_at = headers.index("英文食譜")
    out_headers = headers[: recipe_at + 1] + ["煮法"] + headers[recipe_at + 1 :]
    methods: list[str] = []
    out_rows = []
    problems = []
    seen: dict[str, int] = {}
    for index, row in enumerate(rows, start=1):
        zh = str(row[name_at]).strip()
        en = str(row[en_at]).strip()
        recipe = str(row[recipe_at]).strip()
        items = parse_recipe(recipe)
        method = method_for(zh, en, items)
        missing = [f"{name}{amount}克" for name, amount in items if f"{name}{amount}克" not in method]
        if missing:
            problems.append(f"row {index} {zh} missing {missing}")
        if not method.strip():
            problems.append(f"row {index} {zh} empty")
        if method in seen:
            problems.append(f"row {index} {zh} duplicates row {seen[method]}")
        seen[method] = index
        methods.append(method)
        out_rows.append(row[: recipe_at + 1] + [method] + row[recipe_at + 1 :])
    if out_headers != TARGET_HEADERS:
        problems.append("headers " + " | ".join(out_headers))
    return out_headers, out_rows, problems


def save_book(headers: list[str], rows: list[list]) -> str:
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
    book = xlwt.Workbook(encoding="utf-8")
    sheet = book.add_sheet("食譜")
    widths = [28, 22, 36, 28, 24, 78, 72, 55, 55, 80, 28]
    for col, header in enumerate(headers):
        sheet.write(0, col, header, header_style)
        sheet.col(col).width = 256 * widths[col]
    sheet.panes_frozen = True
    sheet.horz_split_pos = 1
    for row_index, values in enumerate(rows, start=1):
        for col, value in enumerate(values):
            sheet.write(row_index, col, value, cell_style)
    tmp_path = ROOT / "Recipe.xls.writing"
    new_path = ROOT / "Recipe.xls.new"
    final_path = ROOT / "Recipe.xls"
    book.save(str(tmp_path))
    os.replace(tmp_path, new_path)
    try:
        os.replace(new_path, final_path)
        return str(final_path)
    except OSError as exc:
        return f"{new_path} (Recipe.xls locked: {exc})"


def main() -> None:
    source = choose_source()
    headers, rows = load_rows(source)
    print("source", source.name, "rows", len(rows), "headers", " | ".join(headers))
    out_headers, out_rows, problems = insert_methods(headers, rows)
    print("out", " | ".join(out_headers), "problems", len(problems))
    for line in problems[:20]:
        print(line)
    tech_counts = Counter()
    for row in rows:
        tech_counts[technique_for(str(row[1]), str(row[2]))] += 1
    print("techniques", dict(tech_counts))
    if problems:
        raise SystemExit(1)
    saved = save_book(out_headers, out_rows)
    print("saved", saved)
    print("sample1", out_rows[0][1], out_rows[0][6])
    print("sample49", out_rows[48][1], out_rows[48][6])
    print("sample57", out_rows[56][1], out_rows[56][6])


if __name__ == "__main__":
    main()
