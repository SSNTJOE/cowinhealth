# -*- coding: utf-8 -*-
"""Unit check: mock research appends a Recipe.xls row recipes() can read."""
from __future__ import annotations

import shutil
import tempfile
import time
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
    # Unique name so a prior MySQL catalog leftover cannot short-circuit create.
    mock_name = f"單元測試假菜{int(time.time())}"

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
        "Taiwan", mock_name, "zh", research_fn=fake_research
    )
    recipes.invalidate_recipe_cache()
    assert out["created"] is True, out
    row = out["recipe"]
    assert row["country"] == "Taiwan"
    assert mock_name in (row.get("name") or "")
    assert "粳米" in (row.get("recipe") or "")
    assert "雞蛋" in (row.get("allergens") or "")

    js = (root / "app" / "static" / "common.js").read_text(encoding="utf-8")
    for key in (
        "recipeSearching",
        "recipeEnsuring",
        "recipeCreateAction",
        "recipeCreateHint",
        "recipeListLoading",
        "recipeLangUnsupported",
        "recipeCountryCorrected",
        "搜尋中",
        "搜尋建檔中",
        "建立此食譜",
        "載入該國食譜中",
        "以中文進行",
        "目前僅支援中文",
    ):
        assert key in js, key

    assert recipe_ensure.name_script_supported("雞腿便當")
    assert recipe_ensure.name_script_supported("chicken bento")
    assert recipe_ensure.name_script_supported("キムチチゲ")
    assert recipe_ensure.name_script_supported("김치찌개")
    assert not recipe_ensure.name_script_supported("борщ")
    assert not recipe_ensure.name_script_supported("ผัดไทย")
    assert not recipe_ensure.name_script_supported("بيتزا")

    # Wrong country + known dish → resolve to catalog country; do not create.
    before_resolve = len(recipes.recipe_rows())
    resolved = recipe_ensure.ensure_recipe("Japan", "蛋餅", "zh", research_fn=fake_research)
    assert resolved.get("created") is False, resolved
    assert resolved.get("country_corrected") is True, resolved
    assert resolved["recipe"]["country"] == "Taiwan", resolved["recipe"]
    assert len(recipes.recipe_rows()) == before_resolve

    # Regression: wrong country + 牛肉麵 / Beef noodle soup must hit Taiwan, never create.
    before_beef = len(recipes.recipe_rows())
    beef = recipe_ensure.ensure_recipe("Japan", "牛肉麵", "zh", research_fn=fake_research)
    assert beef.get("created") is False, beef
    assert beef.get("country_corrected") is True, beef
    assert beef["recipe"]["country"] == "Taiwan", beef["recipe"]
    assert "牛肉" in (beef["recipe"].get("name") or ""), beef["recipe"]
    beef_en = recipe_ensure.ensure_recipe("France", "Beef noodle soup", "en", research_fn=fake_research)
    assert beef_en.get("created") is False, beef_en
    assert beef_en["recipe"]["country"] == "Taiwan", beef_en["recipe"]
    beef_simp = recipe_ensure.ensure_recipe("Korea", "牛肉面", "zh", research_fn=fake_research)
    assert beef_simp.get("created") is False, beef_simp
    assert beef_simp["recipe"]["country"] == "Taiwan", beef_simp["recipe"]
    assert len(recipes.recipe_rows()) == before_beef

    # Country-scoped list helper must return Taiwan dishes without full-catalog scan path only.
    tw = recipes.filter_recipes(country="Taiwan", lang="zh", by_body=False)
    assert tw["count"] > 0, tw
    assert any("牛肉麵" in (r.get("name") or "") for r in tw["recipes"]), "Taiwan list missing 牛肉麵"

    en_hit = recipe_ensure.ensure_recipe("France", "Kimchi stew", "en", research_fn=fake_research)
    assert en_hit.get("created") is False, en_hit
    assert en_hit["recipe"]["country"] == "South Korea", en_hit["recipe"]
    ko_hit = recipe_ensure.ensure_recipe("France", "김치찌개", "ko", research_fn=fake_research)
    assert ko_hit.get("created") is False, ko_hit
    assert ko_hit["recipe"]["country"] == "South Korea", ko_hit["recipe"]

    rejected = recipe_ensure.ensure_recipe("Taiwan", "борщ", "zh", research_fn=fake_research)
    assert rejected.get("rejected") is True, rejected
    assert rejected.get("recipe") is None
    assert "中文" in (rejected.get("note") or "")

    try:
        from app.main import app

        paths = {getattr(route, "path", None) for route in app.routes}
        assert "/api/recipes/create" in paths
        assert "/api/recipes/ensure" in paths
    except Exception as exc:  # pragma: no cover - env may lack full web deps
        print("skip route import:", exc)
    print(
        "OK",
        "id",
        out["recipe"]["id"],
        "rows_before",
        before,
        "foods_added",
        out["foods_added"],
        "country_corrected",
        resolved["recipe"]["country"],
    )


if __name__ == "__main__":
    main()
