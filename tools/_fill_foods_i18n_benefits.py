# -*- coding: utf-8 -*-
"""Fill blank Foods.xls i18n + 益處/禁忌 columns, then sync to MySQL catalog_foods.

Blanks only — never overwrites non-empty cells. Ban derived from existing 益處
using the sheet's opposite-pattern rule (208/209 exact match on filled rows).
"""
from __future__ import annotations

import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FOODS_PATH = ROOT / "Foods.xls"
BACKUP_DIR = ROOT / "backups"

ORGANS = ("大腸", "小腸", "膀胱", "三焦", "心包", "肝", "心", "脾", "肺", "腎", "胃", "膽")
PATTERNS = ("實熱", "虛熱", "實寒", "虛寒")

# Explicit fills for the three fully blank rows (椰漿/白菜/薑) matching sheet tone.
EXPLICIT: dict[str, dict[str, str]] = {
    "椰漿": {
        "name_en": "coconut milk",
        "name_ja": "ココナッツミルク",
        "name_ko": "코코넛밀크",
        # Align with 椰子肉 / 椰子汁 — mild spleen/large-intestine deficiency support.
        "benefit": "脾虛熱,脾虛寒,大腸虛熱,大腸虛寒",
    },
    "白菜": {
        # Alias-style Chinese cabbage; match 大白菜 cooling tone.
        "name_en": "Chinese cabbage",
        "name_ja": "白菜",
        "name_ko": "배추",
        "benefit": "脾實熱,脾虛熱,大腸實熱,大腸虛熱,膀胱實熱,膀胱虛熱",
    },
    "薑": {
        # Short form of 生薑 — same warming tone.
        "name_en": "ginger",
        "name_ja": "ショウガ",
        "name_ko": "생강",
        "benefit": "脾實寒,脾虛寒,肺實寒,肺虛寒",
    },
}


def _blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _tokens(blob: str) -> list[str]:
    return [t.strip() for t in re.split(r"[,，、]", blob or "") if t.strip()]


def _organ_of(token: str) -> str | None:
    for organ in ORGANS:
        if token.startswith(organ):
            return organ
    return None


def _pattern_of(token: str) -> str | None:
    for pattern in PATTERNS:
        if token.endswith(pattern):
            return pattern
    return None


def ban_from_benefit(benefit: str) -> str:
    """Opposite-pattern 禁忌 from 益處 — matches existing Foods.xls style."""
    organs: dict[str, set[str]] = defaultdict(set)
    extras: list[str] = []
    for token in _tokens(benefit):
        organ = _organ_of(token)
        pattern = _pattern_of(token)
        if organ and pattern:
            organs[organ].add(pattern)
        elif token == "濕" or token.endswith("濕"):
            extras.append(token)
    out: list[str] = []
    # Preserve organ order as first appearance in benefit.
    seen: set[str] = set()
    organ_order: list[str] = []
    for token in _tokens(benefit):
        organ = _organ_of(token)
        if organ and organ not in seen:
            seen.add(organ)
            organ_order.append(organ)
    for organ in organ_order:
        patterns = organs[organ]
        heats = patterns & {"實熱", "虛熱"}
        colds = patterns & {"實寒", "虛寒"}
        if heats and not colds:
            out.extend([f"{organ}實寒", f"{organ}虛寒"])
        elif colds and not heats:
            out.extend([f"{organ}實熱", f"{organ}虛熱"])
        else:
            # Mixed deficiency tags → ban excess only (matches _guess_food_effect_tags).
            out.extend([f"{organ}實熱", f"{organ}實寒"])
    out.extend(extras)
    return ",".join(out)


def _backup() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = BACKUP_DIR / f"Foods.xls.bak-{stamp}-i18n"
    dest.write_bytes(FOODS_PATH.read_bytes())
    return dest


