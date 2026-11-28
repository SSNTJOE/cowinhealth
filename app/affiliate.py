"""Affiliate geo redirect + admin CRUD (PyMySQL only)."""

from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

from .config import AFFILIATE_ADMIN_PASSWORD, AFFILIATE_ADMIN_USER
from .db import connect

logger = logging.getLogger(__name__)

router = APIRouter()
_security = HTTPBasic()


def detect_country_code(request: Request) -> str:
    """
    自動偵測訪客國家代碼：
    1. 未來上線掛上 Cloudflare 後，會自動帶有 CF-IPCountry 標頭 (最準確)
    2. 目前本機開發階段，自動從瀏覽器/手機的 Accept-Language 判斷語系
    """
    cf_country = request.headers.get("CF-IPCountry")
    if cf_country:
        return cf_country.upper()

    accept_lang = request.headers.get("Accept-Language", "").lower()
    if "zh-tw" in accept_lang or "zh-hant" in accept_lang:
        return "TW"
    if "ja" in accept_lang:
        return "JP"
    if "en-us" in accept_lang or "en" in accept_lang:
        return "US"
    return "DEFAULT"


def increment_click_count(link_id: int) -> None:
    conn = None
    try:
        conn = connect(ensure=False)
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE affiliate_links SET click_count = click_count + 1 WHERE id = %s",
                (link_id,),
            )
    except Exception:
        logger.exception("affiliate click_count update failed id=%s", link_id)
    finally:
        if conn is not None:
            conn.close()


