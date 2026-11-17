"""Quick smoke checks for meal-calendar nutrient wiring. Run: python _smoke_meal_nutrients.py"""

from __future__ import annotations

import sys


def main() -> int:
    from app.nutrient_targets import lookup_targets, NUTRIENT_KEYS
    from app.recipes import recipe_rows, recipe_nutrient_map, public_recipe

    t = lookup_targets(30, "male")
    assert t["age_band"] == "19-50 歲", t["age_band"]
    assert "蛋白質(克)" in t["targets"], t["targets"].keys()
    print("targets ok", t["age_band"], t["gender"], t["targets"]["蛋白質(克)"])

    rows = recipe_rows()
    assert rows, "no recipes"
    sample = rows[0]
    nutrients = recipe_nutrient_map(sample)
    assert set(nutrients) == set(NUTRIENT_KEYS)
    pub = public_recipe(sample, "zh", 0)
    assert "nutrients" in pub
    print(
        "recipe ok",
        sample.get("name_zh") or sample.get("id"),
        "has_xls=",
        sample.get("has_nutrients"),
        "kcal=",
        nutrients.get("每日熱量(大卡)"),
    )

    from app.main import app

    paths = {getattr(r, "path", None) for r in app.routes}
    for needed in (
        "/api/nutrient-targets",
        "/api/meals/day",
        "/api/meals/month",
        "/api/meals",
        "/api/meals/{meal_id}",
    ):
        assert needed in paths, f"missing route {needed}"
    print("routes ok")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("FAIL:", exc, file=sys.stderr)
        raise
