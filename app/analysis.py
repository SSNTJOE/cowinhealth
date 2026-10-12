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
            "r": 0,
            "g": 0,
            "b": 0,
            "red_ratio": 0,
            "yellow_ratio": 0,
            "green_ratio": 0,
            "purple_ratio": 0,
            "white_ratio": 0,
            "pale_ratio": 0,
            "dark_ratio": 0,
        }

    hues, sats, vals = [], [], []
    red = yellow = green = purple = white = pale = dark = 0
    rs = gs = bs = 0
    for r, g, b in pixels:
        h, s, v = rgb_to_hsv_pixel(r, g, b)
        hues.append(h)
        sats.append(s)
        vals.append(v)
        rs += r
        gs += g
        bs += b
        is_red = (h <= 18 or h >= 345) and s >= 0.28 and v >= 0.28
        is_yellow = 28 <= h <= 70 and s >= 0.25 and v >= 0.35
        is_green = 80 <= h <= 160 and s >= 0.18 and v >= 0.18
        is_purple = 250 <= h <= 310 and s >= 0.18
        is_white = s <= 0.18 and v >= 0.72
        is_pale = s <= 0.22 and 0.55 <= v <= 0.88
        is_dark = v <= 0.28
        red += int(is_red)
        yellow += int(is_yellow)
        green += int(is_green)
        purple += int(is_purple)
        white += int(is_white)
        pale += int(is_pale)
        dark += int(is_dark)

    n = float(len(pixels))
    return {
        "h": sum(hues) / n,
        "s": sum(sats) / n,
        "v": sum(vals) / n,
        "r": rs / n,
        "g": gs / n,
        "b": bs / n,
        "red_ratio": red / n,
        "yellow_ratio": yellow / n,
        "green_ratio": green / n,
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
    if stats.get("green_ratio", 0) > 0.14:
        return "氣色偏綠（寒象傾向）"
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


# 4 rows × 3 columns. Row 4 visual order is 10 | 12 lips (center) | 11.
FACE_CELL_LAYOUT = [
    {"id": 1, "row": 0, "col": 0, "name": "左側面", "organs": "左臉"},
    {"id": 2, "row": 0, "col": 1, "name": "額頭", "organs": "咽喉／肺"},
    {"id": 3, "row": 0, "col": 2, "name": "右側面", "organs": "右臉"},
    {"id": 4, "row": 1, "col": 0, "name": "左眼", "organs": "肝"},
    {"id": 5, "row": 1, "col": 1, "name": "心區", "organs": "心"},
    {"id": 6, "row": 1, "col": 2, "name": "右眼", "organs": "肝"},
    {"id": 7, "row": 2, "col": 0, "name": "左頰", "organs": "小腸／大腸"},
    {"id": 8, "row": 2, "col": 1, "name": "鼻準區", "organs": "上段肝膽／下段脾胃", "split": True},
    {"id": 9, "row": 2, "col": 2, "name": "右頰", "organs": "小腸／大腸"},
    {"id": 10, "row": 3, "col": 0, "name": "左下頜", "organs": "生殖器／腎"},
    {"id": 12, "row": 3, "col": 1, "name": "唇", "organs": "脾"},
    {"id": 11, "row": 3, "col": 2, "name": "右下頜", "organs": "生殖器／腎"},
]
COMPLEXION_CELL_IDS = (1, 2, 3, 5, 7, 8, 9, 10, 12)
COMPLEXION_EXCLUDED_IDS = (4, 6, 11)
TEACHING_NOTE = "教學示範，非中醫診斷"


def hex_from_stats(stats: dict[str, float]) -> str:
    r = max(0, min(255, int(round(stats.get("r", 0)))))
    g = max(0, min(255, int(round(stats.get("g", 0)))))
    b = max(0, min(255, int(round(stats.get("b", 0)))))
    return f"#{r:02x}{g:02x}{b:02x}"


def compact_hsv(stats: dict[str, float]) -> dict[str, float]:
    return {
        "hue": round(stats["h"], 1),
        "saturation": round(stats["s"], 3),
        "value": round(stats["v"], 3),
        "red_ratio": round(stats.get("red_ratio", 0), 3),
        "yellow_ratio": round(stats.get("yellow_ratio", 0), 3),
        "green_ratio": round(stats.get("green_ratio", 0), 3),
        "white_ratio": round(stats.get("white_ratio", 0), 3),
        "pale_ratio": round(stats.get("pale_ratio", 0), 3),
        "dark_ratio": round(stats.get("dark_ratio", 0), 3),
    }


def average_stats(items: list[dict[str, float]]) -> dict[str, float]:
    if not items:
        return region_stats(Image.new("RGB", (1, 1), (200, 180, 170)))
    keys = (
        "h",
        "s",
        "v",
        "r",
        "g",
        "b",
        "red_ratio",
        "yellow_ratio",
        "green_ratio",
        "purple_ratio",
        "white_ratio",
        "pale_ratio",
        "dark_ratio",
    )
    n = float(len(items))
    return {key: sum(item.get(key, 0) for item in items) / n for key in keys}


def crop_cell(image: Image.Image, row: int, col: int, half: str | None = None) -> Image.Image:
    left, right = col / 3.0, (col + 1) / 3.0
    top, bottom = row / 4.0, (row + 1) / 4.0
    if half == "upper":
        bottom = (row + 0.5) / 4.0
    elif half == "lower":
        top = (row + 0.5) / 4.0
    return crop_box(image, left, top, right, bottom)


def complexion_reading(stats: dict[str, float]) -> tuple[str, str, str]:
    if stats.get("green_ratio", 0) > 0.12 or (80 <= stats["h"] <= 160 and stats["s"] >= 0.16 and stats["v"] <= 0.78):
        return "偏綠", "寒證", f"臉色偏綠，屬寒證（{TEACHING_NOTE}）"
    if stats["red_ratio"] > 0.18:
        return "偏紅", "熱證", f"臉色偏紅，屬熱證（{TEACHING_NOTE}）"
    if stats["yellow_ratio"] > 0.16:
        return "偏黃", "濕證", f"臉色偏黃，屬濕證（{TEACHING_NOTE}）"
    if stats["white_ratio"] > 0.22 or stats["pale_ratio"] > 0.28:
        return "偏白", "虛證", f"臉色偏白，屬虛證（{TEACHING_NOTE}）"
    return "中性", "未定", f"臉色接近中性（{TEACHING_NOTE}）"


def cell8_reading(stats: dict[str, float]) -> tuple[str, str]:
    if stats["dark_ratio"] > 0.16 or stats["v"] < 0.32:
        return "偏深色", "胃不好"
    if stats["yellow_ratio"] > 0.16:
        return "偏黃", "濕熱"
    if stats["white_ratio"] > 0.22 or stats["pale_ratio"] > 0.3:
        return "偏白", "血虛"
    if stats["red_ratio"] > 0.18:
        return "偏紅熱", "肺和皮實熱"
    return "中性", "未見明顯偏色"


def lips_reading(stats: dict[str, float]) -> tuple[str, str]:
    if stats["white_ratio"] > 0.2 or stats["pale_ratio"] > 0.28 or (stats["s"] < 0.22 and stats["v"] >= 0.58):
        return "偏白", "氣血虛"
    if stats["red_ratio"] > 0.2:
        return "偏紅", "實熱證"
    return "中性", "唇色接近中性"


def eyes_reading(stats: dict[str, float]) -> tuple[str, str]:
    swollen = stats["red_ratio"] > 0.12 and stats["s"] >= 0.22
    if swollen or stats["red_ratio"] > 0.14:
        return "偏紅／腫脹傾向", "肝"
    return "中性", "眼部未見明顯紅腫"


def generic_organ_reading(stats: dict[str, float], organs: str) -> tuple[str, str]:
    if stats.get("green_ratio", 0) > 0.12:
        return "偏綠", f"{organs}寒象傾向"
    if stats["red_ratio"] > 0.18:
        return "偏紅", f"{organs}熱象傾向"
    if stats["yellow_ratio"] > 0.16:
        return "偏黃", f"{organs}濕象傾向"
    if stats["white_ratio"] > 0.22 or stats["pale_ratio"] > 0.28:
        return "偏白", f"{organs}虛象傾向"
    if stats["dark_ratio"] > 0.16:
        return "偏深", f"{organs}不足傾向"
    return "中性", f"{organs}未見明顯偏色"


def analyze_face_grid(image: Image.Image) -> tuple[dict[str, Any], list[str], dict[str, str | None]]:
    findings: list[str] = []
    cells: list[dict[str, Any]] = []
    stats_by_id: dict[int, dict[str, float]] = {}

    for spec in FACE_CELL_LAYOUT:
        cell_id = spec["id"]
        row, col = spec["row"], spec["col"]
        if spec.get("split"):
            upper_img = crop_cell(image, row, col, "upper")
            lower_img = crop_cell(image, row, col, "lower")
            whole = crop_cell(image, row, col)
            upper_stats = region_stats(upper_img)
            lower_stats = region_stats(lower_img)
            whole_stats = region_stats(whole)
            stats_by_id[cell_id] = whole_stats
            halves = []
            for part, part_stats, organs in (
                ("upper", upper_stats, "肝膽"),
                ("lower", lower_stats, "脾胃"),
            ):
                bias, meaning = cell8_reading(part_stats)
                interpretation = f"第8格{('上段' if part == 'upper' else '下段')}（{organs}）{bias} → {meaning}（{TEACHING_NOTE}）"
                halves.append(
                    {
                        "part": part,
                        "organs": organs,
                        "hex": hex_from_stats(part_stats),
                        "hsv": compact_hsv(part_stats),
                        "bias": bias,
                        "meaning": meaning,
                        "interpretation": interpretation,
                    }
                )
                if bias != "中性":
                    findings.append(interpretation)
            cells.append(
                {
                    "id": cell_id,
                    "row": row,
                    "col": col,
                    "name": spec["name"],
                    "organs": spec["organs"],
                    "hex": hex_from_stats(whole_stats),
                    "hsv": compact_hsv(whole_stats),
                    "bias": halves[0]["bias"] if halves[0]["bias"] != "中性" else halves[1]["bias"],
                    "reading": f"上段{halves[0]['bias']}／下段{halves[1]['bias']}",
                    "interpretation": "；".join(item["interpretation"] for item in halves),
                    "split": halves,
                }
            )
            continue

        crop = crop_cell(image, row, col)
        stats = region_stats(crop)
        stats_by_id[cell_id] = stats
        if cell_id in (4, 6):
            bias, meaning = eyes_reading(stats)
            interpretation = f"第{cell_id}格{spec['name']}（{spec['organs']}）{bias} → {meaning}（{TEACHING_NOTE}）"
        elif cell_id == 12:
            bias, meaning = lips_reading(stats)
            interpretation = f"第12格唇（脾）{bias} → {meaning}（{TEACHING_NOTE}）"
        else:
            bias, meaning = generic_organ_reading(stats, spec["organs"])
            interpretation = f"第{cell_id}格{spec['name']}（{spec['organs']}）{bias} → {meaning}（{TEACHING_NOTE}）"
        if bias != "中性":
            findings.append(interpretation)
        cells.append(
            {
                "id": cell_id,
                "row": row,
                "col": col,
                "name": spec["name"],
                "organs": spec["organs"],
                "hex": hex_from_stats(stats),
                "hsv": compact_hsv(stats),
                "bias": bias,
                "reading": bias,
                "interpretation": interpretation,
                "split": None,
            }
        )

    complexion_stats = average_stats([stats_by_id[i] for i in COMPLEXION_CELL_IDS if i in stats_by_id])
    c_bias, c_pattern, c_text = complexion_reading(complexion_stats)
    findings.insert(0, c_text)
    lip_stats = stats_by_id.get(12)
    if lip_stats:
        lip_bias, lip_meaning = lips_reading(lip_stats)
        lip_color = f"唇{lip_bias} → {lip_meaning}"
    else:
        lip_color = None
    colors = {
        "face_color": c_text,
        "lip_color": lip_color,
        "tongue_body_color": None,
        "tongue_coat_color": None,
    }
    face_grid = {
        "rows": 4,
        "cols": 3,
        "cells": cells,
        "complexion": {
            "hex": hex_from_stats(complexion_stats),
            "hsv": compact_hsv(complexion_stats),
            "bias": c_bias,
            "pattern": c_pattern,
            "interpretation": c_text,
            "included_cells": list(COMPLEXION_CELL_IDS),
            "excluded_cells": list(COMPLEXION_EXCLUDED_IDS),
        },
        "disclaimer": TEACHING_NOTE,
    }
    return face_grid, findings, colors


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

    face_grid = None
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
        face_grid, grid_findings, colors = analyze_face_grid(image)
        findings.extend(grid_findings)

    if not findings:
        findings.append("未見明顯偏色，先給中間分數 5")

    complexion = (face_grid or {}).get("complexion")
    return {
        "shot_type": shot_type,
        "dominant_color": (complexion or {}).get("hex") or dominant,
        "hsv": (complexion or {}).get("hsv") or {
            "hue": round(overall["h"], 1),
            "saturation": round(overall["s"], 3),
            "value": round(overall["v"], 3),
        },
        "color_label": (complexion or {}).get("interpretation") or hsv_label(overall),
        "findings": findings,
        "region_colors": colors,
        "face_grid": face_grid,
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
    face_grid = None
    for report in color_reports:
        findings.extend(report["findings"])
        for key, value in report["region_colors"].items():
            if value:
                region_colors[key] = value
        dominant = report["dominant_color"]
        hsv = report["hsv"]
        color_label = report["color_label"]
        if report.get("face_grid"):
            face_grid = report["face_grid"]

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
        "face_grid": face_grid,
        "complexion": (face_grid or {}).get("complexion"),
        "disclaimer": "此為教學示範用色彩／臟腑對應邏輯，不能取代醫師診斷。CNN 醫學模型可於蒐集標註照片後再訓練。",
    }
