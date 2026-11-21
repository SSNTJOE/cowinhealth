from __future__ import annotations

import re
import urllib.parse
import urllib.request
from collections import Counter
from html import unescape
from typing import Any

from .health_flags import ACUPOINT_BIAS, DIET_BIAS, allergy_exclude_tokens
from .syndrome import ORGAN_META

USER_AGENT = "Health-ing/1.0 (educational demo)"

# Organ → gentle teaching diet keywords (not prescriptions).
ORGAN_DIET_KEYWORDS = {
    "心": "養心",
    "肝": "疏肝",
    "脾": "健脾",
    "胃": "養胃",
    "肺": "潤肺",
    "腎": "補腎",
    "膽": "利膽清淡",
    "大腸": "潤腸通便",
    "小腸": "健運脾胃",
    "膀胱": "清利小便",
    "子宮": "溫養調理",
}

# Organ → common teaching acupoint / massage directions (not prescriptions).
ORGAN_ACUPOINT_KEYWORDS = {
    "心": "心俞 內關 穴位按摩",
    "肝": "肝俞 太衝 穴位按摩",
    "脾": "脾俞 足三里 穴位按摩",
    "胃": "中脘 足三里 穴位按摩",
    "肺": "肺俞 列缺 穴位按摩",
    "腎": "腎俞 太溪 穴位按摩",
    "膽": "膽俞 陽陵泉 穴位按摩",
    "大腸": "天樞 合谷 穴位按摩",
    "小腸": "小海 後溪 穴位按摩",
    "膀胱": "膀胱俞 委中 穴位按摩",
    "子宮": "關元 三陰交 輕柔按摩",
}

# Compact 證型 → diet direction.
PATTERN_KIND_DIET = {
    "實熱": "清熱降火",
    "虛熱": "滋陰清熱",
    "實寒": "溫中祛寒",
    "虛寒": "溫補祛寒",
    "濕": "祛濕利水",
    "濕熱": "清熱祛濕",
    "寒濕": "溫化祛濕",
}

PATTERN_KIND_ACUPOINT = {
    "實熱": "清熱穴位輕柔按摩",
    "虛熱": "滋陰穴位輕柔按摩",
    "實寒": "溫通穴位按摩",
    "虛寒": "溫補穴位艾灸按摩教學",
    "濕": "祛濕穴位按摩",
    "濕熱": "清熱祛濕穴位輕柔按摩",
    "寒濕": "溫化祛濕穴位按摩",
}

# Face / tongue / coat → short cooking / massage *direction* only (never put raw
# color labels like 黃苔／舌紅 into the Google query as status explanations).
COLOR_DIET_KEYWORDS = (
    ("黃苔", "清熱化濕"),
    ("白厚苔", "溫化祛濕"),
    ("白苔", "健脾溫化"),
    ("少苔", "養陰生津"),
    ("無苔", "養陰生津"),
    ("舌尖紅", "清心火"),
    ("舌紅", "清熱"),
    ("舌淡", "益氣溫補"),
    ("淡白", "益氣溫補"),
    ("青紫", "行氣活血"),
    ("面紅", "清熱"),
    ("面白", "益氣"),
    ("唇紅", "清熱"),
    ("唇淡", "補血益氣"),
)

COLOR_ACUPOINT_KEYWORDS = (
    ("黃苔", "清熱化濕"),
    ("白厚苔", "溫化祛濕"),
    ("白苔", "健脾溫陽"),
    ("少苔", "養陰輕柔"),
    ("無苔", "養陰輕柔"),
    ("舌尖紅", "清心火"),
    ("舌紅", "清熱輕柔"),
    ("舌淡", "補氣"),
    ("淡白", "補氣"),
    ("青紫", "行氣活血輕柔"),
    ("面紅", "清熱輕柔"),
    ("面白", "補氣"),
    ("唇紅", "清熱"),
    ("唇淡", "補血"),
)

HEALTHY_PATTERN = frozenset({"", "健康", "待觀察", "未定", "正常", "接近正常", "接近基本色", None})


def clip50(text: str) -> str:
    text = re.sub(r"\s+", "", text)
    return text[:50]


def search_urls(diet_query: str, acupoint_query: str) -> tuple[str, str]:
    diet = "https://www.google.com/search?q=" + urllib.parse.quote(diet_query)
    acupoint = "https://www.google.com/search?q=" + urllib.parse.quote(acupoint_query)
    return diet, acupoint


def google_recipe_article_url(query: str) -> str:
    """Google web search biased toward recipe articles / write-ups."""
    return "https://www.google.com/search?q=" + urllib.parse.quote(query)


def google_recipe_video_url(query: str) -> str:
    """Google Videos tab for recipe / cooking clips."""
    return "https://www.google.com/search?tbm=vid&q=" + urllib.parse.quote(query)


