"""Special-disease + allergen display labels (zh canonical, en/ja/ko via MySQL/xls)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .config import ROOT
from .health_flags import (
    BASE_ALLERGY_OPTIONS,
    CONDITION_OPTIONS,
    allergy_options,
    canonicalize_allergy_label,
)
from .recipes import normalize_lang

logger = logging.getLogger(__name__)

CONDITIONS_XLS = ROOT / "Conditions.xls"
ALLERGENS_XLS = ROOT / "Allergens.xls"

# Built-in fallbacks when MySQL/xls rows are empty (zh is always the stored value).
CONDITION_I18N: dict[str, dict[str, str]] = {
    "糖尿病": {"en": "Diabetes", "ja": "糖尿病", "ko": "당뇨병"},
    "中風": {"en": "Stroke", "ja": "脳卒中", "ko": "뇌졸중"},
    "痛風": {"en": "Gout", "ja": "痛風", "ko": "통풍"},
    "腎臟病": {"en": "Kidney disease", "ja": "腎臓病", "ko": "신장병"},
    "肝病": {"en": "Liver disease", "ja": "肝疾患", "ko": "간질환"},
    "高血壓": {"en": "Hypertension", "ja": "高血圧", "ko": "고혈압"},
    "服用抗凝血劑": {
        "en": "Taking anticoagulants",
        "ja": "抗凝固薬を服用中",
        "ko": "항응고제 복용",
    },
}

ALLERGEN_I18N: dict[str, dict[str, str]] = {
    "蝦蟹": {"en": "Shellfish (shrimp/crab)", "ja": "エビ・カニ", "ko": "새우·게"},
    "魚": {"en": "Fish", "ja": "魚", "ko": "생선"},
    "芒果": {"en": "Mango", "ja": "マンゴー", "ko": "망고"},
    "花生": {"en": "Peanut", "ja": "落花生", "ko": "땅콩"},
    "堅果": {"en": "Tree nuts", "ja": "ナッツ類", "ko": "견과류"},
    "雞蛋": {"en": "Egg", "ja": "鶏卵", "ko": "달걀"},
    "牛奶": {"en": "Milk", "ja": "牛乳", "ko": "우유"},
    "蛋": {"en": "Egg", "ja": "卵", "ko": "달걀"},
}

LABEL_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS catalog_health_labels (
  label_id INT AUTO_INCREMENT PRIMARY KEY,
  kind ENUM('condition','allergen') NOT NULL,
  name_zh VARCHAR(128) NOT NULL,
  name_en VARCHAR(255) NULL,
  name_ja VARCHAR(255) NULL,
  name_ko VARCHAR(255) NULL,
  sort_order INT NOT NULL DEFAULT 0,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_health_labels_kind_zh (kind, name_zh),
  INDEX idx_health_labels_kind (kind)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

RECIPE_TRANSLATIONS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS recipe_translations (
  recipe_id INT NOT NULL,
  lang VARCHAR(8) NOT NULL,
  recipe MEDIUMTEXT NULL,
  method MEDIUMTEXT NULL,
  benefit TEXT NULL,
  ban TEXT NULL,
  allergens TEXT NULL,
  nutrient TEXT NULL,
  source_hash VARCHAR(64) NULL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (recipe_id, lang),
  CONSTRAINT fk_recipe_tr_recipe
    FOREIGN KEY (recipe_id) REFERENCES catalog_recipes(recipe_id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

LONG_TEXT_FIELDS = ("recipe", "method", "benefit", "ban", "allergens", "nutrient")


def _connect():
    from .db import connect

    return connect(ensure=False)


def ensure_label_tables() -> None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(LABEL_SCHEMA_SQL)
            cur.execute(RECIPE_TRANSLATIONS_SCHEMA_SQL)
    finally:
        conn.close()


def _pick_lang_field(row: dict[str, Any], lang: str, zh: str) -> str:
    code = normalize_lang(lang)
    if code == "zh":
        return zh
    key = {"en": "name_en", "ja": "name_ja", "ko": "name_ko"}.get(code, "name_en")
    text = str(row.get(key) or "").strip()
    return text or zh


def _builtin_label(kind: str, zh: str, lang: str) -> str:
    code = normalize_lang(lang)
    if code == "zh":
        return zh
    table = CONDITION_I18N if kind == "condition" else ALLERGEN_I18N
    return (table.get(zh) or {}).get(code) or zh


def _load_mysql_labels(kind: str) -> dict[str, dict[str, str]]:
    try:
        ensure_label_tables()
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT name_zh, name_en, name_ja, name_ko, sort_order
                    FROM catalog_health_labels
                    WHERE kind=%s
                    ORDER BY sort_order, label_id
                    """,
                    (kind,),
                )
                rows = cur.fetchall() or []
        finally:
            conn.close()
    except Exception:
        logger.exception("load catalog_health_labels kind=%s failed", kind)
        return {}
    out: dict[str, dict[str, str]] = {}
    for row in rows:
        zh = str(row.get("name_zh") or "").strip()
        if not zh:
            continue
        out[zh] = {
            "name_zh": zh,
            "name_en": str(row.get("name_en") or "").strip(),
            "name_ja": str(row.get("name_ja") or "").strip(),
            "name_ko": str(row.get("name_ko") or "").strip(),
            "sort_order": int(row.get("sort_order") or 0),
        }
    return out


