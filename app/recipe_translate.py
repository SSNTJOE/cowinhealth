"""Shared Gemini recipe translation helpers (batch script + BackgroundTasks).

Titles live on catalog_recipes.name_zh/en/ja/ko.
Long plain-text fields use recipe_translations (COALESCE fallback to zh baseline).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

from .config import ROOT
from .recipes import NAME_FIELDS, normalize_lang

logger = logging.getLogger(__name__)

LONG_FIELDS = ("recipe", "method", "benefit", "ban", "allergens", "nutrient")
UI_LANGS = ("zh", "en", "ja", "ko")
_LANG_NAMES = {
    "zh": "Traditional Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
}

_MISSING_KEY_LOGGED = False


def has_gemini_key() -> bool:
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


def log_missing_key_once() -> None:
    global _MISSING_KEY_LOGGED
    if _MISSING_KEY_LOGGED:
        return
    _MISSING_KEY_LOGGED = True
    logger.info(
        "recipe_translate: GEMINI_API_KEY / GOOGLE_API_KEY not set — skipping background translate"
    )


def source_hash(row: dict[str, Any]) -> str:
    blob = "\n".join(str(row.get(f) or "") for f in LONG_FIELDS)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def load_glossary() -> dict[str, Any]:
    """Optional TCM / term glossary (ROOT/glossary.json or app/glossary.json)."""
    for path in (ROOT / "glossary.json", ROOT / "app" / "glossary.json"):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            logger.exception("failed to load glossary %s", path)
    return {}


def gemini_translate(
    row: dict[str, Any],
    target_lang: str,
    *,
    source_lang: str = "zh",
    include_title: bool = False,
) -> dict[str, str]:
    """Call Gemini Flash with structured JSON. Raises if no key / API error.

    ``row`` should contain LONG_FIELDS (and optionally ``name`` / name_* for title).
    Returns translated long fields; when include_title, also includes ``name``.
    """
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY / GOOGLE_API_KEY not set")

    try:
        import google.generativeai as genai
    except ImportError as exc:
        raise RuntimeError("pip install google-generativeai") from exc

    code = normalize_lang(target_lang)
    src = normalize_lang(source_lang)
    if code == src:
        raise ValueError("target_lang must differ from source_lang")

    genai.configure(api_key=api_key)
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    model = genai.GenerativeModel(model_name)

    payload: dict[str, str] = {field: str(row.get(field) or "") for field in LONG_FIELDS}
    keys = list(LONG_FIELDS)
    if include_title:
        title = (
            str(row.get("name") or "").strip()
            or str(row.get(NAME_FIELDS.get(src, "name_zh")) or "").strip()
        )
        payload["name"] = title
        keys = ["name", *LONG_FIELDS]

    glossary = load_glossary()
    glossary_note = ""
    if glossary:
        glossary_note = (
            " Prefer these glossary mappings when present: "
            + json.dumps(glossary, ensure_ascii=False)[:2000]
            + "."
        )

    src_name = _LANG_NAMES.get(src, src)
    tgt_name = _LANG_NAMES.get(code, code)
    prompt = (
        f"Translate the following {src_name} recipe fields into {tgt_name}. "
        f"Return ONLY a JSON object with keys {keys}. "
        "Preserve HTML tags, newlines, punctuation, ingredient amounts, and "
        "placeholders like {price}. Do not invent HTML or markdown. "
        "Keep empty strings empty."
        f"{glossary_note}\n\n"
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
    out = {field: str(data.get(field) or "") for field in LONG_FIELDS}
    if include_title:
        out["name"] = str(data.get("name") or "").strip()
    return out


def upsert_translation(
    lang: str,
    recipe_id: int,
    fields: dict[str, Any],
    digest: str,
) -> None:
    from .db import connect
    from .health_labels import ensure_label_tables

    code = normalize_lang(lang)
    if code == "zh":
        return
    ensure_label_tables()
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
                    int(recipe_id),
                    code,
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


def update_name_columns(recipe_id: int, names: dict[str, str]) -> None:
    """Write non-empty name_zh/en/ja/ko onto catalog_recipes."""
    from .db import connect
    from .shared_catalog import invalidate_recipe_mysql_cache

    sets: list[str] = []
    values: list[Any] = []
    for lang, col in NAME_FIELDS.items():
        text = str(names.get(col) or names.get(lang) or "").strip()
        if not text:
            continue
        sets.append(f"`{col}` = %s")
        values.append(text)
    if not sets:
        return
    values.append(int(recipe_id))
    conn = connect(ensure=False)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE catalog_recipes SET " + ", ".join(sets) + " WHERE recipe_id = %s",
                values,
            )
    finally:
        conn.close()
    invalidate_recipe_mysql_cache()


def _load_recipe_row(recipe_id: int) -> dict[str, Any] | None:
    from .db import connect

    conn = connect(ensure=False)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT recipe_id, name_zh, name_en, name_ja, name_ko,
                       recipe, method, benefit, ban, allergens, nutrient
                FROM catalog_recipes
                WHERE recipe_id = %s
                """,
                (int(recipe_id),),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    except Exception:
        logger.exception("recipe_translate: load recipe_id=%s failed", recipe_id)
        return None
    finally:
        conn.close()