def fill_xls() -> dict:
    import xlrd

    backup = _backup()
    rb = xlrd.open_workbook(str(FOODS_PATH), formatting_info=True)
    sheet = rb.sheet_by_index(0)
    headers = [str(sheet.cell_value(0, c)).strip() for c in range(sheet.ncols)]
    need = ["食材中文", "食材英文", "食材日文", "食材韓文", "益處", "禁忌"]
    for name in need:
        if name not in headers:
            raise SystemExit(f"missing header {name}")
    zh_i, en_i, ja_i, ko_i, ben_i, ban_i = (headers.index(h) for h in need)

    try:
        from xlutils.copy import copy as xl_copy

        wb = xl_copy(rb)
        dest = wb.get_sheet(0)
        writer = "xlutils"
    except Exception:
        import xlwt

        wb = xlwt.Workbook(encoding="utf-8")
        dest = wb.add_sheet(sheet.name or "Foods")
        writer = "xlwt"
        for col in range(sheet.ncols):
            dest.write(0, col, sheet.cell_value(0, col))
        for row in range(1, sheet.nrows):
            for col in range(sheet.ncols):
                val = sheet.cell_value(row, col)
                if val != "":
                    dest.write(row, col, val)

    filled_en = filled_ja = filled_ko = filled_ben = filled_ban = 0
    rows_touched = 0
    explicit_names: list[str] = []
    ban_derived = 0

    for row in range(1, sheet.nrows):
        zh = str(sheet.cell_value(row, zh_i)).strip()
        if not zh:
            continue
        en = str(sheet.cell_value(row, en_i)).strip()
        ja = str(sheet.cell_value(row, ja_i)).strip()
        ko = str(sheet.cell_value(row, ko_i)).strip()
        ben = str(sheet.cell_value(row, ben_i)).strip()
        ban = str(sheet.cell_value(row, ban_i)).strip()
        touched = False
        explicit = EXPLICIT.get(zh)

        if explicit:
            if _blank(en) and explicit.get("name_en"):
                dest.write(row, en_i, explicit["name_en"])
                en = explicit["name_en"]
                filled_en += 1
                touched = True
            if _blank(ja) and explicit.get("name_ja"):
                dest.write(row, ja_i, explicit["name_ja"])
                ja = explicit["name_ja"]
                filled_ja += 1
                touched = True
            if _blank(ko) and explicit.get("name_ko"):
                dest.write(row, ko_i, explicit["name_ko"])
                ko = explicit["name_ko"]
                filled_ko += 1
                touched = True
            if _blank(ben) and explicit.get("benefit"):
                dest.write(row, ben_i, explicit["benefit"])
                ben = explicit["benefit"]
                filled_ben += 1
                touched = True
                explicit_names.append(zh)

        if _blank(ban) and ben:
            new_ban = ban_from_benefit(ben)
            if new_ban:
                dest.write(row, ban_i, new_ban)
                filled_ban += 1
                ban_derived += 1
                touched = True

        if touched:
            rows_touched += 1

    tmp = str(FOODS_PATH) + f".tmp-{os.getpid()}"
    wb.save(tmp)
    os.replace(tmp, str(FOODS_PATH))
    return {
        "backup": str(backup),
        "writer": writer,
        "total_rows": sheet.nrows - 1,
        "rows_touched": rows_touched,
        "filled_en": filled_en,
        "filled_ja": filled_ja,
        "filled_ko": filled_ko,
        "filled_benefit": filled_ben,
        "filled_ban": filled_ban,
        "ban_derived_from_benefit": ban_derived,
        "explicit_full_blank_rows": explicit_names,
    }


