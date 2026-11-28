"""UI language resolution for FastAPI (zh / en / ja / ko)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query, Request

from .recipes import normalize_lang

UI_LANGS = ("zh", "en", "ja", "ko")

# CF-IPCountry / coarse geo → UI lang when Accept-Language is missing/unsupported.
_COUNTRY_LANG = {
    "TW": "zh",
    "HK": "zh",
    "MO": "zh",
    "CN": "zh",
    "SG": "zh",
    "JP": "ja",
    "KR": "ko",
    "US": "en",
    "GB": "en",
    "AU": "en",
    "CA": "en",
    "NZ": "en",
    "IE": "en",
}


def parse_accept_language(header: str | None) -> str | None:
    """Best zh/en/ja/ko from an Accept-Language header (q-order)."""
    raw = (header or "").strip()
    if not raw:
        return None
    parts: list[tuple[float, str]] = []
    for chunk in raw.split(","):
        piece = chunk.strip()
        if not piece:
            continue
        tag, *params = [p.strip() for p in piece.split(";")]
        q = 1.0
        for param in params:
            if param.lower().startswith("q="):
                try:
                    q = float(param[2:])
                except ValueError:
                    q = 0.0
        primary = tag.lower().replace("_", "-").split("-", 1)[0]
        if primary in UI_LANGS:
            parts.append((q, primary))
    if not parts:
        return None
    parts.sort(key=lambda item: item[0], reverse=True)
    return parts[0][1]


def lang_from_country(code: str | None) -> str | None:
    raw = (code or "").strip().upper()
    if not raw or raw in {"XX", "T1"}:
        return None
    return _COUNTRY_LANG.get(raw)


def resolve_ui_lang(
    request: Request,
    lang: str | None = None,
    *,
    preferred_lang: str | None = None,
    default: str = "zh",
) -> str:
    """Cascade: query/body → X-App-Lang → Accept-Language → preferred_lang → CF-IPCountry → default."""
    if lang and str(lang).strip():
        return normalize_lang(lang)
    header_lang = (request.headers.get("X-App-Lang") or "").strip()
    if header_lang:
        return normalize_lang(header_lang)
    from_accept = parse_accept_language(request.headers.get("Accept-Language"))
    if from_accept:
        return from_accept
    if preferred_lang and str(preferred_lang).strip():
        return normalize_lang(preferred_lang)
    from_cf = lang_from_country(request.headers.get("CF-IPCountry"))
    if from_cf:
        return from_cf
    return normalize_lang(default)


def detect_locale_payload(request: Request) -> dict:
    """Public /api/config/locale payload — suggest only, never force-write preference."""
    query = (request.query_params.get("lang") or "").strip()
    x_app = (request.headers.get("X-App-Lang") or "").strip()
    accept = parse_accept_language(request.headers.get("Accept-Language"))
    cf_raw = (request.headers.get("CF-IPCountry") or "").strip().upper() or None
    cf_lang = lang_from_country(cf_raw)

    source = "default"
    detected = "zh"
    if query:
        detected = normalize_lang(query)
        source = "query"
    elif x_app:
        detected = normalize_lang(x_app)
        source = "x-app-lang"
    elif accept:
        detected = accept
        source = "accept-language"
    elif cf_lang:
        detected = cf_lang
        source = "cf-ipcountry"
    return {
        "detected": detected,
        "source": source,
        "suggested": detected,
        "accept_language": accept,
        "cf_ipcountry": cf_raw,
        "supported": list(UI_LANGS),
        "note": "Soft tip only — clients must not force-write preferred_lang from this endpoint.",
    }


def UiLang(
    request: Request,
    lang: Annotated[str | None, Query(description="zh|en|ja|ko")] = None,
) -> str:
    """FastAPI dependency: Query lang → X-App-Lang → Accept-Language → CF-IPCountry."""
    return resolve_ui_lang(request, lang)


UiLangDep = Annotated[str, Depends(UiLang)]
