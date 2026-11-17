# -*- coding: utf-8 -*-
"""Append 14 nutrient columns to Recipe.xls and Foods.xls.

Foods values are per 100 g edible portion (typical USDA / TW FDA tables).
Recipe values scale ingredient grams in the 食譜 cell to about one serving.
Minerals/vitamins are stored as grams (mg/1000, ug/1e6). Teaching estimates only.
Unmatched rows leave nutrient cells blank.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECIPE_PATH = ROOT / "Recipe.xls"
FOODS_PATH = ROOT / "Foods.xls"

HEADERS = (
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
)
# kcal, fiber g, Ca mg, Fe mg, Zn mg, I ug, Se ug, B mg, C mg, D ug, carb, protein, fat, water
DIGITS = (1, 2, 4, 4, 4, 7, 7, 6, 4, 8, 2, 2, 2, 2)
TO_G = (
    1,
    1,
    1 / 1000,
    1 / 1000,
    1 / 1000,
    1 / 1_000_000,
    1 / 1_000_000,
    1 / 1000,
    1 / 1000,
    1 / 1_000_000,
    1,
    1,
    1,
    1,
)
ING_RE = re.compile(r"^(.+?)\s*(\d+(?:\.\d+)?)\s*克$")

# Per 100 g. Keys are 中文 names used in Foods.xls / Recipe 食譜.
PER100G: dict[str, tuple] = {}
ALIASES: dict[str, str] = {}


def add(name: str, *vals) -> None:
    if len(vals) != 14:
        raise ValueError(name)
    PER100G[name] = tuple(vals)


def add_many(names: list[str], row: tuple) -> None:
    for name in names:
        add(name, *row)


def alias(src: str, *names: str) -> None:
    for name in names:
        ALIASES[name] = src


# Staples
add("粳米", 360, 1.3, 9, 0.8, 1.1, 0, 15, 3.2, 0, 0, 79, 6.7, 0.6, 12)
add("糙米", 362, 3.5, 23, 1.5, 2.0, 0, 23, 6.5, 0, 0, 76, 7.5, 2.7, 12)
add("糯米", 370, 1.0, 6, 0.8, 1.2, 0, 12, 2.8, 0, 0, 81, 6.8, 0.6, 11)
add("小米", 378, 8.5, 8, 3.0, 1.7, 0, 3, 4.6, 0, 0, 73, 11, 4.2, 9)
add("小麥", 340, 12, 34, 3.6, 2.6, 0, 70, 6.0, 0, 0, 72, 13, 2.5, 11)
add("大麥", 354, 17, 33, 3.6, 2.8, 0, 38, 6.5, 0, 0, 73, 12, 2.3, 10)
add("燕麥", 389, 11, 54, 4.7, 4.0, 0, 29, 4.0, 0, 0, 66, 17, 6.9, 8)
add("高粱", 329, 6.3, 28, 4.4, 1.5, 0, 12, 3.5, 0, 0, 72, 11, 3.3, 9)
add("蕎麥", 343, 10, 18, 2.2, 2.4, 0, 8, 6.0, 0, 0, 71, 13, 3.4, 10)
add("玉米", 86, 2.0, 2, 0.5, 0.5, 0, 0.6, 1.8, 6.8, 0, 19, 3.3, 1.4, 76)
add("馬鈴薯", 77, 2.2, 12, 0.8, 0.3, 0, 0.4, 1.5, 20, 0, 17, 2.0, 0.1, 79)
add("地瓜", 86, 3.0, 30, 0.6, 0.3, 0, 0.6, 0.8, 2.4, 0, 20, 1.6, 0.1, 77)
add("芋頭", 112, 4.1, 43, 0.6, 0.2, 0, 0.7, 0.9, 4.5, 0, 26, 1.5, 0.2, 71)
add("冬粉", 351, 0.5, 12, 0.6, 0.2, 0, 2, 0.2, 0, 0, 86, 0.2, 0.1, 13)
add("白飯", 130, 0.4, 3, 0.2, 0.4, 0, 8, 0.4, 0, 0, 28, 2.4, 0.3, 69)

# Pulses / soy
add("黃豆", 446, 9.3, 277, 16, 4.9, 0, 18, 6.5, 6, 0, 30, 36, 20, 8)
add("黑豆", 341, 15, 138, 7.0, 3.4, 0, 10, 4.0, 0, 0, 62, 22, 1.4, 11)
add("紅豆", 329, 13, 66, 5.0, 2.8, 0, 3, 4.0, 0, 0, 63, 20, 0.5, 13)
add("綠豆", 347, 16, 27, 6.7, 2.7, 0, 8, 4.5, 0, 0, 62, 24, 1.2, 9)
add("毛豆", 147, 5.2, 197, 2.3, 1.0, 0, 1.5, 2.0, 6, 0, 11, 13, 6.8, 73)
add("豆腐", 76, 0.3, 350, 1.6, 0.8, 0, 9, 0.5, 0.2, 0, 1.9, 8, 4.8, 85)
add("豆漿", 33, 0.4, 25, 0.5, 0.2, 0, 2, 0.3, 0, 0, 1.8, 3.3, 1.8, 93)
add("豆干", 180, 1.0, 180, 2.5, 1.5, 0, 8, 0.8, 0, 0, 4, 16, 10, 68)
add("鷹嘴豆", 364, 17, 105, 6.2, 3.4, 0, 8, 4.8, 4, 0, 61, 19, 6, 8)
add("紅腰豆", 333, 15, 83, 6.7, 2.8, 0, 3, 4.2, 4.5, 0, 60, 24, 0.8, 12)
add("兵豆", 352, 11, 35, 6.5, 3.3, 0, 8, 5.5, 4.5, 0, 63, 25, 1.1, 8)
add("豌豆", 81, 5.7, 25, 1.5, 1.2, 0, 1.8, 2.0, 40, 0, 14, 5.4, 0.4, 79)
add("花生", 567, 8.5, 92, 4.6, 3.3, 0, 7.2, 14, 0, 0, 16, 26, 49, 7)

# Vegetables
add("菠菜", 23, 2.2, 99, 2.7, 0.5, 0, 1.0, 1.2, 28, 0, 3.6, 2.9, 0.4, 91)
add("青江菜", 13, 1.0, 105, 0.8, 0.2, 0, 0.5, 0.5, 45, 0, 2.2, 1.5, 0.2, 95)
add("高麗菜", 25, 2.5, 40, 0.5, 0.2, 0, 0.3, 0.4, 37, 0, 5.8, 1.3, 0.1, 92)
add("大白菜", 13, 1.2, 77, 0.3, 0.1, 0, 0.4, 0.3, 45, 0, 2.2, 1.5, 0.2, 95)
add("空心菜", 19, 2.1, 80, 2.5, 0.3, 0, 0.9, 0.7, 55, 0, 3.1, 2.6, 0.2, 93)
add("番茄", 18, 1.2, 10, 0.3, 0.2, 0, 0, 0.8, 14, 0, 3.9, 0.9, 0.2, 95)
add("胡蘿蔔", 41, 2.8, 33, 0.3, 0.2, 0, 0.1, 0.8, 5.9, 0, 9.6, 0.9, 0.2, 88)
add("洋蔥", 40, 1.7, 23, 0.2, 0.2, 0, 0.5, 0.3, 7.4, 0, 9.3, 1.1, 0.1, 89)
add("大蒜", 149, 2.1, 181, 1.7, 1.2, 0, 14, 1.6, 31, 0, 33, 6.4, 0.5, 59)
add("生薑", 80, 2.0, 16, 0.6, 0.3, 0, 0.7, 0.8, 5, 0, 18, 1.8, 0.8, 79)
add("蔥", 32, 2.6, 72, 1.5, 0.4, 0, 0.6, 0.6, 19, 0, 7.3, 1.8, 0.2, 90)
add("韭菜", 30, 2.5, 105, 1.6, 0.4, 0, 1.0, 0.8, 45, 0, 4.3, 2.7, 0.4, 91)
add("黃瓜", 15, 0.5, 16, 0.3, 0.2, 0, 0.3, 0.3, 2.8, 0, 3.6, 0.7, 0.1, 95)
add("茄子", 25, 3.0, 9, 0.2, 0.2, 0, 0.3, 0.7, 2.2, 0, 5.9, 1.0, 0.2, 92)
add("青椒", 20, 1.7, 10, 0.3, 0.1, 0, 0, 0.6, 80, 0, 4.6, 0.9, 0.2, 94)
add("甜椒", 31, 2.1, 7, 0.4, 0.3, 0, 0, 0.8, 128, 0, 6.0, 1.0, 0.3, 92)
add("花椰菜", 25, 2.0, 22, 0.4, 0.3, 0, 0.6, 0.7, 48, 0, 5.0, 1.9, 0.3, 92)
add("青花菜", 34, 2.6, 47, 0.7, 0.4, 0, 2.5, 1.1, 89, 0, 6.6, 2.8, 0.4, 89)
add("南瓜", 26, 0.5, 21, 0.8, 0.3, 0, 0.3, 0.6, 9, 0, 6.5, 1.0, 0.1, 92)
add("白蘿蔔", 18, 1.6, 27, 0.4, 0.2, 0, 0.6, 0.4, 15, 0, 4.1, 0.7, 0.1, 95)
add("芹菜", 16, 1.6, 40, 0.2, 0.1, 0, 0.4, 0.4, 3.1, 0, 3.0, 0.7, 0.2, 95)
add("香菇", 34, 2.5, 2, 0.4, 1.0, 0, 5.7, 4.0, 0, 0.4, 6.8, 2.2, 0.5, 90)
add("金針菇", 37, 2.7, 0, 1.2, 0.6, 0, 2.2, 5.5, 0, 0.1, 7.8, 2.7, 0.3, 88)
add("黑木耳", 65, 7.0, 37, 5.0, 0.6, 0, 2.0, 0.4, 0, 0, 14, 1.5, 0.2, 80)
add("海帶", 43, 1.3, 168, 2.8, 1.2, 24000, 0.5, 0.5, 3, 0, 9, 1.7, 0.6, 82)
add("紫菜", 35, 0.3, 70, 1.8, 0.6, 1400, 0.7, 1.0, 39, 0, 5, 5.8, 0.3, 85)

# Fruit
add("蘋果", 52, 2.4, 6, 0.1, 0.04, 0, 0, 0.2, 4.6, 0, 14, 0.3, 0.2, 86)
add("香蕉", 89, 2.6, 5, 0.3, 0.2, 0, 1.0, 0.7, 8.7, 0, 23, 1.1, 0.3, 75)
add("柳橙", 47, 2.4, 40, 0.1, 0.1, 0, 0.5, 0.4, 53, 0, 12, 0.9, 0.1, 87)
add("檸檬", 29, 2.8, 26, 0.6, 0.1, 0, 0.4, 0.4, 53, 0, 9.3, 1.1, 0.3, 89)
add("芒果", 60, 1.6, 11, 0.2, 0.1, 0, 0.6, 0.7, 36, 0, 15, 0.8, 0.4, 83)
add("木瓜", 43, 1.7, 20, 0.3, 0.1, 0, 0.6, 0.4, 61, 0, 11, 0.5, 0.3, 88)
add("西瓜", 30, 0.4, 7, 0.2, 0.1, 0, 0.4, 0.2, 8.1, 0, 7.6, 0.6, 0.2, 91)

# Meat / egg / dairy
add("雞肉", 165, 0, 11, 0.9, 1.3, 6, 16, 8.0, 1.6, 0.2, 0, 20, 9, 70)
add("豬肉", 242, 0, 19, 0.9, 2.4, 1, 35, 6.5, 0.7, 0.6, 0, 17, 20, 62)
add("牛肉", 250, 0, 18, 2.6, 6.3, 2, 21, 6.0, 0, 0.1, 0, 26, 15, 58)
add("羊肉", 294, 0, 17, 1.9, 4.7, 2, 18, 6.5, 0, 0.1, 0, 25, 21, 54)
add("鴨肉", 201, 0, 11, 2.4, 1.9, 4, 16, 5.5, 3, 0.3, 0, 18, 14, 66)
add("豬肝", 134, 0, 9, 23, 5.8, 15, 53, 16, 23, 1.2, 2.5, 21, 3.6, 71)
add("雞蛋", 143, 0, 56, 1.8, 1.3, 50, 30, 2.2, 0, 2.0, 0.7, 13, 9.5, 76)
add("牛奶", 61, 0, 113, 0.03, 0.4, 20, 3.7, 0.5, 0, 0.1, 4.8, 3.2, 3.3, 88)
add("優格", 61, 0, 121, 0.05, 0.6, 15, 3.0, 0.4, 0.5, 0.1, 4.7, 3.5, 3.3, 88)
add("起司", 402, 0, 721, 0.7, 3.1, 30, 14, 0.6, 0, 0.6, 1.3, 25, 33, 37)
add("奶油", 717, 0, 24, 0.02, 0.1, 8, 1.0, 0.1, 0, 1.5, 0.1, 0.9, 81, 16)

# Seafood
add("鮭魚", 208, 0, 12, 0.3, 0.6, 15, 36, 9.0, 0, 11, 0, 20, 13, 64)
add("鯖魚", 205, 0, 12, 1.6, 0.6, 50, 44, 8.0, 0, 16, 0, 19, 14, 64)
add("吳郭魚", 96, 0, 10, 0.6, 0.3, 8, 42, 3.5, 0, 3.1, 0, 20, 1.7, 78)
add("虱目魚", 147, 0, 22, 0.5, 0.6, 12, 25, 4.0, 0, 4, 0, 20, 7, 70)
add("蝦", 99, 0, 70, 0.5, 1.6, 35, 38, 2.5, 0, 0.1, 0.9, 24, 0.3, 75)
add("蛤蜊", 74, 0, 46, 2.8, 1.4, 140, 24, 2.5, 10, 0.1, 2.6, 13, 1.0, 82)
add("牡蠣", 81, 0, 80, 5.1, 16, 60, 64, 4.0, 8, 0.5, 4.9, 9, 2.3, 83)
add("鱈魚", 82, 0, 16, 0.4, 0.5, 24, 28, 2.5, 1, 0.9, 0, 18, 0.7, 81)
add("鮪魚", 144, 0, 8, 1.0, 0.6, 20, 90, 12, 0, 1.7, 0, 23, 4.9, 68)

# Seasonings / fats / extras used in recipes
add("食鹽", 0, 0, 24, 0.3, 0.1, 4500, 0.1, 0, 0, 0, 0, 0, 0, 0)
add("醬油", 53, 0.8, 20, 1.4, 0.4, 2, 0.5, 2.5, 0, 0, 4.9, 8.1, 0.1, 71)
add("白糖", 387, 0, 1, 0.05, 0.01, 0, 0.6, 0, 0, 0, 100, 0, 0, 0.2)
add("冰糖", 387, 0, 1, 0.05, 0.01, 0, 0.6, 0, 0, 0, 100, 0, 0, 0.2)
add("蜂蜜", 304, 0.2, 6, 0.4, 0.2, 0, 0.8, 0.2, 0.5, 0, 82, 0.3, 0, 17)
add("醋", 18, 0, 7, 0.2, 0.04, 0, 0.1, 0, 0, 0, 0.9, 0.1, 0, 95)
add("麻油", 884, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 100, 0)
add("花生油", 884, 0, 0, 0.03, 0.01, 0, 0, 0, 0, 0, 0, 0, 100, 0)
add("橄欖油", 884, 0, 1, 0.6, 0, 0, 0, 0, 0, 0, 0, 0, 100, 0)
add("白芝麻", 573, 12, 975, 15, 7.8, 0, 34, 6.0, 0, 0, 23, 18, 50, 5)
add("核桃", 654, 6.7, 98, 2.9, 3.1, 0, 4.9, 2.5, 1.3, 0, 14, 15, 65, 4)
add("味噌", 198, 5.4, 57, 2.5, 2.6, 0, 7, 2.0, 0, 0, 26, 13, 6, 43)
add("胡椒", 251, 25, 443, 9.7, 1.2, 0, 4.9, 1.5, 0, 0, 64, 10, 3.3, 12)
add("芥藍", 28, 2.6, 128, 0.8, 0.3, 0, 0.8, 0.8, 70, 0, 5.0, 1.5, 0.4, 90)
add("油菜", 14, 1.2, 108, 1.0, 0.3, 0, 0.6, 0.6, 36, 0, 2.2, 1.2, 0.2, 95)
add("茼蒿", 24, 2.2, 70, 2.0, 0.4, 0, 0.5, 0.6, 20, 0, 3.0, 2.0, 0.3, 93)
add("生菜", 15, 1.3, 36, 0.9, 0.2, 0, 0.6, 0.4, 9, 0, 2.9, 1.4, 0.2, 95)
add("香菜", 23, 2.8, 67, 1.8, 0.5, 0, 0.9, 1.2, 27, 0, 3.7, 2.1, 0.5, 92)
add("小黃瓜", 15, 0.5, 16, 0.3, 0.2, 0, 0.3, 0.3, 2.8, 0, 3.6, 0.7, 0.1, 95)
add("秋葵", 33, 3.2, 82, 0.6, 0.6, 0, 0.7, 1.0, 23, 0, 7.5, 1.9, 0.2, 90)
add("竹筍", 27, 2.2, 13, 0.5, 0.5, 0, 0.5, 0.6, 4, 0, 5.2, 2.6, 0.3, 91)
add("黃豆芽", 30, 1.8, 40, 0.8, 0.4, 0, 0.6, 0.6, 13, 0, 4.0, 3.0, 0.2, 92)
add("洋菇", 22, 1.0, 3, 0.5, 0.5, 0, 9.3, 3.8, 2.1, 0.2, 3.3, 3.1, 0.3, 92)
add("梨", 57, 3.1, 9, 0.2, 0.1, 0, 0.1, 0.2, 4.3, 0, 15, 0.4, 0.1, 84)
add("草莓", 32, 2.0, 16, 0.4, 0.1, 0, 0.4, 0.3, 59, 0, 7.7, 0.7, 0.3, 91)
add("奇異果", 61, 3.0, 34, 0.3, 0.1, 0, 0.2, 0.4, 93, 0, 15, 1.1, 0.5, 83)
add("葡萄", 69, 0.9, 10, 0.4, 0.1, 0, 0.1, 0.3, 3.2, 0, 18, 0.7, 0.2, 81)
add("荔枝", 66, 1.3, 5, 0.3, 0.1, 0, 0.6, 0.3, 72, 0, 17, 0.8, 0.4, 82)
add("龍眼", 60, 1.1, 1, 0.1, 0.1, 0, 0.5, 0.3, 84, 0, 15, 1.3, 0.1, 83)
add("紅棗", 287, 6.0, 64, 1.0, 0.3, 0, 2, 1.2, 10, 0, 74, 3.0, 0.4, 18)
add("枸杞", 349, 13, 190, 6.8, 2.0, 0, 50, 2.0, 48, 0, 77, 14, 0.4, 8)
add("杏仁果", 579, 13, 269, 3.7, 3.1, 0, 4.1, 4.5, 0, 0, 22, 21, 50, 4)
add("栗子", 213, 5.1, 27, 1.0, 0.5, 0, 1.2, 1.3, 26, 0, 45, 2.4, 2.3, 48)
add("龍蝦", 90, 0, 48, 0.3, 2.9, 100, 42, 2.0, 0, 0, 0.5, 19, 0.9, 79)
add("螃蟹", 87, 0, 89, 0.7, 3.5, 40, 40, 3.0, 3, 0, 0, 18, 1.1, 79)
add("魷魚", 92, 0, 32, 0.7, 1.5, 20, 45, 3.0, 4.7, 0, 3.1, 16, 1.4, 78)
add("章魚", 82, 0, 53, 5.3, 1.7, 20, 45, 3.5, 5, 0, 2.2, 15, 1.0, 80)
add("茶", 1, 0, 0, 0.02, 0.01, 0, 0, 0.02, 0, 0, 0.3, 0, 0, 99)
add("綠茶", 1, 0, 0, 0.02, 0.01, 0, 0, 0.02, 0, 0, 0.3, 0, 0, 99)
add("紅茶", 1, 0, 0, 0.02, 0.01, 0, 0, 0.02, 0, 0, 0.3, 0, 0, 99)
add_many(
    ["石斑魚", "鱸魚", "鯛魚", "鯉魚", "草魚", "鰱魚"],
    (100, 0, 20, 0.4, 0.5, 30, 30, 3.5, 1, 1.5, 0, 20, 2, 76),
)

alias("粳米", "白米", "白米飯", "米飯", "米")
alias("白飯", "飯")
alias("小麥", "麵粉", "麵條", "麵")
alias("黃豆", "大豆")
alias("豆腐", "嫩豆腐", "板豆腐", "豆花")
alias("豆漿", "豆奶")
alias("蔥", "青蔥", "蔥花")
alias("生薑", "薑", "嫩薑")
alias("胡蘿蔔", "紅蘿蔔")
alias("青江菜", "小白菜", "油菜")
alias("黑木耳", "木耳")
alias("雞肉", "雞胸", "雞腿", "雞絲", "土雞")
alias("豬肉", "豬排", "里肌", "絞肉", "五花肉")
alias("牛肉", "牛排", "牛腱")
alias("雞蛋", "蛋", "雞蛋白", "鴨蛋")
alias("牛奶", "鮮奶", "牛乳")
alias("鮭魚", "鮭")
alias("蝦", "草蝦", "白蝦", "蝦仁")
alias("食鹽", "鹽", "鹽巴")
alias("白糖", "糖", "砂糖")
alias("麻油", "香油")
alias("白芝麻", "芝麻", "黑芝麻")
alias("海帶", "昆布")


def ensure_deps() -> None:
    try:
        import xlrd  # noqa: F401
        import xlwt  # noqa: F401
        import xlutils  # noqa: F401
    except ImportError:
        import subprocess

        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "xlrd==1.2.0", "xlwt", "xlutils"]
        )


def lookup(name: str) -> tuple | None:
    key = (name or "").strip()
    if not key:
        return None
    if key in PER100G:
        return PER100G[key]
    mapped = ALIASES.get(key)
    if mapped:
        return PER100G.get(mapped)
    hit = None
    for cand in list(PER100G) + list(ALIASES):
        if cand in key or key in cand:
            if hit is None or len(cand) > len(hit):
                hit = cand
    if not hit:
        return None
    if hit in PER100G:
        return PER100G[hit]
    return PER100G.get(ALIASES.get(hit, ""))


def parse_ingredients(text: str) -> list[tuple[str, float]]:
    items: list[tuple[str, float]] = []
    blob = str(text or "").replace("，", "、")
    for part in blob.split("、"):
        piece = part.strip()
        if not piece:
            continue
        match = ING_RE.match(piece)
        if not match:
            continue
        items.append((match.group(1).strip(), float(match.group(2))))
    return items


def scale_row(raw: tuple, grams: float) -> list[float]:
    factor = grams / 100.0
    out = []
    for index, value in enumerate(raw):
        out.append(round(value * factor * TO_G[index], DIGITS[index]))
    return out


def add_rows(left: list[float] | None, right: list[float]) -> list[float]:
    if left is None:
        return list(right)
    return [round(a + b, DIGITS[i]) for i, (a, b) in enumerate(zip(left, right))]


def recipe_nutrients(recipe_text: str, dish_name: str) -> list[float] | None:
    total = None
    for name, grams in parse_ingredients(recipe_text):
        raw = lookup(name)
        if raw is None:
            continue
        total = add_rows(total, scale_row(raw, grams))
    if total is not None:
        return total
    raw = lookup(dish_name)
    if raw is None:
        return None
    return scale_row(raw, 150.0)


def foods_nutrients(zh_name: str) -> list[float] | None:
    raw = lookup(zh_name)
    if raw is None:
        return None
    return scale_row(raw, 100.0)


def cell_write_value(sheet, row: int, col: int):
    import xlrd

    cell = sheet.cell(row, col)
    if cell.ctype == xlrd.XL_CELL_EMPTY or cell.ctype == xlrd.XL_CELL_BLANK:
        return None
    if cell.ctype == xlrd.XL_CELL_NUMBER:
        value = cell.value
        if value == int(value):
            return int(value)
        return value
    if cell.ctype == xlrd.XL_CELL_BOOLEAN:
        return bool(cell.value)
    return cell.value


def existing_headers(sheet) -> list[str]:
    return [str(sheet.cell_value(0, col)).strip() for col in range(sheet.ncols)]


def nutrient_start(headers: list[str]) -> int:
    if HEADERS[0] in headers:
        return headers.index(HEADERS[0])
    for index, name in enumerate(headers):
        if name == "":
            return index
    return len(headers)


def write_book(src_sheet, start: int, values_for_row) -> tuple[object, int, int]:
    import xlwt

    out = xlwt.Workbook(encoding="utf-8")
    dest = out.add_sheet(src_sheet.name or "Sheet1")
    width = max(src_sheet.ncols, start + len(HEADERS))
    for col in range(width):
        dest.col(col).width = 256 * (18 if col >= start else 22)
    header_style = xlwt.easyxf(
        "font: name 微軟正黑體, bold on, height 220, colour white;"
        "align: horiz center, vert center, wrap on;"
        "pattern: pattern solid, fore_colour gray80;"
        "borders: left thin, right thin, top thin, bottom thin"
    )
    cell_style = xlwt.easyxf(
        "font: name 微軟正黑體, height 200;"
        "align: vert top, wrap on;"
        "borders: left thin, right thin, top thin, bottom thin"
    )
    for col in range(src_sheet.ncols):
        dest.write(0, col, src_sheet.cell_value(0, col), header_style)
    for offset, header in enumerate(HEADERS):
        dest.write(0, start + offset, header, header_style)

    filled = 0
    blank = 0
    for row in range(1, src_sheet.nrows):
        for col in range(src_sheet.ncols):
            value = cell_write_value(src_sheet, row, col)
            if value is None:
                continue
            if start <= col < start + len(HEADERS):
                continue
            dest.write(row, col, value, cell_style)
        nums = values_for_row(row)
        if nums is None:
            blank += 1
            continue
        filled += 1
        for offset, value in enumerate(nums):
            dest.write(row, start + offset, value, cell_style)
    return out, filled, blank


def save_xls(book, path: Path) -> None:
    tmp = str(path) + f".tmp-{os.getpid()}"
    book.save(tmp)
    os.replace(tmp, str(path))


def fill_foods(sheet):
    headers = existing_headers(sheet)
    start = nutrient_start(headers)
    zh_col = headers.index("食材中文") if "食材中文" in headers else 0

    def values(row: int):
        name = str(sheet.cell_value(row, zh_col)).strip()
        return foods_nutrients(name)

    return write_book(sheet, start, values), start, values, zh_col


def fill_recipe(sheet):
    headers = existing_headers(sheet)
    start = nutrient_start(headers)
    recipe_col = headers.index("食譜") if "食譜" in headers else 5
    name_col = headers.index("中文食譜") if "中文食譜" in headers else 1

    def values(row: int):
        return recipe_nutrients(
            str(sheet.cell_value(row, recipe_col)),
            str(sheet.cell_value(row, name_col)).strip(),
        )

    return write_book(sheet, start, values), start, values, name_col


def try_xlutils_fill(path: Path, values_for_row, start: int):
    import xlrd
    from xlutils.copy import copy as xl_copy

    rb = xlrd.open_workbook(str(path), formatting_info=True)
    sheet = rb.sheet_by_index(0)
    wb = xl_copy(rb)
    dest = wb.get_sheet(0)
    for offset, header in enumerate(HEADERS):
        dest.write(0, start + offset, header)
    filled = 0
    blank = 0
    for row in range(1, sheet.nrows):
        nums = values_for_row(row)
        if nums is None:
            blank += 1
            continue
        filled += 1
        for offset, value in enumerate(nums):
            dest.write(row, start + offset, value)
    return wb, filled, blank


def print_samples(path: Path, label_col: int, start: int) -> None:
    import xlrd

    sheet = xlrd.open_workbook(str(path)).sheet_by_index(0)
    headers = existing_headers(sheet)
    print(f"--- {path.name} sample ---")
    shown = 0
    for row in range(1, sheet.nrows):
        nums = [sheet.cell_value(row, start + i) for i in range(len(HEADERS))]
        if all(v == "" or v is None for v in nums):
            continue
        name = sheet.cell_value(row, label_col)
        print(name, dict(zip(HEADERS, nums)))
        shown += 1
        if shown >= 3:
            break
    if shown == 0:
        print("(no filled rows)")


def main() -> None:
    ensure_deps()
    import xlrd

    jobs = (
        (FOODS_PATH, fill_foods),
        (RECIPE_PATH, fill_recipe),
    )
    for path, filler in jobs:
        if not path.exists():
            raise FileNotFoundError(path)
        book = xlrd.open_workbook(str(path))
        sheet = book.sheet_by_index(0)
        (out, filled, blank), start, values_fn, label_col = filler(sheet)
        used = "xlwt"
        try:
            out, filled, blank = try_xlutils_fill(path, values_fn, start)
            used = "xlutils"
        except Exception:
            pass
        save_xls(out, path)
        print(
            f"{path.name}: filled {filled} blank {blank} "
            f"total {filled + blank} dict {len(PER100G)} via {used}"
        )
        print_samples(path, label_col, start)


if __name__ == "__main__":
    main()