def google_acupoint_image_url(query: str) -> str:
    """Google Images tab for acupoint location / massage diagrams."""
    return "https://www.google.com/search?tbm=isch&q=" + urllib.parse.quote(query)


def google_acupoint_video_url(query: str) -> str:
    """Google Videos tab for acupoint massage clips."""
    return "https://www.google.com/search?tbm=vid&q=" + urllib.parse.quote(query)


def fetch_snippet(query: str, timeout: int = 8) -> str:
    encoded = urllib.parse.quote(query)
    url = "https://html.duckduckgo.com/html/?q=" + encoded
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""
    snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, flags=re.S)
    if not snippets:
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</(td|div)', html, flags=re.S)
    if not snippets:
        return ""
    raw = unescape(re.sub(r"<[^>]+>", "", snippets[0]))
    return clip50(raw)


def allergy_excludes(allergies: list[str]) -> list[str]:
    """Google exclude tokens from the user's allergy labels (keep query short)."""
    tokens: list[str] = []
    seen: set[str] = set()
    # Prefer the checkbox labels the user actually selected.
    for word in allergies or []:
        label = str(word or "").strip()
        if not label or label in seen:
            continue
        seen.add(label)
        tokens.append(f"-{label}")
        tokens.append(f"不含{label}")
        if len(seen) >= 5:
            break
    # Add a few expanded synonyms only when still short.
    if len(seen) < 5:
        for word in allergy_exclude_tokens(allergies):
            if word in seen:
                continue
            seen.add(word)
            tokens.append(f"-{word}")
            if len(seen) >= 8:
                break
    return tokens


def _split_organ_pattern(label: str) -> tuple[str, str] | None:
    text = (label or "").strip()
    if not text or text in HEALTHY_PATTERN:
        return None
    for kind in ("實熱", "虛熱", "實寒", "虛寒", "濕熱", "寒濕"):
        if text.endswith(kind) and len(text) > len(kind):
            return text[: -len(kind)], kind
        if text == kind:
            return "", kind
    if "濕" in text:
        return "", "濕"
    for _key, name, _sk, _pk in ORGAN_META:
        if text.startswith(name) and len(text) > len(name):
            return name, text[len(name) :]
    return "", text


def keywords_from_pattern_label(
    label: str,
    *,
    organ_map: dict[str, str] = ORGAN_DIET_KEYWORDS,
    kind_map: dict[str, str] = PATTERN_KIND_DIET,
) -> list[str]:
    split = _split_organ_pattern(label)
    if not split:
        return []
    organ, kind = split
    out: list[str] = []
    if organ and organ in organ_map:
        out.append(organ_map[organ])
    kind_key = kind if kind in kind_map else None
    if not kind_key:
        for key in kind_map:
            if key in kind:
                kind_key = key
                break
    if kind_key:
        out.append(kind_map[kind_key])
    return out


def keywords_from_color_text(*blobs: str, color_map: tuple[tuple[str, str], ...] = COLOR_DIET_KEYWORDS) -> list[str]:
    text = " ".join(str(part or "") for part in blobs)
    hits: list[str] = []
    seen: set[str] = set()
    for needle, term in color_map:
        if needle in text and term not in seen:
            seen.add(term)
            hits.append(term)
    return hits


def _color_aux_from_result(
    result: dict[str, Any] | None,
    color_map: tuple[tuple[str, str], ...],
) -> list[str]:
    """Auxiliary direction terms from face/tongue/coat — never raw color status text."""
    if not result:
        return []
    colors = result.get("region_colors") or {}
    return keywords_from_color_text(
        result.get("color_label") or "",
        " ".join(str(v) for v in colors.values() if v),
        color_map=color_map,
    )[:2]


def _color_aux_from_week(
    records: list[dict[str, Any]] | None,
    color_map: tuple[tuple[str, str], ...],
) -> list[str]:
    if not records:
        return []
    counter: Counter[str] = Counter()
    for row in records:
        for term in keywords_from_color_text(
            row.get("face_color") or "",
            row.get("lip_color") or "",
            row.get("tongue_body_color") or "",
            row.get("tongue_coat_color") or "",
            row.get("complexion_label") or "",
            color_map=color_map,
        ):
            counter[term] += 1
    return [term for term, _n in counter.most_common(2)]


def keywords_from_session_result(result: dict[str, Any] | None) -> list[str]:
    return _color_aux_from_result(result, COLOR_DIET_KEYWORDS)


def acupoint_keywords_from_session_result(result: dict[str, Any] | None) -> list[str]:
    return _color_aux_from_result(result, COLOR_ACUPOINT_KEYWORDS)


def keywords_from_week_records(records: list[dict[str, Any]] | None) -> list[str]:
    return _color_aux_from_week(records, COLOR_DIET_KEYWORDS)