def _food_lookup_label(zh: str, lang: str) -> str | None:
    """COALESCE allergen display from catalog_foods / Foods.xls name_* columns."""
    code = normalize_lang(lang)
    if code == "zh":
        return zh
    try:
        from .recipe_ensure import load_food_name_index

        row = load_food_name_index().get(zh)
    except Exception:
        row = None
    if not row:
        return None
    field = {"en": "name_en", "ja": "name_ja", "ko": "name_ko"}.get(code)
    text = str((row or {}).get(field) or "").strip()
    return text or None


def localize_label(kind: str, zh: str, lang: str, mysql_map: dict[str, dict[str, str]] | None = None) -> str:
    code = normalize_lang(lang)
    name = (zh or "").strip()
    if not name or code == "zh":
        return name
    rows = mysql_map if mysql_map is not None else _load_mysql_labels(kind)
    if name in rows:
        picked = _pick_lang_field(rows[name], code, name)
        if picked != name:
            return picked
    if kind == "allergen":
        food = _food_lookup_label(name, code)
        if food:
            return food
    return _builtin_label(kind, name, code)


def labeled_options(kind: str, values: list[str] | tuple[str, ...], lang: str) -> list[dict[str, str]]:
    mysql_map = _load_mysql_labels(kind)
    out: list[dict[str, str]] = []
    for zh in values:
        text = (zh or "").strip()
        if not text:
            continue
        out.append(
            {
                "value": text,
                "label": localize_label(kind, text, lang, mysql_map),
            }
        )
    return out


def flags_payload(lang: str) -> dict[str, Any]:
    code = normalize_lang(lang)
    conditions = labeled_options("condition", CONDITION_OPTIONS, code)
    allergies = labeled_options("allergen", allergy_options(), code)
    return {
        "lang": code,
        "conditions": conditions,
        "allergies": allergies,
        "allergy_options": allergies,
        # Convenience flat lists (localized display) for older clients.
        "condition_labels": [item["label"] for item in conditions],
        "allergy_labels": [item["label"] for item in allergies],
        # Canonical zh values (storage / matching).
        "condition_values": [item["value"] for item in conditions],
        "allergy_values": [item["value"] for item in allergies],
    }


def _xls_rows(path: Path) -> list[dict[str, str]]:
    import xlrd

    if not path.exists():
        return []
    sheet = xlrd.open_workbook(str(path)).sheet_by_index(0)
    if sheet.nrows < 2:
        return []
    headers = [str(sheet.cell_value(0, c)).strip() for c in range(sheet.ncols)]
    index = {h: i for i, h in enumerate(headers) if h}

    def cell(r: int, *names: str) -> str:
        for name in names:
            if name in index:
                return str(sheet.cell_value(r, index[name])).strip()
        return ""

    rows: list[dict[str, str]] = []
    for r in range(1, sheet.nrows):
        zh = cell(r, "中文", "name_zh", "特殊疾病中文", "過敏原中文", "病症中文")
        if not zh:
            continue
        rows.append(
            {
                "name_zh": zh,
                "name_en": cell(r, "英文", "name_en", "特殊疾病英文", "過敏原英文", "病症英文"),
                "name_ja": cell(r, "日文", "name_ja", "特殊疾病日文", "過敏原日文", "病症日文"),
                "name_ko": cell(r, "韓文", "name_ko", "特殊疾病韓文", "過敏原韓文", "病症韓文"),
            }
        )
    return rows


