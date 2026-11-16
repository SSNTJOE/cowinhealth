# -*- coding: utf-8 -*-
"""Unit check: mock research appends a Recipe.xls row recipes() can read."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from app import recipe_ensure, recipes


def main() -> None:
    root = Path(__file__).resolve().parent
    tmpdir = Path(tempfile.mkdtemp(prefix="recipe-ensure-"))
    shutil.copy(root / "Recipe.xls", tmpdir / "Recipe.xls")
    shutil.copy(root / "Foods.xls", tmpdir / "Foods.xls")
    recipe_ensure.RECIPE_PATH = tmpdir / "Recipe.xls"
    recipe_ensure.FOODS_PATH = tmpdir / "Foods.xls"
    recipes.RECIPE_PATH = tmpdir / "Recipe.xls"
    recipes.invalidate_recipe_cache()
    before = len(recipes.recipe_rows())

    def fake_research(country, name, lang):
        return {
            "name_zh": name,
            "name_en": "Mock Dish",
            "name_ja": "",
            "name_ko": "",
            "ingredients": [
                ("粳米", 200),
                ("雞蛋", 100),
                ("蔥", 50),
                ("花生油", 50),
                ("食鹽", 100),
            ],
            "method": "炒熟盛盤（測試）",
            "benefit": "",
            "ban": "",
            "nutrient": "",
            "allergens": "",
            "partial": False,
        }

    out = recipe_ensure.ensure_recipe(
        "Taiwan", "單元測試假菜", "zh", research_fn=fake_research
    )
    recipes.invalidate_recipe_cache()
    after = recipes.recipe_rows()
    assert out["created"] is True, out
    assert len(after) == before + 1, (before, len(after))
    row = after[-1]
    assert row["country"] == "Taiwan"
    assert row["name_zh"] == "單元測試假菜"
    assert "粳米" in row["recipe"]
    assert "雞蛋" in (row.get("allergens") or "")

    js = (root / "app" / "static" / "common.js").read_text(encoding="utf-8")
    for key in (
        "recipeSearching",
        "recipeEnsuring",
        "recipeCreateAction",
        "搜尋中",
        "搜尋建立資料中",
        "建立此食譜",
    ):
        assert key in js, key

    from app.main import app

    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/api/recipes/create" in paths
    assert "/api/recipes/ensure" in paths
    print(
        "OK",
        "id",
        out["recipe"]["id"],
        "rows",
        len(after),
        "foods_added",
        out["foods_added"],
    )


if __name__ == "__main__":
    main()
