from __future__ import annotations

from collections import Counter
from io import BytesIO
from typing import Any

from PIL import Image

from .syndrome import apply_color_findings, apply_pulse, apply_text, empty_evidence, finalize


def clamp(value: float, low: int = 1, high: int = 10) -> int:
    return max(low, min(high, int(round(value))))


def crop_box(image: Image.Image, left: float, top: float, right: float, bottom: float) -> Image.Image:
    width, height = image.size
    box = (
        int(width * left),
        int(height * top),
        int(width * right),
        int(height * bottom),
    )
    return image.crop(box)


def sample_pixels(image: Image.Image, max_side: int = 160) -> list[tuple[int, int, int]]:
    work = image.convert("RGB")
    work.thumbnail((max_side, max_side))
    return list(work.getdata())


def rgb_to_hsv_pixel(r: int, g: int, b: int) -> tuple[float, float, float]:
    rf, gf, bf = r / 255.0, g / 255.0, b / 255.0
    mx = max(rf, gf, bf)
    mn = min(rf, gf, bf)
    diff = mx - mn
    if diff == 0:
        hue = 0.0
    elif mx == rf:
        hue = (60 * ((gf - bf) / diff) + 360) % 360
    elif mx == gf:
        hue = (60 * ((bf - rf) / diff) + 120) % 360
    else:
        hue = (60 * ((rf - gf) / diff) + 240) % 360
    sat = 0.0 if mx == 0 else diff / mx
    return hue, sat, mx


def region_stats(image: Image.Image) -> dict[str, float]:
    pixels = sample_pixels(image)
    if not pixels:
        return {
            "h": 0,
            "s": 0,
            "v": 0,
            "red_ratio": 0,
            "yellow_ratio": 0,
            "purple_ratio": 0,
            "white_ratio": 0,
            "pale_ratio": 0,
            "dark_ratio": 0,
        }

    hues, sats, vals = [], [], []
    red = yellow = purple = white = pale = dark = 0
    for r, g, b in pixels:
        h, s, v = rgb_to_hsv_pixel(r, g, b)
        hues.append(h)
        sats.append(s)
        vals.append(v)
        is_red = (h <= 18 or h >= 345) and s >= 0.28 and v >= 0.28
        is_yellow = 28 <= h <= 70 and s >= 0.25 and v >= 0.35
        is_purple = 250 <= h <= 310 and s >= 0.18
        is_white = s <= 0.18 and v >= 0.72
        is_pale = s <= 0.22 and 0.55 <= v <= 0.88
        is_dark = v <= 0.28
        red += int(is_red)
        yellow += int(is_yellow)
        purple += int(is_purple)
        white += int(is_white)
        pale += int(is_pale)
        dark += int(is_dark)

    n = float(len(pixels))
    return {
        "h": sum(hues) / n,
        "s": sum(sats) / n,
        "v": sum(vals) / n,
        "red_ratio": red / n,
        "yellow_ratio": yellow / n,
        "purple_ratio": purple / n,
        "white_ratio": white / n,
        "pale_ratio": pale / n,
        "dark_ratio": dark / n,
    }