def default_seed_rows() -> dict[str, list[dict[str, Any]]]:
    conditions = []
    for i, zh in enumerate(CONDITION_OPTIONS):
        pack = CONDITION_I18N.get(zh, {})
        conditions.append(
            {
                "kind": "condition",
                "name_zh": zh,
                "name_en": pack.get("en", ""),
                "name_ja": pack.get("ja", ""),
                "name_ko": pack.get("ko", ""),
                "sort_order": i,
            }
        )
    allergens = []
    for i, zh in enumerate(BASE_ALLERGY_OPTIONS):
        pack = ALLERGEN_I18N.get(zh, {})
        allergens.append(
            {
                "kind": "allergen",
                "name_zh": zh,
                "name_en": pack.get("en", ""),
                "name_ja": pack.get("ja", ""),
                "name_ko": pack.get("ko", ""),
                "sort_order": i,
            }
        )
    # Extra allergen groups / aliases commonly missing from Foods.xls
    extras = [
        ("蝦蟹", ALLERGEN_I18N["蝦蟹"]),
        ("魚", ALLERGEN_I18N["魚"]),
        ("堅果", ALLERGEN_I18N["堅果"]),
        ("蛋", ALLERGEN_I18N["蛋"]),
    ]
    seen = {a["name_zh"] for a in allergens}
    for zh, pack in extras:
        if zh in seen:
            continue
        allergens.append(
            {
                "kind": "allergen",
                "name_zh": zh,
                "name_en": pack.get("en", ""),
                "name_ja": pack.get("ja", ""),
                "name_ko": pack.get("ko", ""),
                "sort_order": len(allergens),
            }
        )
        seen.add(zh)
    return {"condition": conditions, "allergen": allergens}