def _existing_translation_langs(recipe_id: int) -> set[str]:
    from .db import connect
    from .health_labels import ensure_label_tables

    ensure_label_tables()
    conn = connect(ensure=False)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT lang FROM recipe_translations
                WHERE recipe_id = %s
                  AND (
                    NULLIF(recipe,'') IS NOT NULL
                    OR NULLIF(method,'') IS NOT NULL
                    OR NULLIF(benefit,'') IS NOT NULL
                  )
                """,
                (int(recipe_id),),
            )
            return {normalize_lang(r["lang"]) for r in (cur.fetchall() or [])}
    except Exception:
        logger.exception("recipe_translate: list translations failed id=%s", recipe_id)
        return set()
    finally:
        conn.close()


def write_source_lang_fields(
    recipe_id: int,
    source_lang: str,
    *,
    title: str | None = None,
    body: dict[str, str] | None = None,
) -> None:
    """Persist user-submitted title/body into the source-lang column / translation row.

    zh title → name_zh; zh body → catalog_recipes baseline columns.
    Non-zh title → name_*; non-zh body → recipe_translations upsert.
    """
    code = normalize_lang(source_lang)
    if title and str(title).strip():
        col = NAME_FIELDS.get(code, "name_zh")
        update_name_columns(recipe_id, {col: str(title).strip()})
    if not body:
        return
    fields = {f: str(body.get(f) or "") for f in LONG_FIELDS}
    if not any(fields.values()):
        return
    if code == "zh":
        from .shared_catalog import update_recipe

        update_recipe(recipe_id, fields)
    else:
        upsert_translation(code, recipe_id, fields, source_hash(fields))


def translate_recipe_missing_langs(
    recipe_id: int,
    source_lang: str = "zh",
    *,
    skip_name_langs: list[str] | tuple[str, ...] | None = None,
    skip_body_langs: list[str] | tuple[str, ...] | None = None,
) -> None:
    """Background job: fill empty name_* + recipe_translations for the other langs.

    Failures are logged only — never raised to the HTTP caller.
    """
    if not has_gemini_key():
        log_missing_key_once()
        return

    rid = int(recipe_id)
    src = normalize_lang(source_lang)
    row = _load_recipe_row(rid)
    if not row:
        logger.warning("recipe_translate: recipe_id=%s not found", rid)
        return

    skip_names = {normalize_lang(x) for x in (skip_name_langs or [])}
    skip_bodies = {normalize_lang(x) for x in (skip_body_langs or [])}
    # Never overwrite the title the user just saved for their UI lang.
    skip_names.add(src)

    # Already-populated title columns count as explicit / researched — do not overwrite.
    for lang, col in NAME_FIELDS.items():
        if str(row.get(col) or "").strip():
            skip_names.add(lang)

    # Existing non-empty translation rows stay put.
    skip_bodies |= _existing_translation_langs(rid)
    # zh body lives on the main row — never write recipe_translations for zh.
    skip_bodies.add("zh")
    # Body baseline is always Chinese on catalog_recipes, so a non-zh UI source
    # still needs recipe_translations for that lang (and the other two).

    # Title source text from the UI lang column (fallback to any available name).
    title_src = str(row.get(NAME_FIELDS.get(src, "name_zh")) or "").strip()
    if not title_src:
        for col in ("name_zh", "name_en", "name_ja", "name_ko"):
            title_src = str(row.get(col) or "").strip()
            if title_src:
                break

    # Long-text source is always the Chinese baseline on catalog_recipes.
    body_src = {field: str(row.get(field) or "") for field in LONG_FIELDS}
    has_body = any(v.strip() for v in body_src.values())
    digest = source_hash(body_src)

    # Titles: other three langs. Body: en/ja/ko (whatever is still empty).
    title_targets = [lang for lang in UI_LANGS if lang not in skip_names]
    body_targets = [lang for lang in ("en", "ja", "ko") if lang not in skip_bodies]
    targets = sorted(set(title_targets) | set(body_targets))
    for target in targets:
        need_title = target not in skip_names and bool(title_src)
        need_body = target not in skip_bodies and has_body
        if not need_title and not need_body:
            continue
        try:
            name_text = ""
            body_fields: dict[str, str] = {}
            # Titles may be in the UI source lang; long text baseline is always zh.
            if need_title and need_body and src == "zh":
                payload = dict(body_src)
                payload["name"] = title_src
                translated = gemini_translate(
                    payload, target, source_lang="zh", include_title=True
                )
                name_text = str(translated.get("name") or "").strip()
                body_fields = {f: str(translated.get(f) or "") for f in LONG_FIELDS}
            else:
                if need_title:
                    title_row = {"name": title_src, **{f: "" for f in LONG_FIELDS}}
                    title_out = gemini_translate(
                        title_row, target, source_lang=src, include_title=True
                    )
                    name_text = str(title_out.get("name") or "").strip()
                if need_body:
                    body_fields = gemini_translate(
                        body_src, target, source_lang="zh", include_title=False
                    )
            if need_title and name_text:
                update_name_columns(rid, {NAME_FIELDS[target]: name_text})
            if need_body and body_fields:
                upsert_translation(target, rid, body_fields, digest)
            logger.info(
                "recipe_translate: ok recipe_id=%s target=%s title=%s body=%s",
                rid,
                target,
                need_title,
                need_body,
            )
        except Exception:
            logger.exception(
                "recipe_translate: failed recipe_id=%s target=%s", rid, target
            )


def schedule_recipe_translate(
    background_tasks: Any,
    recipe_id: int | str | None,
    source_lang: str,
    *,
    created: bool = False,
    updated: bool = False,
    skip_name_langs: list[str] | None = None,
    skip_body_langs: list[str] | None = None,
) -> bool:
    """Enqueue BackgroundTasks job when a recipe was created/updated. Returns True if queued."""
    if not created and not updated:
        return False
    if recipe_id is None or recipe_id == "":
        return False
    try:
        rid = int(recipe_id)
    except (TypeError, ValueError):
        return False
    if not has_gemini_key():
        log_missing_key_once()
        return False
    background_tasks.add_task(
        translate_recipe_missing_langs,
        rid,
        normalize_lang(source_lang),
        skip_name_langs=skip_name_langs,
        skip_body_langs=skip_body_langs,
    )
    return True
