from __future__ import annotations

import re
import urllib.parse
import urllib.request
from html import unescape

USER_AGENT = "Health-ing/1.0 (educational demo)"


def clip50(text: str) -> str:
    text = re.sub(r"\s+", "", text)
    return text[:50]


def search_urls(query: str) -> tuple[str, str]:
    encoded = urllib.parse.quote(query)
    diet = f"https://www.google.com/search?q={encoded}+食療"
    acupoint = f"https://www.google.com/search?q={encoded}+穴道按摩"
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


def local_fallback(findings: list[str], symptoms: str) -> str:
    blob = " ".join(findings) + (symptoms or "")
    if any(word in blob for word in ("寒", "怕冷", "遲脈", "淡白")):
        return "宜溫補脾胃，可食薑棗茶、小米粥，避免生冷冰品。"
    if any(word in blob for word in ("熱", "口乾", "數脈", "舌尖紅", "黃苔")):
        return "宜清熱，可食綠豆湯、苦瓜，少煎炸辛辣與熬夜。"
    if any(word in blob for word in ("瘀", "青紫", "經痛")):
        return "宜行氣活血，可食山楂、玫瑰花茶，搭配適度走動。"
    if any(word in blob for word in ("虛", "疲倦", "蒼白", "苔白")):
        return "宜健脾益氣，可食山藥、紅棗小米粥，早睡養神。"
    return "作息規律、飲食清淡、適度活動；詳細調理請詢問合格醫師。"


def build_advice(findings: list[str], symptoms: str, discomfort: str) -> dict[str, str]:
    query = " ".join(
        part for part in ["中醫", symptoms, discomfort, " ".join(findings[:2])] if part
    ).strip() or "中醫食療 穴道按摩"
    snippet = fetch_snippet(query + " 食療")
    if not snippet:
        snippet = clip50(local_fallback(findings, (symptoms or "") + (discomfort or "")))
    diet_url, acupoint_url = search_urls(query)
    return {
        "diet_advice": snippet,
        "diet_url": diet_url,
        "acupoint_url": acupoint_url,
    }
