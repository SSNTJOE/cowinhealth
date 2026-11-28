#!/usr/bin/env python3
"""Batch-translate catalog_recipes long fields into recipe_translations via Gemini.

Content shape (inspected 2026-11-28): plain Traditional Chinese text for
recipe / method / benefit / ban / allergens / nutrient — not HTML, not JSON.
Titles stay on catalog_recipes.name_zh/en/ja/ko (not rewritten here).

Usage:
  python scripts/translate_recipes.py --lang en --limit 20 --dry-run
  python scripts/translate_recipes.py --lang ja --batch-size 10

Requires GEMINI_API_KEY (or GOOGLE_API_KEY). Without a key, runs dry-run only.
Resume-safe: skips rows that already have recipe_translations for the lang
(NOT EXISTS). Optional source_hash skips unchanged zh bodies.

Shared helpers live in app.recipe_translate (also used by BackgroundTasks on
POST /api/recipes/create|ensure).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app.recipe_translate import (  # noqa: E402
    LONG_FIELDS,
    gemini_translate,
    has_gemini_key,
    source_hash,
    upsert_translation,
)


def pending_rows(lang: str, limit: int) -> list[dict]:
    from app.db import connect, init_schema
    from app.health_labels import ensure_label_tables

    init_schema()
    ensure_label_tables()
    conn = connect(ensure=False)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.recipe_id, r.name_zh, r.recipe, r.method, r.benefit,
                       r.ban, r.allergens, r.nutrient
                FROM catalog_recipes r
                WHERE NOT EXISTS (
                  SELECT 1 FROM recipe_translations t
                  WHERE t.recipe_id = r.recipe_id AND t.lang = %s
                )
                ORDER BY r.recipe_id
                LIMIT %s
                """,
                (lang, limit),
            )
            return list(cur.fetchall() or [])
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lang", choices=("en", "ja", "ko"), required=True)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List pending rows without calling Gemini / writing MySQL",
    )
    args = parser.parse_args()

    dry = args.dry_run or not has_gemini_key()
    if not has_gemini_key():
        print("No GEMINI_API_KEY — forcing dry-run.")

    rows = pending_rows(args.lang, args.limit)
    print(f"pending lang={args.lang} count={len(rows)} dry_run={dry}")
    if not rows:
        return 0

    for row in rows[: min(3, len(rows))]:
        print(
            f"  sample id={row['recipe_id']} name={row.get('name_zh')} "
            f"recipe={str(row.get('recipe') or '')[:60]!r}"
        )

    if dry:
        print("Dry-run complete (no writes).")
        return 0

    ok = 0
    errors = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        batch_size = max(1, int(args.batch_size))
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            futures = {
                pool.submit(gemini_translate, row, args.lang): row for row in batch
            }
            for fut in as_completed(futures):
                row = futures[fut]
                try:
                    fields = fut.result()
                    digest = source_hash(row)
                    upsert_translation(args.lang, int(row["recipe_id"]), fields, digest)
                    ok += 1
                    print(f"ok recipe_id={row['recipe_id']}")
                except Exception as exc:
                    errors += 1
                    print(f"fail recipe_id={row['recipe_id']}: {exc}")
            time.sleep(0.2)

    print(f"done ok={ok} errors={errors}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