def acupoint_keywords_from_week_records(records: list[dict[str, Any]] | None) -> list[str]:
    return _color_aux_from_week(records, COLOR_ACUPOINT_KEYWORDS)


def _add_symptom_chunks(text: str, out: list[str], seen: set[str], *, limit: int) -> None:
    raw = (text or "").strip()
    if not raw:
        return
    # Keep short free-text phrases the user typed (pain / feeling), split lightly.
    chunks = re.split(r"[,，、;；/\n\r\t|]+", raw)
    if len(chunks) == 1 and " " in raw and len(raw) > 12:
        chunks = re.split(r"\s+", raw)
    for chunk in chunks:
        chunk = chunk.strip(" 。．.！!？?：:（）()【】[]")
        if len(chunk) < 2:
            continue
        # Skip chunks that are only color-status explanations.
        if any(token in chunk for token in ("臉色", "面色", "舌色", "舌苔", "苔色", "唇色")):
            continue
        if chunk in seen:
            continue
        seen.add(chunk)
        out.append(chunk)
        if len(out) >= limit:
            return


def symptom_discomfort_keywords(
    symptoms: str,
    discomfort: str,
    week_records: list[dict[str, Any]] | None = None,
    *,
    limit: int = 6,
) -> list[str]:
    """Primary search axis: today + this week's 今日感覺 / 不舒服的地方."""
    out: list[str] = []
    seen: set[str] = set()
    _add_symptom_chunks(symptoms, out, seen, limit=limit)
    _add_symptom_chunks(discomfort, out, seen, limit=limit)
    for row in week_records or []:
        if len(out) >= limit:
            break
        _add_symptom_chunks(row.get("symptoms") or "", out, seen, limit=limit)
        if len(out) >= limit:
            break
        _add_symptom_chunks(row.get("discomfort") or "", out, seen, limit=limit)
    return out


def acupoint_allergy_notes(allergies: list[str]) -> list[str]:
    """Massage-oil / contact caution tokens for Google (not food recipe excludes)."""
    notes: list[str] = []
    labels = {str(a or "").strip() for a in (allergies or []) if str(a or "").strip()}
    if "花生" in labels:
        notes.extend(["-花生油", "避開花生油精油"])
    if "堅果" in labels:
        notes.append("避開堅果油精油")
    if "雞蛋" in labels:
        notes.append("避開蛋清面膜類偏方")
    return notes[:4]


