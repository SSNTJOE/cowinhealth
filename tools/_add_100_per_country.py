# -*- coding: utf-8 -*-
"""Add 100 NEW recipes per existing catalog_recipes country (incl. Global).

Fills all Recipe columns (text + nutrients), appends missing Foods with stubs,
then exports Recipe.xls / Foods.xls. Uses curated pools from fill_recipes_per_country.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import fill_recipes_per_country as fr  # noqa: E402
from app.db import connect  # noqa: E402
from app.recipe_ensure import ALLERGEN_FOODS, format_ingredients, _normalize_grams  # noqa: E402
from app.shared_catalog import (  # noqa: E402
    COLUMN_FIELDS,
    NUTRIENT_FIELDS,
    append_missing_foods,
    export_foods_xls,
    export_recipes_xls,
    invalidate_foods_mysql_cache,
    invalidate_recipe_mysql_cache,
)

# Soft nutrient totals from teaching table (skip unknown ingredients).
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "fill_recipe_nutrients", ROOT / "_fill_recipe_nutrients.py"
)
_nut = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_nut)

NUT_KEYS = [f for f, _ in NUTRIENT_FIELDS]
STYLE_SUFFIX = (
    ("家常", "home style"),
    ("清淡", "light"),
    ("濃郁", "rich"),
    ("快炒", "stir-fry"),
    ("燉煮", "stew"),
    ("烤焗", "baked"),
    ("湯品", "soup"),
    ("冷盤", "cold plate"),
    ("一鍋", "one-pot"),
    ("時令", "seasonal"),
    ("街頭", "street"),
    ("宴客", "banquet"),
    ("早餐", "breakfast"),
    ("午膳", "lunch"),
    ("晚膳", "dinner"),
    ("小食", "snack"),
    ("素雅", "simple"),
    ("香料", "spiced"),
    ("鮮香", "aromatic"),
    ("養生", "wellness"),
)

# Extra aliases so cuisine stubs resolve to Foods / nutrient table names.
EXTRA_ALIASES = {
    "薑": "生薑",
    "白菜": "大白菜",
    "起司": "起司",
    "雞蛋": "雞蛋",
    "味噌": "味噌",
    "海苔": "海苔",
    "醬油": "醬油",
    "麻油": "麻油",
    "花生油": "花生油",
    "橄欖油": "橄欖油",
    "優格": "優格",
    "奶油": "奶油",
    "牛奶": "牛奶",
    "食鹽": "食鹽",
    "辣椒": "辣椒",
    "蝦": "蝦",
    "羊肉": "羊肉",
    "牛肉": "牛肉",
    "豬肉": "豬肉",
    "雞肉": "雞肉",
    "鮭魚": "鮭魚",
    "鱸魚": "鱸魚",
    "椰漿": "椰漿",
    "豆腐": "豆腐",
    "蔥": "蔥",
    "大蒜": "大蒜",
    "洋蔥": "洋蔥",
    "番茄": "番茄",
    "胡蘿蔔": "胡蘿蔔",
    "馬鈴薯": "馬鈴薯",
    "粳米": "粳米",
    "小麥": "小麥",
    "玉米": "玉米",
    "菠菜": "菠菜",
    "甜椒": "甜椒",
    "香菜": "香菜",
    "檸檬": "檸檬",
    "蘋果": "蘋果",
    "黃瓜": "黃瓜",
    "核桃": "核桃",
    "花生": "花生",
}


def setup_log() -> logging.Logger:
    log = fr.setup_logging()
    return log


def soft_nutrients(recipe_text: str) -> dict[str, float | None]:
    """Return nutrient field dict; soft-skip unknown ingredients."""
    out: dict[str, float | None] = {k: None for k in NUT_KEYS}
    text = (recipe_text or "").strip()
    if not text:
        return out
    food_table = _nut.N
    sums = [0.0] * len(_nut.HEADERS)
    any_hit = False
    for chunk in text.split("、"):
        try:
            parts = _nut.parse_recipe(chunk)
        except Exception:
            continue
        for name, grams in parts:
            row = food_table.get(name)
            if row is None:
                # try alias
                alt = EXTRA_ALIASES.get(name) or fr._ING_ALIASES.get(name)
                row = food_table.get(alt) if alt else None
            if row is None:
                continue
            any_hit = True
            factor = float(grams) / 100.0
            for i, raw in enumerate(row):
                sums[i] += float(raw) * factor * float(_nut.TO_G[i])
    if not any_hit:
        return out
    values = [round(v, int(_nut.DIGITS[i])) for i, v in enumerate(sums)]
    for key, val in zip(NUT_KEYS, values):
        out[key] = val
    return out


def resolve_ing(name: str, food_set: set[str]) -> str:
    if name in food_set:
        return name
    for table in (EXTRA_ALIASES, fr._ING_ALIASES):
        alt = table.get(name)
        if alt and alt in food_set:
            return alt
        if alt and alt in _nut.N:
            return alt
    if name in _nut.N:
        return name
    alt = EXTRA_ALIASES.get(name) or fr._ING_ALIASES.get(name)
    return alt or name


def build_pairs(country: str, food_set: set[str], dish_idx: int) -> list[tuple[str, int]]:
    base = fr.CUISINE_ING[fr.cuisine_for(country)]
    rot = dish_idx % len(base)
    rotated = base[rot:] + base[:rot]
    pairs = [(resolve_ing(n, food_set), g) for n, g in rotated[:8]]
    seen: dict[str, int] = {}
    for n, g in pairs:
        seen.setdefault(n, g)
    return _normalize_grams(list(seen.items()), total=500)


def expand_candidates(country: str, need: int) -> list[tuple[str, str, str, str]]:
    primary = fr.dish_candidates(country)
    out: list[tuple[str, str, str, str]] = []
    for item in primary:
        zh, en = item[0], item[1]
        ja = item[2] if len(item) > 2 else ""
        ko = item[3] if len(item) > 3 else ""
        out.append((zh, en, ja, ko))
    # Style variants until we have enough unique bases
    n = 0
    while len(out) < need + 40:
        base = primary[n % len(primary)]
        style_zh, style_en = STYLE_SUFFIX[n % len(STYLE_SUFFIX)]
        wave = n // len(STYLE_SUFFIX) + 1
        zh = f"{base[0]}·{style_zh}"
        en = f"{base[1]} ({style_en})"
        if wave > 1:
            zh = f"{zh}{wave}"
            en = f"{en} {wave}"
        ja = (base[2] if len(base) > 2 and base[2] else base[0]) + f"·{style_zh}"
        ko = (base[3] if len(base) > 3 and base[3] else base[0]) + f"·{style_zh}"
        out.append((zh, en, ja, ko))
        n += 1
    return out


def make_row(
    country: str,
    zh: str,
    en: str,
    ja: str,
    ko: str,
    pairs: list[tuple[str, int]],
) -> dict:
    recipe = format_ingredients(pairs)
    allergens = "、".join(n for n, _ in pairs if n in ALLERGEN_FOODS)
    method = (
        f"教學示範煮法（{country}）：備齊{'、'.join(n for n, _ in pairs[:5])}等材料，"
        f"依常法清洗切配後加熱至熟透，調味盛盤。請依實際食材調整。"
    )
    top = "、".join(n for n, _ in pairs[:4])
    benefit = f"教學示範：以{top}搭配，均衡蛋白質與蔬菜，可作日常參考餐。"
    ban = "教學示範：過敏者避開標示過敏原；特殊飲食請諮詢專業人士。"
    nutrient = "、".join(f"{n}:待補" for n, _ in pairs[:4])
    row = {
        "country": country,
        "name_zh": zh,
        "name_en": en,
        "name_ja": ja or "",
        "name_ko": ko or "",
        "recipe": recipe,
        "method": method,
        "benefit": benefit,
        "ban": ban,
        "nutrient": nutrient,
        "allergens": allergens,
    }
    row.update(soft_nutrients(recipe))
    return row


def load_state() -> tuple[Counter, dict[str, set[str]], set[str]]:
    counts, names = fr.load_counts_and_names()
    food_set = fr.load_food_set()
    return counts, names, food_set


def build_country_rows(
    country: str,
    need: int,
    existing_names: set[str],
    food_set: set[str],
) -> tuple[list[dict], list[str]]:
    candidates = expand_candidates(country, need)
    used = set(existing_names)
    rows: list[dict] = []
    foods_used: list[str] = []
    idx = 0
    attempt = 0
    while len(rows) < need and attempt < need + 200:
        attempt += 1
        if idx >= len(candidates):
            n = len(rows) + attempt
            item = (f"{country}家常菜{n}", f"{country} home dish {n}", "", "")
        else:
            item = candidates[idx]
            idx += 1
        zh, en, ja, ko = item
        base_zh, base_en = zh, en
        suffix = 2
        while zh.casefold() in used or en.casefold() in used:
            zh = f"{base_zh}（{country}{suffix}）"
            en = f"{base_en} ({country} {suffix})"
            suffix += 1
            if suffix > 50:
                break
        pairs = build_pairs(country, food_set, len(rows) + attempt)
        row = make_row(country, zh, en, ja, ko, pairs)
        used.add(zh.casefold())
        used.add(en.casefold())
        foods_used.extend(n for n, _ in pairs)
        rows.append(row)
    return rows, foods_used


def bulk_insert(rows: list[dict], batch_size: int = 250) -> int:
    if not rows:
        return 0
    cols = [f for f, _ in COLUMN_FIELDS] + [f for f, _ in NUTRIENT_FIELDS]
    placeholders = ", ".join(f"%({c})s" for c in cols)
    col_sql = ", ".join(cols)
    sql = f"INSERT INTO catalog_recipes ({col_sql}) VALUES ({placeholders})"
    inserted = 0
    conn = connect()
    try:
        with conn.cursor() as cur:
            for i in range(0, len(rows), batch_size):
                chunk = rows[i : i + batch_size]
                payloads = []
                for r in chunk:
                    p = {f: (r.get(f) or "") for f, _ in COLUMN_FIELDS}
                    for f, _ in NUTRIENT_FIELDS:
                        v = r.get(f)
                        p[f] = None if v is None or v == "" else float(v)
                    payloads.append(p)
                cur.executemany(sql, payloads)
                inserted += len(payloads)
        conn.commit()
    finally:
        conn.close()
    return inserted


def enrich_foods_from_table(names: list[str]) -> int:
    """Upsert missing foods with nutrient + stub i18n from teaching table."""
    from app.shared_catalog import upsert_food, fetch_foods_index

    index = fetch_foods_index() or {}
    added = 0
    for name in names:
        zh = str(name or "").strip()
        if not zh:
            continue
        existing = index.get(zh)
        need_nut = not existing or not existing.get("kcal")
        # Only create / patch when missing entirely or missing kcal
        row = _nut.N.get(zh)
        if row is None:
            alt = EXTRA_ALIASES.get(zh) or fr._ING_ALIASES.get(zh)
            row = _nut.N.get(alt) if alt else None
        if existing and not need_nut:
            continue
        if not existing:
            payload: dict = {
                "name_zh": zh,
                "name_en": "",
                "name_ja": "",
                "name_ko": "",
                "benefit": "教學示範：常見食材，可作日常搭配參考。",
                "ban": "教學示範：過敏或特殊飲食請諮詢專業人士。",
                "nutrient": "網路搜尋待補（教學示範）",
            }
            if row is not None:
                # per-100g values converted like Foods.xls
                vals = [
                    round(float(raw) * float(_nut.TO_G[i]), int(_nut.DIGITS[i]))
                    for i, raw in enumerate(row)
                ]
                for key, val in zip(NUT_KEYS, vals):
                    payload[key] = val
            upsert_food(payload)
            index[zh] = payload
            added += 1
        elif row is not None and need_nut:
            payload = {"name_zh": zh}
            vals = [
                round(float(raw) * float(_nut.TO_G[i]), int(_nut.DIGITS[i]))
                for i, raw in enumerate(row)
            ]
            for key, val in zip(NUT_KEYS, vals):
                payload[key] = val
            upsert_food(payload)
            added += 1
    return added


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--add", type=int, default=100, help="New recipes per country")
    parser.add_argument("--countries", nargs="*", default=None)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--skip-export", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-size", type=int, default=250)
    args = parser.parse_args()
    log = setup_log()
    t0 = time.time()

    # Ensure Global maps to a cuisine pool
    if "Global" not in fr.COUNTRY_POOL:
        fr.COUNTRY_POOL["Global"] = "generic"

    counts, names, food_set = load_state()
    countries = sorted(c for c in counts if c and c != "(empty)")
    if args.countries:
        wanted = set(args.countries)
        countries = [c for c in countries if c in wanted]
    if args.offset:
        countries = countries[args.offset :]
    if args.limit and args.limit > 0:
        countries = countries[: args.limit]

    log.info(
        "ADD start add=%s countries=%s expected~%s",
        args.add,
        len(countries),
        args.add * len(countries),
    )
    print(f"countries={len(countries)} add={args.add} expected~{args.add * len(countries)}")

    all_rows: list[dict] = []
    all_foods: list[str] = []
    per_country: dict[str, int] = {}

    for i, country in enumerate(countries, start=1):
        have = counts[country]
        rows, foods = build_country_rows(country, args.add, names[country], food_set)
        per_country[country] = len(rows)
        all_rows.extend(rows)
        all_foods.extend(foods)
        if i % 20 == 0 or i == len(countries):
            log.info(
                "built %s/%s country=%s +%s total_rows=%s",
                i,
                len(countries),
                country,
                len(rows),
                len(all_rows),
            )
            print(f"built {i}/{len(countries)} {country} +{len(rows)} total={len(all_rows)}")

    if args.dry_run:
        print(f"DRY RUN rows={len(all_rows)} foods_candidates={len(set(all_foods))}")
        return 0

    log.info("bulk_insert rows=%s", len(all_rows))
    inserted = bulk_insert(all_rows, batch_size=args.batch_size)
    log.info("inserted=%s elapsed=%.1fs", inserted, time.time() - t0)
    print(f"inserted={inserted}")

    unique_foods = sorted({f for f in all_foods if f})
    log.info("enrich foods candidates=%s", len(unique_foods))
    # Ensure stubs exist first
    try:
        stubs = append_missing_foods(unique_foods)
        log.info("food stubs added=%s", len(stubs))
    except Exception as exc:
        log.exception("append_missing_foods: %s", exc)
        stubs = []
    enriched = enrich_foods_from_table(unique_foods)
    log.info("foods enriched/added=%s", enriched)

    invalidate_recipe_mysql_cache()
    invalidate_foods_mysql_cache()

    if not args.skip_export:
        log.info("exporting xls")
        rp = export_recipes_xls()
        fp = export_foods_xls()
        log.info("exported %s %s", rp, fp)
        print(f"EXPORTED {rp} {fp}")

    # Final counts
    final, _ = fr.load_counts_and_names()
    short = [(c, final[c] - counts[c], final[c]) for c in countries]
    under = [c for c, added, now in short if added < args.add]
    print("\n=== PER COUNTRY ADDED ===")
    for c, added, now in sorted(short, key=lambda x: x[0]):
        flag = " SHORT" if added < args.add else ""
        print(f"{c}\t+{added}\tnow={now}{flag}")
    print(
        f"\ncountries={len(countries)} inserted={inserted} "
        f"min_now={min(final[c] for c in countries)} "
        f"shortfalls={len(under)} elapsed={time.time()-t0:.1f}s"
    )
    # Write machine-readable summary next to logs
    summary = ROOT / "logs" / "per_country_add_100_summary.txt"
    summary.parent.mkdir(parents=True, exist_ok=True)
    with summary.open("w", encoding="utf-8") as fh:
        fh.write(f"inserted={inserted}\n")
        fh.write(f"countries={len(countries)}\n")
        fh.write(f"add={args.add}\n")
        fh.write(f"food_stubs={len(stubs)}\n")
        fh.write(f"foods_enriched={enriched}\n")
        for c, added, now in sorted(short, key=lambda x: x[0]):
            fh.write(f"{c}\t{counts[c]}\t+{added}\t{now}\n")
    log.info("summary %s", summary)
    return 0 if not under else 1


if __name__ == "__main__":
    raise SystemExit(main())