def affiliate_payload_from_join(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Build public affiliate JSON from LEFT JOIN columns (or nested dict)."""
    if not row:
        return None
    nested = row.get("affiliate")
    if isinstance(nested, dict) and nested.get("slug"):
        slug = str(nested.get("slug") or "").strip()
        if not slug:
            return None
        return {
            "slug": slug,
            "title": str(nested.get("title") or "").strip(),
            "platform_name": str(nested.get("platform_name") or "").strip(),
            "button_text": str(nested.get("button_text") or "前往查看優惠").strip()
            or "前往查看優惠",
            "go_url": "/go/" + slug,
        }
    slug = str(row.get("aff_slug") or row.get("affiliate_slug_joined") or "").strip()
    if not slug:
        return None
    return {
        "slug": slug,
        "title": str(row.get("aff_title") or "").strip(),
        "platform_name": str(row.get("aff_platform_name") or "").strip(),
        "button_text": str(row.get("aff_button_text") or "前往查看優惠").strip()
        or "前往查看優惠",
        "go_url": "/go/" + slug,
    }


AFFILIATE_JOIN_SELECT = """
  a.slug AS aff_slug,
  a.title AS aff_title,
  a.platform_name AS aff_platform_name,
  a.button_text AS aff_button_text
"""


@router.get("/go/{slug}")
def smart_geo_redirect(slug: str, request: Request, background_tasks: BackgroundTasks):
    conn = connect(ensure=True)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM affiliate_links WHERE slug = %s AND is_active = 1 LIMIT 1",
                (slug,),
            )
            link = cursor.fetchone()
    finally:
        conn.close()

    if not link:
        return RedirectResponse(url="/", status_code=302)

    country = detect_country_code(request)
    target_url = link["url_default"]
    if country == "TW" and link.get("url_tw"):
        target_url = link["url_tw"]
    elif country == "US" and link.get("url_us"):
        target_url = link["url_us"]
    elif country == "JP" and link.get("url_jp"):
        target_url = link["url_jp"]

    background_tasks.add_task(increment_click_count, link["id"])
    return RedirectResponse(url=target_url, status_code=302)


def require_affiliate_admin(
    credentials: HTTPBasicCredentials = Depends(_security),
) -> str:
    user_ok = secrets.compare_digest(
        credentials.username or "", AFFILIATE_ADMIN_USER or ""
    )
    pass_ok = secrets.compare_digest(
        credentials.password or "", AFFILIATE_ADMIN_PASSWORD or ""
    )
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


class AffiliateCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=255)
    platform_name: str = Field(min_length=1, max_length=50)
    button_text: str = Field(default="前往查看優惠", max_length=100)
    category: str = Field(default="diet", max_length=32)
    url_tw: str | None = None
    url_us: str | None = None
    url_jp: str | None = None
    url_default: str = Field(min_length=1)
    is_active: int = 1


class AffiliateUpdate(BaseModel):
    slug: str | None = Field(default=None, min_length=1, max_length=100)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    platform_name: str | None = Field(default=None, min_length=1, max_length=50)
    button_text: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=32)
    url_tw: str | None = None
    url_us: str | None = None
    url_jp: str | None = None
    url_default: str | None = None
    is_active: int | None = None


def _row_public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "slug": row.get("slug"),
        "title": row.get("title"),
        "platform_name": row.get("platform_name"),
        "button_text": row.get("button_text"),
        "category": str(row.get("category") or "diet").strip() or "diet",
        "url_tw": row.get("url_tw"),
        "url_us": row.get("url_us"),
        "url_jp": row.get("url_jp"),
        "url_default": row.get("url_default"),
        "is_active": int(row.get("is_active") or 0),
        "click_count": int(row.get("click_count") or 0),
        "created_at": str(row.get("created_at") or ""),
    }


def _normalize_category(raw: str | None) -> str | None:
    value = str(raw or "").strip().lower()
    if not value:
        return None
    if value in ("diet", "fitness"):
        return value
    return value


@router.get("/api/affiliates")
def list_active_affiliates(category: str | None = None):
    """Public carousel feed: active affiliate_links → /go/{slug} CTAs.

    Optional ``category`` filter: ``diet`` (also matches blank/NULL legacy rows)
    or ``fitness``. Omit to return all active links.
    """
    cat = _normalize_category(category)
    conn = connect(ensure=True)
    try:
        with conn.cursor() as cur:
            if cat == "fitness":
                cur.execute(
                    """
                    SELECT slug, title, platform_name, button_text, category
                    FROM affiliate_links
                    WHERE is_active = 1 AND LOWER(IFNULL(category, '')) = 'fitness'
                    ORDER BY id ASC
                    """
                )
            elif cat == "diet":
                cur.execute(
                    """
                    SELECT slug, title, platform_name, button_text, category
                    FROM affiliate_links
                    WHERE is_active = 1
                      AND (
                        category IS NULL
                        OR TRIM(category) = ''
                        OR LOWER(category) = 'diet'
                      )
                    ORDER BY id ASC
                    """
                )
            elif cat:
                cur.execute(
                    """
                    SELECT slug, title, platform_name, button_text, category
                    FROM affiliate_links
                    WHERE is_active = 1 AND LOWER(IFNULL(category, '')) = %s
                    ORDER BY id ASC
                    """,
                    (cat,),
                )
            else:
                cur.execute(
                    """
                    SELECT slug, title, platform_name, button_text, category
                    FROM affiliate_links
                    WHERE is_active = 1
                    ORDER BY id ASC
                    """
                )
            rows = cur.fetchall() or []
        items = []
        for row in rows:
            slug = str(row.get("slug") or "").strip()
            if not slug:
                continue
            items.append(
                {
                    "slug": slug,
                    "title": str(row.get("title") or "").strip(),
                    "platform_name": str(row.get("platform_name") or "").strip(),
                    "button_text": str(row.get("button_text") or "前往查看優惠").strip()
                    or "前往查看優惠",
                    "category": str(row.get("category") or "diet").strip() or "diet",
                    "go_url": "/go/" + slug,
                }
            )
        return {"affiliates": items}
    finally:
        conn.close()


@router.get("/api/admin/affiliates")
def admin_list_affiliates(_user: str = Depends(require_affiliate_admin)):
    conn = connect(ensure=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM affiliate_links ORDER BY id DESC"
            )
            rows = cur.fetchall() or []
        return {"affiliates": [_row_public(r) for r in rows]}
    finally:
        conn.close()


@router.post("/api/admin/affiliates")
def admin_create_affiliate(
    body: AffiliateCreate, _user: str = Depends(require_affiliate_admin)
):
    slug = body.slug.strip()
    conn = connect(ensure=True)
    try:
        with conn.cursor() as cur:
            try:
                cat = _normalize_category(body.category) or "diet"
                cur.execute(
                    """
                    INSERT INTO affiliate_links (
                      slug, title, platform_name, button_text, category,
                      url_tw, url_us, url_jp, url_default, is_active
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        slug,
                        body.title.strip(),
                        body.platform_name.strip(),
                        (body.button_text or "前往查看優惠").strip(),
                        cat,
                        (body.url_tw or None),
                        (body.url_us or None),
                        (body.url_jp or None),
                        body.url_default.strip(),
                        1 if int(body.is_active) else 0,
                    ),
                )
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"建立失敗：{exc}") from exc
            new_id = int(cur.lastrowid)
            cur.execute("SELECT * FROM affiliate_links WHERE id=%s", (new_id,))
            row = cur.fetchone()
        return {"ok": True, "affiliate": _row_public(row)}
    finally:
        conn.close()


@router.put("/api/admin/affiliates/{link_id}")
def admin_update_affiliate(
    link_id: int, body: AffiliateUpdate, _user: str = Depends(require_affiliate_admin)
):
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="沒有要更新的欄位")
    sets: list[str] = []
    vals: list[Any] = []
    for key in (
        "slug",
        "title",
        "platform_name",
        "button_text",
        "category",
        "url_tw",
        "url_us",
        "url_jp",
        "url_default",
        "is_active",
    ):
        if key not in data:
            continue
        value = data[key]
        if isinstance(value, str):
            value = value.strip()
        if key == "category":
            value = _normalize_category(value) or "diet"
        if key == "is_active" and value is not None:
            value = 1 if int(value) else 0
        sets.append(f"`{key}`=%s")
        vals.append(value)
    vals.append(link_id)
    conn = connect(ensure=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE affiliate_links SET " + ", ".join(sets) + " WHERE id=%s",
                vals,
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="找不到 affiliate")
            cur.execute("SELECT * FROM affiliate_links WHERE id=%s", (link_id,))
            row = cur.fetchone()
        return {"ok": True, "affiliate": _row_public(row)}
    finally:
        conn.close()