def _merge_unique(*groups: list[str], limit: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for term in group or []:
            if not term or term in seen:
                continue
            seen.add(term)
            out.append(term)
            if len(out) >= limit:
                return out
    return out


def diet_search_query(
    base: str,
    conditions: list[str],
    allergies: list[str],
    *,
    primary_keywords: list[str] | None = None,
    aux_keywords: list[str] | None = None,
    session_keywords: list[str] | None = None,
    week_keywords: list[str] | None = None,
) -> str:
    """Google query: symptoms/discomfort first, color directions aux, − allergens."""
    extras = [DIET_BIAS[key] for key in conditions if key in DIET_BIAS]
    primary = list(primary_keywords or [])
    # Legacy callers may still pass session/week as color aux.
    aux = _merge_unique(aux_keywords or [], session_keywords or [], week_keywords or [], limit=2)
    if not primary and base:
        primary = [tok for tok in str(base).split() if tok][:4]
    parts = [
        *primary[:6],
        "食譜",
        "作法",
        "做法",
        *aux,
        *extras,
        *allergy_excludes(allergies),
        "(文章 OR 作法教學 OR 影片 OR YouTube OR 食譜影片)",
        "教學參考食療",
        "非診斷",
    ]
    query = " ".join(part for part in parts if part).strip()
    if len(query) > 180:
        query = query[:180].rsplit(" ", 1)[0]
    return query


def acupoint_search_query(
    base: str,
    conditions: list[str],
    allergies: list[str] | None = None,
    *,
    primary_keywords: list[str] | None = None,
    aux_keywords: list[str] | None = None,
    session_keywords: list[str] | None = None,
    week_keywords: list[str] | None = None,
) -> str:
    """Google query: symptoms/discomfort first, color directions aux, image/video intent."""
    extras = [ACUPOINT_BIAS[key] for key in conditions if key in ACUPOINT_BIAS]
    if "服用抗凝血劑" in conditions:
        extras.append("避免放血破血")
        extras.append("輕柔按揉勿刮痧放血")
    primary = list(primary_keywords or [])
    aux = _merge_unique(aux_keywords or [], session_keywords or [], week_keywords or [], limit=2)
    if not primary and base:
        primary = [tok for tok in str(base).split() if tok][:4]
    parts = [
        *primary[:6],
        "穴道按摩",
        "穴位圖",
        "按摩手法",
        *aux,
        *extras,
        *acupoint_allergy_notes(allergies or []),
        "(圖片 OR 示意圖 OR 影片 OR YouTube OR 按摩教學)",
        "教學參考",
        "非診斷",
    ]
    query = " ".join(part for part in parts if part).strip()
    if len(query) > 180:
        query = query[:180].rsplit(" ", 1)[0]
    return query


def local_fallback(
    findings: list[str],
    symptoms: str,
    conditions: list[str] | None = None,
    allergies: list[str] | None = None,
) -> str:
    conditions = conditions or []
    allergies = allergies or []
    blob = " ".join(findings) + (symptoms or "")
    if "痛風" in conditions:
        core = "低普林清淡，少內臟海鮮與甜飲。"
    elif "糖尿病" in conditions:
        core = "低GI定時定量，少甜飲精緻澱粉。"
    elif "高血壓" in conditions or "中風" in conditions:
        core = "少鈉少油清淡，作息規律輔助復健。"
    elif "腎臟病" in conditions:
        core = "控鉀磷與適量蛋白，清淡少加工。"
    elif "肝病" in conditions:
        core = "少油膩戒酒精，清淡蔬食為主。"
    elif "服用抗凝血劑" in conditions:
        core = "蔬菜份量求穩定，菠菜勿突然過量。"
    elif any(token in blob for token in ("脾實寒", "脾虛寒")) and any(token in blob for token in ("胃實寒", "胃虛寒")):
        core = "脾寒與胃寒分開看：脾宜溫脾，胃宜溫胃，可食薑棗茶、小米粥，避免生冷冰品。"
    elif any(token in blob for token in ("脾實寒", "脾虛寒")):
        core = "脾寒宜溫脾，可食薑棗茶、小米粥，避免生冷冰品。"
    elif any(token in blob for token in ("胃實寒", "胃虛寒")):
        core = "胃寒宜溫胃，可食薑棗茶、小米粥，避免生冷冰品。"
    elif any(word in blob for word in ("寒", "怕冷", "遲脈", "淡白")):
        core = "宜溫補脾胃，可食薑棗茶、小米粥，避免生冷冰品。"
    elif any(word in blob for word in ("熱", "口乾", "數脈", "舌尖紅", "黃苔")):
        core = "宜清熱，可食綠豆湯、苦瓜，少煎炸辛辣與熬夜。"
    elif any(word in blob for word in ("瘀", "青紫", "經痛")):
        if "服用抗凝血劑" in conditions:
            core = "宜輕柔活動，勿自行活血放血。"
        else:
            core = "宜行氣活血，可食山楂、玫瑰花茶，搭配適度走動。"
    elif any(word in blob for word in ("虛", "疲倦", "蒼白", "苔白")):
        core = "宜健脾益氣，可食山藥、紅棗小米粥，早睡養神。"
    else:
        core = "作息規律、飲食清淡、適度活動。"
    if allergies:
        core += "避" + "、".join(allergies[:3]) + "。"
    core += "教學參考非診斷。"
    return core


def build_advice(
    findings: list[str],
    symptoms: str,
    discomfort: str,
    conditions: list[str] | None = None,
    allergies: list[str] | None = None,
    *,
    result: dict[str, Any] | None = None,
    week_records: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    conditions = conditions or []
    allergies = allergies or []
    primary = symptom_discomfort_keywords(symptoms, discomfort, week_records)
    diet_aux = _merge_unique(
        keywords_from_session_result(result),
        keywords_from_week_records(week_records),
        limit=2,
    )
    acu_aux = _merge_unique(
        acupoint_keywords_from_session_result(result),
        acupoint_keywords_from_week_records(week_records),
        limit=2,
    )
    diet_query = diet_search_query(
        " ".join(primary) or "中醫食譜調理",
        conditions,
        allergies,
        primary_keywords=primary,
        aux_keywords=diet_aux,
    )
    acupoint_query = acupoint_search_query(
        " ".join(primary) or "中醫調理",
        conditions,
        allergies,
        primary_keywords=primary,
        aux_keywords=acu_aux,
    )
    snippet = fetch_snippet(diet_query)
    if not snippet:
        snippet = clip50(
            local_fallback(findings, (symptoms or "") + (discomfort or ""), conditions, allergies)
        )
    diet_url = google_recipe_article_url(diet_query)
    diet_video_url = google_recipe_video_url(diet_query)
    acupoint_url = google_acupoint_image_url(acupoint_query)
    acupoint_video_url = google_acupoint_video_url(acupoint_query)
    return {
        "diet_advice": snippet,
        "diet_url": diet_url,
        "diet_video_url": diet_video_url,
        "diet_query": diet_query,
        "acupoint_url": acupoint_url,
        "acupoint_video_url": acupoint_video_url,
        "acupoint_query": acupoint_query,
    }