def sync_mysql() -> dict:
    """Push blank i18n/benefit/ban fields from Foods.xls into catalog_foods."""
    import xlrd
    from app.db import connect
    from app.shared_catalog import invalidate_foods_mysql_cache

    sheet = xlrd.open_workbook(str(FOODS_PATH)).sheet_by_index(0)
    headers = [str(sheet.cell_value(0, c)).strip() for c in range(sheet.ncols)]
    index = {name: i for i, name in enumerate(headers)}

    field_map = [
        ("name_en", "食材英文"),
        ("name_ja", "食材日文"),
        ("name_ko", "食材韓文"),
        ("benefit", "益處"),
        ("ban", "禁忌"),
    ]

    updated_rows = 0
    field_updates = {k: 0 for k, _ in field_map}
    skipped_no_match = 0
    skipped_nothing = 0

    conn = connect()
    try:
        with conn.cursor() as cur:
            for r in range(1, sheet.nrows):
                zh = str(sheet.cell_value(r, index["食材中文"])).strip()
                if not zh:
                    continue
                cur.execute(
                    "SELECT name_en, name_ja, name_ko, benefit, ban FROM catalog_foods WHERE name_zh=%s LIMIT 1",
                    (zh,),
                )
                row = cur.fetchone()
                if not row:
                    skipped_no_match += 1
                    continue
                sets = []
                vals = []
                for field, header in field_map:
                    xls_val = str(sheet.cell_value(r, index[header])).strip()
                    if not xls_val:
                        continue
                    db_val = str(row.get(field) or "").strip()
                    if db_val:
                        continue
                    sets.append(f"{field}=%s")
                    vals.append(xls_val)
                    field_updates[field] += 1
                if not sets:
                    skipped_nothing += 1
                    continue
                vals.append(zh)
                cur.execute(
                    f"UPDATE catalog_foods SET {', '.join(sets)} WHERE name_zh=%s",
                    vals,
                )
                if cur.rowcount and cur.rowcount > 0:
                    updated_rows += cur.rowcount
        conn.commit()
    finally:
        conn.close()

    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM catalog_foods")
            total = int((cur.fetchone() or {}).get("c") or 0)

            def blank_count(col: str) -> int:
                cur.execute(
                    f"SELECT COUNT(*) AS c FROM catalog_foods WHERE {col} IS NULL OR {col}=''"
                )
                return int((cur.fetchone() or {}).get("c") or 0)

            blanks = {col: blank_count(col) for col, _ in field_map}
            # Spot-check the three target foods
            cur.execute(
                "SELECT name_zh, name_en, name_ja, name_ko, benefit, ban "
                "FROM catalog_foods WHERE name_zh IN (%s,%s,%s)",
                ("椰漿", "白菜", "薑"),
            )
            spot = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    invalidate_foods_mysql_cache()
    return {
        "mysql_rows_updated": updated_rows,
        "mysql_field_updates": field_updates,
        "mysql_skipped_no_match": skipped_no_match,
        "mysql_skipped_already_or_blank_xls": skipped_nothing,
        "mysql_total": total,
        "mysql_blanks_after": blanks,
        "mysql_spot_check": spot,
    }


def verify_xls() -> dict:
    import xlrd

    sheet = xlrd.open_workbook(str(FOODS_PATH)).sheet_by_index(0)
    headers = [str(sheet.cell_value(0, c)).strip() for c in range(sheet.ncols)]
    index = {name: i for i, name in enumerate(headers)}
    blanks = {"en": 0, "ja": 0, "ko": 0, "benefit": 0, "ban": 0}
    spot = {}
    for r in range(1, sheet.nrows):
        zh = str(sheet.cell_value(r, index["食材中文"])).strip()
        en = str(sheet.cell_value(r, index["食材英文"])).strip()
        ja = str(sheet.cell_value(r, index["食材日文"])).strip()
        ko = str(sheet.cell_value(r, index["食材韓文"])).strip()
        ben = str(sheet.cell_value(r, index["益處"])).strip()
        ban = str(sheet.cell_value(r, index["禁忌"])).strip()
        if not en:
            blanks["en"] += 1
        if not ja:
            blanks["ja"] += 1
        if not ko:
            blanks["ko"] += 1
        if not ben:
            blanks["benefit"] += 1
        if not ban:
            blanks["ban"] += 1
        if zh in ("椰漿", "白菜", "薑"):
            spot[zh] = {"en": en, "ja": ja, "ko": ko, "benefit": ben, "ban": ban}
    return {"xls_blanks_after": blanks, "xls_spot_check": spot}


def main() -> None:
    print("=== fill Foods.xls i18n/benefits blanks ===")
    xls_stats = fill_xls()
    for k, v in xls_stats.items():
        print(f"xls {k}: {v}")
    print("=== verify xls ===")
    ver = verify_xls()
    for k, v in ver.items():
        print(f"xls {k}: {v}")
    print("=== sync MySQL blanks ===")
    db_stats = sync_mysql()
    for k, v in db_stats.items():
        print(f"db {k}: {v}")


if __name__ == "__main__":
    main()