def dominant_color_hex(image: Image.Image) -> str:
    pixels = sample_pixels(image, max_side=80)
    quantized = [((r // 16) * 16, (g // 16) * 16, (b // 16) * 16) for r, g, b in pixels]
    (r, g, b), _ = Counter(quantized).most_common(1)[0]
    return f"#{r:02x}{g:02x}{b:02x}"


def hsv_label(stats: dict[str, float]) -> str:
    if stats["white_ratio"] > 0.28:
        return "苔白偏厚／氣色偏白"
    if stats["yellow_ratio"] > 0.22:
        return "面色或舌苔偏黃（萎黃傾向）"
    if stats["purple_ratio"] > 0.12:
        return "青紫傾向（瘀象）"
    if stats["red_ratio"] > 0.22:
        return "偏紅（熱象／舌質紅）"
    if stats["pale_ratio"] > 0.3:
        return "偏淡白（血虛傾向）"
    if stats["dark_ratio"] > 0.18:
        return "偏暗（寒或腎虛傾向）"
    return "顏色接近中性"


def inspect_image(image_bytes: bytes, shot_type: str) -> dict[str, Any]:
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    dominant = dominant_color_hex(image)
    overall = region_stats(image)
    findings: list[str] = []
    colors = {
        "face_color": None,
        "lip_color": None,
        "tongue_body_color": None,
        "tongue_coat_color": None,
    }

    if shot_type == "tongue":
        tip = region_stats(crop_box(image, 0.35, 0.72, 0.65, 0.95))
        sides = region_stats(crop_box(image, 0.05, 0.25, 0.22, 0.75))
        sides_r = region_stats(crop_box(image, 0.78, 0.25, 0.95, 0.75))
        center = region_stats(crop_box(image, 0.3, 0.3, 0.7, 0.7))
        root = region_stats(crop_box(image, 0.3, 0.05, 0.7, 0.28))
        colors["tongue_body_color"] = hsv_label(tip if tip["red_ratio"] > center["red_ratio"] else center)
        colors["tongue_coat_color"] = hsv_label(center)
        if tip["red_ratio"] > 0.18:
            findings.append("舌尖紅，屬心火偏旺")
        if max(sides["purple_ratio"], sides_r["purple_ratio"]) > 0.1:
            findings.append("舌邊青紫，屬肝瘀傾向")
        if center["white_ratio"] > 0.25:
            findings.append("中部苔白偏厚，屬脾濕／肺衛氣虛傾向")
        if center["yellow_ratio"] > 0.18:
            findings.append("舌苔偏黃，屬脾胃濕熱或膽熱")
        if root["dark_ratio"] > 0.16 or root["purple_ratio"] > 0.1:
            findings.append("舌根偏暗，屬腎與膀胱氣化不足")
        if overall["pale_ratio"] > 0.28:
            findings.append("舌質偏淡，屬氣血不足")
    else:
        complexion = region_stats(crop_box(image, 0.25, 0.28, 0.75, 0.62))
        eyes = region_stats(crop_box(image, 0.15, 0.18, 0.85, 0.42))
        lips = region_stats(crop_box(image, 0.32, 0.62, 0.68, 0.86))
        colors["face_color"] = hsv_label(complexion)
        colors["lip_color"] = hsv_label(lips)
        if complexion["yellow_ratio"] > 0.18:
            findings.append("面色萎黃，屬脾虛／膽胃不和")
        if complexion["pale_ratio"] > 0.28 or lips["pale_ratio"] > 0.3:
            findings.append("嘴唇或面色蒼白，屬脾血虛")
        if lips["red_ratio"] > 0.22:
            findings.append("唇色偏紅，屬心火或血熱")
        if lips["purple_ratio"] > 0.1 or complexion["purple_ratio"] > 0.1:
            findings.append("唇面青紫，屬肝瘀")
        if eyes["red_ratio"] > 0.16:
            findings.append("眼部偏紅，屬肝火／心火上炎")
        if complexion["dark_ratio"] > 0.14:
            findings.append("面色偏暗，屬腎氣不足")
        if complexion["white_ratio"] > 0.3:
            findings.append("氣色偏白，屬肺氣虛")

    if not findings:
        findings.append("未見明顯偏色，先給中間分數 5")

    return {
        "shot_type": shot_type,
        "dominant_color": dominant,
        "hsv": {
            "hue": round(overall["h"], 1),
            "saturation": round(overall["s"], 3),
            "value": round(overall["v"], 3),
        },
        "color_label": hsv_label(overall),
        "findings": findings,
        "region_colors": colors,
    }


def analyze_session(
    images: list[tuple[str, bytes]],
    symptoms: str = "",
    discomfort: str = "",
    pulse: dict[str, Any] | None = None,
) -> dict[str, Any]:
    color_reports = [inspect_image(raw, shot_type) for shot_type, raw in images]
    findings: list[str] = []
    region_colors: dict[str, str | None] = {
        "face_color": None,
        "lip_color": None,
        "tongue_body_color": None,
        "tongue_coat_color": None,
    }
    dominant = None
    hsv = None
    color_label = "尚未拍照"
    for report in color_reports:
        findings.extend(report["findings"])
        for key, value in report["region_colors"].items():
            if value:
                region_colors[key] = value
        dominant = report["dominant_color"]
        hsv = report["hsv"]
        color_label = report["color_label"]

    evidence = empty_evidence()
    text_notes = apply_text(evidence, f"{symptoms} {discomfort}")
    apply_color_findings(evidence, findings)
    pulse_notes = apply_pulse(evidence, pulse)
    scores, patterns, overlays = finalize(evidence)
    all_findings = findings + text_notes + pulse_notes
    if not all_findings:
        all_findings = ["資料不足，各臟腑先記 5 分（未定），不放置證型圖"]

    return {
        "dominant_color": dominant,
        "hsv": hsv,
        "color_label": color_label,
        "region_colors": region_colors,
        "findings": all_findings,
        "scores": scores,
        "patterns": patterns,
        "overlays": overlays,
        "disclaimer": "此為示範用色彩／臟腑對應邏輯，不能取代醫師診斷。CNN 醫學模型可於蒐集標註照片後再訓練。",
    }