def upsert_health_labels(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    ensure_label_tables()
    conn = _connect()
    try:
        with conn.cursor() as cur:
            for row in rows:
                cur.execute(
                    """
                    INSERT INTO catalog_health_labels
                      (kind, name_zh, name_en, name_ja, name_ko, sort_order)
                    VALUES
                      (%(kind)s, %(name_zh)s, %(name_en)s, %(name_ja)s, %(name_ko)s, %(sort_order)s)
                    ON DUPLICATE KEY UPDATE
                      name_en=IF(VALUES(name_en)='', name_en, VALUES(name_en)),
                      name_ja=IF(VALUES(name_ja)='', name_ja, VALUES(name_ja)),
                      name_ko=IF(VALUES(name_ko)='', name_ko, VALUES(name_ko)),
                      sort_order=VALUES(sort_order)
                    """,
                    {
                        "kind": row["kind"],
                        "name_zh": row["name_zh"],
                        "name_en": row.get("name_en") or "",
                        "name_ja": row.get("name_ja") or "",
                        "name_ko": row.get("name_ko") or "",
                        "sort_order": int(row.get("sort_order") or 0),
                    },
                )
        return len(rows)
    finally:
        conn.close()


def sync_health_labels_from_xls(*, force: bool = False) -> dict[str, int]:
    """Import Conditions.xls / Allergens.xls (+ builtin seeds) into MySQL."""
    ensure_label_tables()
    stats = {"conditions": 0, "allergens": 0, "seeded": 0}
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM catalog_health_labels")
            count = int((cur.fetchone() or {}).get("c") or 0)
    finally:
        conn.close()
    if count and not force:
        return stats

    seeds = default_seed_rows()
    condition_rows = []
    for i, row in enumerate(_xls_rows(CONDITIONS_XLS) or seeds["condition"]):
        condition_rows.append(
            {
                "kind": "condition",
                "name_zh": row["name_zh"],
                "name_en": row.get("name_en") or "",
                "name_ja": row.get("name_ja") or "",
                "name_ko": row.get("name_ko") or "",
                "sort_order": i,
            }
        )
    allergen_rows = []
    xls_allergens = _xls_rows(ALLERGENS_XLS)
    base = xls_allergens or seeds["allergen"]
    for i, row in enumerate(base):
        allergen_rows.append(
            {
                "kind": "allergen",
                "name_zh": canonicalize_allergy_label(row["name_zh"]) or row["name_zh"],
                "name_en": row.get("name_en") or "",
                "name_ja": row.get("name_ja") or "",
                "name_ko": row.get("name_ko") or "",
                "sort_order": i,
            }
        )
    stats["conditions"] = upsert_health_labels(condition_rows)
    stats["allergens"] = upsert_health_labels(allergen_rows)
    stats["seeded"] = stats["conditions"] + stats["allergens"]
    logger.info("catalog_health_labels synced: %s", stats)
    return stats


def write_seed_xls_files() -> dict[str, str]:
    """Create/overwrite Conditions.xls + Allergens.xls from builtin translations."""
    import xlwt

    def write(path: Path, headers: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
        book = xlwt.Workbook()
        sheet = book.add_sheet("labels")
        for c, h in enumerate(headers):
            sheet.write(0, c, h)
        for r, row in enumerate(rows, start=1):
            sheet.write(r, 0, row["name_zh"])
            sheet.write(r, 1, row.get("name_en") or "")
            sheet.write(r, 2, row.get("name_ja") or "")
            sheet.write(r, 3, row.get("name_ko") or "")
        book.save(str(path))

    seeds = default_seed_rows()
    write(
        CONDITIONS_XLS,
        ("特殊疾病中文", "特殊疾病英文", "特殊疾病日文", "特殊疾病韓文"),
        seeds["condition"],
    )
    write(
        ALLERGENS_XLS,
        ("過敏原中文", "過敏原英文", "過敏原日文", "過敏原韓文"),
        seeds["allergen"],
    )
    return {"Conditions.xls": str(CONDITIONS_XLS), "Allergens.xls": str(ALLERGENS_XLS)}


def fetch_recipe_translations(recipe_ids: list[int], lang: str) -> dict[int, dict[str, str]]:
    """Batch-load recipe_translations for COALESCE into detail/list payloads."""
    code = normalize_lang(lang)
    if code == "zh" or not recipe_ids:
        return {}
    ids = sorted({int(i) for i in recipe_ids if i is not None})
    if not ids:
        return {}
    ensure_label_tables()
    out: dict[int, dict[str, str]] = {}
    conn = _connect()
    try:
        with conn.cursor() as cur:
            # Chunk IN lists to stay under packet limits.
            for start in range(0, len(ids), 200):
                chunk = ids[start : start + 200]
                placeholders = ",".join(["%s"] * len(chunk))
                cur.execute(
                    f"""
                    SELECT recipe_id, recipe, method, benefit, ban, allergens, nutrient
                    FROM recipe_translations
                    WHERE lang=%s AND recipe_id IN ({placeholders})
                    """,
                    (code, *chunk),
                )
                for row in cur.fetchall() or []:
                    rid = int(row["recipe_id"])
                    out[rid] = {
                        field: str(row.get(field) or "").strip()
                        for field in LONG_TEXT_FIELDS
                    }
    except Exception:
        logger.exception("fetch_recipe_translations failed lang=%s", code)
        return {}
    finally:
        conn.close()
    return out


def coalesce_recipe_long_fields(row: dict[str, Any], tr: dict[str, str] | None) -> dict[str, Any]:
    """LEFT JOIN semantics: COALESCE(NULLIF(tr.col,''), base_zh)."""
    if not tr:
        return row
    merged = dict(row)
    for field in LONG_TEXT_FIELDS:
        translated = str(tr.get(field) or "").strip()
        if translated:
            merged[field] = translated
    return merged
