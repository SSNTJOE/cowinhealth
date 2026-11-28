"""Apply affiliate_links schema + seed to live MySQL and print confirmation."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.affiliate import seed_demo_affiliate_rows  # noqa: E402
from app.db import connect, init_schema  # noqa: E402
from app.shared_catalog import (  # noqa: E402
    invalidate_foods_mysql_cache,
    invalidate_recipe_mysql_cache,
)


def main() -> None:
    ok = init_schema(timeout_seconds=15)
    print("init_schema", ok)
    seed_demo_affiliate_rows()
    invalidate_recipe_mysql_cache()
    invalidate_foods_mysql_cache()
    conn = connect(ensure=False)
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES LIKE 'affiliate_links'")
            print("table", cur.fetchone())
            cur.execute(
                """
                SELECT COLUMN_NAME FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'catalog_recipes'
                  AND COLUMN_NAME = 'affiliate_slug'
                """
            )
            print("catalog_recipes.affiliate_slug", cur.fetchone())
            cur.execute(
                """
                SELECT COLUMN_NAME FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'catalog_foods'
                  AND COLUMN_NAME = 'affiliate_slug'
                """
            )
            print("catalog_foods.affiliate_slug", cur.fetchone())
            cur.execute(
                "SELECT id, slug, title, is_active, url_default FROM affiliate_links WHERE slug=%s",
                ("test-olive-oil",),
            )
            print("seed", cur.fetchone())
            cur.execute(
                "SELECT COUNT(*) AS c FROM catalog_foods WHERE affiliate_slug=%s",
                ("test-olive-oil",),
            )
            print("foods_linked", cur.fetchone())
            cur.execute(
                "SELECT COUNT(*) AS c FROM catalog_recipes WHERE affiliate_slug=%s",
                ("test-olive-oil",),
            )
            print("recipes_linked", cur.fetchone())
    finally:
        conn.close()


if __name__ == "__main__":
    main()
