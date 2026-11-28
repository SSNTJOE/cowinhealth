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
"""

from __future__ import annotations

import argparse
import hashlib
import json
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

LONG_FIELDS = ("recipe", "method", "benefit", "ban", "allergens", "nutrient")


def source_hash(row: dict) -> str:
    blob = "\n".join(str(row.get(f) or "") for f in LONG_FIELDS)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


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


def upsert_translation(lang: str, recipe_id: int, fields: dict, digest: str) -> None:
    from app.db import connect

    conn = connect(ensure=False)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO recipe_translations
                  (recipe_id, lang, recipe, method, benefit, ban, allergens, nutrient, source_hash)
                VALUES
                  (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  recipe=VALUES(recipe),
                  method=VALUES(method),
                  benefit=VALUES(benefit),
                  ban=VALUES(ban),
                  allergens=VALUES(allergens),
                  nutrient=VALUES(nutrient),
                  source_hash=VALUES(source_hash)
                """,
                (
                    recipe_id,
                    lang,
                    fields.get("recipe") or "",
                    fields.get("method") or "",
                    fields.get("benefit") or "",
                    fields.get("ban") or "",
                    fields.get("allergens") or "",
                    fields.get("nutrient") or "",
                    digest,
                ),
            )
    finally:
        conn.close()


def gemini_translate(row: dict, lang: str) -> dict:
    """Call Gemini with a structured JSON schema. Raises if no key / API error."""
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY / GOOGLE_API_KEY not set")

    try:
        import google.generativeai as genai
    except ImportError as exc:
        raise RuntimeError("pip install google-generativeai") from exc

    genai.configure(api_key=api_key)
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    model = genai.GenerativeModel(model_name)

    lang_name = {"en": "English", "ja": "Japanese", "ko": "Korean"}.get(lang, lang)
    payload = {field: str(row.get(field) or "") for field in LONG_FIELDS}
    prompt = (
        "Translate the following Traditional Chinese recipe fields into "
        f"{lang_name}. Return ONLY a JSON object with keys "
        f"{list(LONG_FIELDS)}. Preserve ingredient amounts, punctuation, and "
        "plain-text structure. Do not invent HTML or markdown. Keep empty "
        "strings empty.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    response = model.generate_content(
        prompt,
        generation_config={
            "response_mime_type": "application/json",
            "temperature": 0.2,
        },
    )
    text = getattr(response, "text", None) or ""
    data = json.loads(text)
    if not isinstance(data, dict):
        raise RuntimeError("Gemini returned non-object JSON")
    return {field: str(data.get(field) or "") for field in LONG_FIELDS}


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

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    dry = args.dry_run or not api_key
    if not api_key:
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
        futures = {}
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
