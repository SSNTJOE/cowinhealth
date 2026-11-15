# -*- coding: utf-8 -*-
import xlrd

foods = xlrd.open_workbook(r"C:\Tube\Health-ing\Foods.xls").sheet_by_index(0)
print("FOODS", foods.nrows, foods.ncols)
print([foods.cell_value(0, c) for c in range(foods.ncols)])
print([foods.cell_value(1, c) for c in range(foods.ncols)])

recipes = xlrd.open_workbook(r"C:\Tube\Health-ing\Recipe.xls").sheet_by_index(0)
print("RECIPES", recipes.nrows, recipes.ncols)
print([recipes.cell_value(0, c) for c in range(recipes.ncols)])
headers = [str(recipes.cell_value(0, c)).strip() for c in range(recipes.ncols)]
recipe_col = headers.index("食譜")
tea_hits = []
for row in range(1, recipes.nrows):
    text = str(recipes.cell_value(row, recipe_col))
    if any(token in text for token in ("茶", "海帶", "紫菜")):
        tea_hits.append((recipes.cell_value(row, 1), text))
print("TEA_SEA", len(tea_hits))
for item in tea_hits[:25]:
    print(item[0], "|", item[1])
