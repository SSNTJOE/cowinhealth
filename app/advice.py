from __future__ import annotations

import re
import urllib.parse
import urllib.request
from html import unescape

from .health_flags import ACUPOINT_BIAS, ALLERGY_EXCLUDE, DIET_BIAS

USER_AGENT = "Health-ing/1.0 (educational demo)"


def clip50(text: str) -> str:
    text = re.sub(r"\s+", "", text)
    return text[:50]


def search_urls(diet_query: str, acupoint_query: str) -> tuple[str, str]:
    diet = "https://www.google.com/search?q=" + urllib.parse.quote(diet_query)
    acupoint = "https://www.google.com/search?q=" + urllib.parse.quote(acupoint_query)
    return diet, acupoint


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
    tokens: list[str] = []
    seen: set[str] = set()
    for allergy in allergies:
        for word in ALLERGY_EXCLUDE.get(allergy, (allergy,)):
            if word not in seen:
                seen.add(word)
                tokens.append(f"-{word}")
                tokens.append(f"不含{word}")
    return tokens


def diet_search_query(base: str, conditions: list[str], allergies: list[str]) -> str:
    extras = [DIET_BIAS[key] for key in conditions if key in DIET_BIAS]
    parts = [base, *extras, *allergy_excludes(allergies), "教學參考食療", "非診斷"]
    return " ".join(part for part in parts if part).strip()


def acupoint_search_query(base: str, conditions: list[str]) -> str:
    extras = [ACUPOINT_BIAS[key] for key in conditions if key in ACUPOINT_BIAS]
    if "服用抗凝血劑" in conditions:
        extras.append("避免放血破血")
    parts = [base, *extras, "穴道按摩教學參考", "非診斷"]
    return " ".join(part for part in parts if part).strip()


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
) -> dict[str, str]:
    conditions = conditions or []
    allergies = allergies or []
    base = " ".join(
        part for part in ["中醫", symptoms, discomfort, " ".join(findings[:2])] if part
    ).strip() or "中醫調理"
    diet_query = diet_search_query(base, conditions, allergies)
    acupoint_query = acupoint_search_query(base, conditions)
    snippet = fetch_snippet(diet_query)
    if not snippet:
        snippet = clip50(local_fallback(findings, (symptoms or "") + (discomfort or ""), conditions, allergies))
    diet_url, acupoint_url = search_urls(diet_query, acupoint_query)
    return {
        "diet_advice": snippet,
        "diet_url": diet_url,
        "acupoint_url": acupoint_url,
    }