@router.patch("/api/admin/affiliates/{link_id}/toggle")
def admin_toggle_affiliate(
    link_id: int, _user: str = Depends(require_affiliate_admin)
):
    conn = connect(ensure=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE affiliate_links SET is_active = IF(is_active=1,0,1) WHERE id=%s",
                (link_id,),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="找不到 affiliate")
            cur.execute("SELECT * FROM affiliate_links WHERE id=%s", (link_id,))
            row = cur.fetchone()
        return {"ok": True, "affiliate": _row_public(row)}
    finally:
        conn.close()


# (slug, title, platform, button, category, url_tw, url_us, url_default)
_CAROUSEL_SEED_ROWS = (
    (
        "test-olive-oil",
        "冷壓初榨橄欖油",
        "iHerb / Amazon",
        "購買推薦健康好油",
        "diet",
        "https://iherb.com",
        "https://amazon.com",
        "https://iherb.com",
    ),
    (
        "healthy-quinoa",
        "有機藜麥",
        "iHerb",
        "補充優質全穀蛋白",
        "diet",
        "https://iherb.com",
        "https://iherb.com",
        "https://iherb.com",
    ),
    (
        "green-tea-matcha",
        "有機抹茶粉",
        "iHerb / Amazon",
        "日常輕爽抗氧化飲",
        "diet",
        "https://iherb.com",
        "https://amazon.com",
        "https://iherb.com",
    ),
    (
        "omega3-fish-oil",
        "高濃度魚油 Omega-3",
        "iHerb",
        "補足每日好油脂",
        "diet",
        "https://iherb.com",
        "https://iherb.com",
        "https://iherb.com",
    ),
    (
        "fitness-resistance-bands",
        "健身彈力帶組",
        "Amazon",
        "居家阻力訓練入門",
        "fitness",
        "https://amazon.com",
        "https://amazon.com",
        "https://amazon.com",
    ),
    (
        "fitness-yoga-mat",
        "防滑瑜珈墊",
        "Amazon",
        "步行伸展與健身房備",
        "fitness",
        "https://amazon.com",
        "https://amazon.com",
        "https://amazon.com",
    ),
)


def seed_demo_affiliate_rows() -> None:
    """Idempotent seed for carousel + Taiwan demo recipe/food links."""
    conn = connect(ensure=False)
    try:
        with conn.cursor() as cur:
            for (
                slug,
                title,
                platform,
                button,
                category,
                url_tw,
                url_us,
                url_default,
            ) in _CAROUSEL_SEED_ROWS:
                cur.execute(
                    """
                    INSERT INTO affiliate_links (
                      slug, title, platform_name, button_text, category,
                      url_tw, url_us, url_default
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE
                      title=VALUES(title),
                      platform_name=VALUES(platform_name),
                      button_text=VALUES(button_text),
                      category=VALUES(category),
                      url_tw=VALUES(url_tw),
                      url_us=VALUES(url_us),
                      url_default=VALUES(url_default),
                      is_active=1
                    """,
                    (
                        slug,
                        title,
                        platform,
                        button,
                        category,
                        url_tw,
                        url_us,
                        url_default,
                    ),
                )
            # Prefer the cooking oil food users actually see in Taiwan recipes.
            cur.execute(
                """
                UPDATE catalog_foods
                SET affiliate_slug = 'test-olive-oil'
                WHERE name_zh IN ('橄欖油', '橄欖', '油橄欖')
                """
            )
            # Easy demos: Taiwan dishes that list 橄欖油 in ingredients.
            cur.execute(
                """
                UPDATE catalog_recipes
                SET affiliate_slug = 'test-olive-oil'
                WHERE country = 'Taiwan'
                  AND name_zh IN ('番茄炒蛋', '蔬菜沙拉', '家常燉雞')
                """
            )
            # Keep a couple of non-TW fallbacks if TW rows missing.
            cur.execute(
                """
                UPDATE catalog_recipes
                SET affiliate_slug = 'test-olive-oil'
                WHERE affiliate_slug IS NULL
                  AND (name_zh LIKE %s OR recipe LIKE %s)
                LIMIT 2
                """,
                ("%橄欖%", "%橄欖油%"),
            )
    except Exception:
        logger.exception("seed_demo_affiliate_rows failed")
    finally:
        conn.close()
