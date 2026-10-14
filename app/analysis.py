from __future__ import annotations

import base64
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


def is_skin_hsv(h: float, s: float, v: float) -> bool:
    """Demo skin: warm hues, skip dark hair and pale walls."""
    hue_ok = h <= 50 or h >= 350
    return hue_ok and 0.12 <= s <= 0.78 and 0.20 <= v <= 0.98


def is_tongue_hsv(h: float, s: float, v: float) -> bool:
    """Demo tongue body (pink/red) plus pale/yellow coat; drop lips-adjacent dark and room."""
    pink = (h <= 28 or h >= 330) and s >= 0.16 and v >= 0.22
    coat = (h <= 70 or h >= 320) and 0.04 <= s <= 0.55 and v >= 0.42
    return v >= 0.18 and (pink or coat)


def _largest_blob_box(mask: bytearray, width: int, height: int) -> tuple[int, int, int, int, int] | None:
    visited = bytearray(width * height)
    best_count = 0
    best: tuple[int, int, int, int, int] | None = None
    for start_y in range(height):
        row = start_y * width
        for start_x in range(width):
            idx = row + start_x
            if not mask[idx] or visited[idx]:
                continue
            stack = [idx]
            visited[idx] = 1
            count = 0
            min_x = max_x = start_x
            min_y = max_y = start_y
            while stack:
                cur = stack.pop()
                cy, cx = divmod(cur, width)
                count += 1
                if cx < min_x:
                    min_x = cx
                elif cx > max_x:
                    max_x = cx
                if cy < min_y:
                    min_y = cy
                elif cy > max_y:
                    max_y = cy
                if cx > 0:
                    left = cur - 1
                    if mask[left] and not visited[left]:
                        visited[left] = 1
                        stack.append(left)
                if cx + 1 < width:
                    right = cur + 1
                    if mask[right] and not visited[right]:
                        visited[right] = 1
                        stack.append(right)
                if cy > 0:
                    up = cur - width
                    if mask[up] and not visited[up]:
                        visited[up] = 1
                        stack.append(up)
                if cy + 1 < height:
                    down = cur + width
                    if mask[down] and not visited[down]:
                        visited[down] = 1
                        stack.append(down)
            if count > best_count:
                best_count = count
                best = (min_x, min_y, max_x + 1, max_y + 1, count)
    return best


def _build_mask(small: Image.Image, shot_type: str) -> bytearray:
    width, height = small.size
    mask = bytearray(width * height)
    checker = is_tongue_hsv if shot_type == "tongue" else is_skin_hsv
    for i, (r, g, b) in enumerate(small.getdata()):
        h, s, v = rgb_to_hsv_pixel(r, g, b)
        if checker(h, s, v):
            mask[i] = 1
    return mask


def _refine_box(
    x0: int, y0: int, x1: int, y1: int, width: int, height: int, shot_type: str
) -> tuple[int, int, int, int]:
    bw = max(1, x1 - x0)
    bh = max(1, y1 - y0)
    if shot_type == "tongue":
        pad_x = max(1, int(bw * 0.04))
        pad_y = max(1, int(bh * 0.04))
        x0 = max(0, x0 - pad_x)
        y0 = max(0, y0 - pad_y)
        x1 = min(width, x1 + pad_x)
        y1 = min(height, y1 + pad_y)
        return x0, y0, x1, y1
    # Face: hairline–chin, inside the ears (inset the skin blob).
    x0 += int(bw * 0.08)
    x1 -= int(bw * 0.08)
    y0 += int(bh * 0.04)
    y1 -= int(bh * 0.10)
    bw = max(1, x1 - x0)
    bh = max(1, y1 - y0)
    face_h = int(bw * 1.32)
    if bh > face_h:
        y1 = y0 + face_h
    x0 = max(0, min(x0, width - 2))
    y0 = max(0, min(y0, height - 2))
    x1 = max(x0 + 2, min(x1, width))
    y1 = max(y0 + 2, min(y1, height))
    return x0, y0, x1, y1


def _median_rgb(pixels: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    if not pixels:
        return (200, 176, 160)
    rs = sorted(p[0] for p in pixels)
    gs = sorted(p[1] for p in pixels)
    bs = sorted(p[2] for p in pixels)
    mid = len(pixels) // 2
    return rs[mid], gs[mid], bs[mid]


def _encode_preview_png(image: Image.Image) -> str:
    buf = BytesIO()
    image.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def isolate_subject(image: Image.Image, shot_type: str) -> tuple[Image.Image, dict[str, Any]]:
    """HSV largest-blob crop. Face ≈ hairline–chin / inner-ear; tongue ≈ tongue body only."""
    rgb = image.convert("RGB")
    full_w, full_h = rgb.size
    max_side = 180
    scale = min(1.0, max_side / max(full_w, full_h))
    small_w = max(1, int(full_w * scale))
    small_h = max(1, int(full_h * scale))
    small = rgb.resize((small_w, small_h), Image.Resampling.BILINEAR)
    mask = _build_mask(small, shot_type)
    blob = _largest_blob_box(mask, small_w, small_h)
    min_area = small_w * small_h * (0.05 if shot_type == "tongue" else 0.08)
    if blob is None or blob[4] < min_area:
        preview = rgb.copy()
        return preview, {
            "method": "passthrough",
            "reason": "blob_too_small",
            "box": [0.0, 0.0, 1.0, 1.0],
            "preview": _encode_preview_png(preview),
        }

    sx0, sy0, sx1, sy1, _count = blob
    sx0, sy0, sx1, sy1 = _refine_box(sx0, sy0, sx1, sy1, small_w, small_h, shot_type)
    inv = 1.0 / scale if scale else 1.0
    x0 = max(0, int(sx0 * inv))
    y0 = max(0, int(sy0 * inv))
    x1 = min(full_w, int(sx1 * inv))
    y1 = min(full_h, int(sy1 * inv))
    if x1 - x0 < 8 or y1 - y0 < 8:
        preview = rgb.copy()
        return preview, {
            "method": "passthrough",
            "reason": "box_too_small",
            "box": [0.0, 0.0, 1.0, 1.0],
            "preview": _encode_preview_png(preview),
        }

    cropped = rgb.crop((x0, y0, x1, y1))
    mask_img = Image.new("L", (small_w, small_h), 0)
    mask_img.putdata([255 if v else 0 for v in mask])
    mask_full = mask_img.resize((full_w, full_h), Image.Resampling.NEAREST).crop((x0, y0, x1, y1))
    fg_pixels = [pix for pix, alpha in zip(cropped.getdata(), mask_full.getdata()) if alpha]
    fill = _median_rgb(fg_pixels)
    out_rgb = Image.composite(cropped, Image.new("RGB", cropped.size, fill), mask_full)
    rgba = Image.new("RGBA", cropped.size, (0, 0, 0, 0))
    rgba.paste(cropped.convert("RGBA"), mask=mask_full)
    return out_rgb, {
        "method": "hsv_blob",
        "shot_type": shot_type,
        "box": [
            round(x0 / full_w, 4),
            round(y0 / full_h, 4),
            round(x1 / full_w, 4),
            round(y1 / full_h, 4),
        ],
        "preview": _encode_preview_png(rgba),
    }


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
            "gray_ratio": 0,
        }

    hues, sats, vals = [], [], []
    red = yellow = green = purple = white = pale = dark = gray = 0
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
        is_gray = s <= 0.28 and 0.12 <= v <= 0.45
        red += int(is_red)
        yellow += int(is_yellow)
        green += int(is_green)
        purple += int(is_purple)
        white += int(is_white)
        pale += int(is_pale)
        dark += int(is_dark)
        gray += int(is_gray)

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
        "gray_ratio": gray / n,
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
        "gray_ratio": round(stats.get("gray_ratio", 0), 3),
        "purple_ratio": round(stats.get("purple_ratio", 0), 3),
        "r": round(stats.get("r", 0), 1),
        "g": round(stats.get("g", 0), 1),
        "b": round(stats.get("b", 0), 1),
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
        "gray_ratio",
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
                        "id": 8,
                        "part": part,
                        "name": spec["name"],
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
                    "meaning": f"上{halves[0]['meaning']}／下{halves[1]['meaning']}",
                    "reading": f"上段{halves[0]['bias']} → {halves[0]['meaning']}／下段{halves[1]['bias']} → {halves[1]['meaning']}",
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
                "meaning": meaning,
                "reading": f"{bias} → {meaning}",
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
        "face_color": f"{c_bias}／{c_pattern}",
        "lip_color": lip_color,
        "tongue_body_color": None,
        "tongue_coat_color": None,
    }
    measurements = []
    for cell in cells:
        measurements.append(
            {
                "cell_id": cell["id"],
                "part": "whole",
                "name": cell["name"],
                "organs": cell["organs"],
                "hex": cell["hex"],
                "hsv": cell["hsv"],
                "bias": cell["bias"],
                "meaning": cell.get("meaning"),
                "reading": cell.get("reading"),
            }
        )
        for part in cell.get("split") or []:
            measurements.append(
                {
                    "cell_id": 8,
                    "part": part["part"],
                    "name": cell["name"],
                    "organs": part["organs"],
                    "hex": part["hex"],
                    "hsv": part["hsv"],
                    "bias": part["bias"],
                    "meaning": part["meaning"],
                    "reading": f"{part['bias']} → {part['meaning']}",
                }
            )
    complexion_hsv = compact_hsv(complexion_stats)
    measurements.append(
        {
            "cell_id": 0,
            "part": "complexion",
            "name": "臉色平均",
            "organs": "1,2,3,5,7,8,9,10,12",
            "hex": hex_from_stats(complexion_stats),
            "hsv": complexion_hsv,
            "bias": c_bias,
            "meaning": c_pattern,
            "reading": c_text,
        }
    )
    face_grid = {
        "rows": 4,
        "cols": 3,
        "layout": "4x3",
        "numbering": "row4 visual 10 | 12 lips | 11",
        "cells": cells,
        "measurements": measurements,
        "complexion": {
            "hex": hex_from_stats(complexion_stats),
            "hsv": complexion_hsv,
            "bias": c_bias,
            "pattern": c_pattern,
            "interpretation": c_text,
            "included_cells": list(COMPLEXION_CELL_IDS),
            "excluded_cells": list(COMPLEXION_EXCLUDED_IDS),
        },
        "disclaimer": TEACHING_NOTE,
    }
    return face_grid, findings, colors


# Photo orientation: tongue tip toward BOTTOM (lips), root toward TOP.
# User listed 上中下左右 (5). The 6th layer is whole-tongue coating overlay,
# not a sixth spatial tile (中 is not split into 中上/中下).
TONGUE_ZONE_LAYOUT = [
    {"id": "top", "label": "上", "organs": "腎", "anatomy": "舌根", "left": 0.22, "top": 0.02, "right": 0.78, "bottom": 0.30},
    {"id": "center", "label": "中", "organs": "脾胃", "anatomy": "舌中", "left": 0.28, "top": 0.28, "right": 0.72, "bottom": 0.72},
    {"id": "bottom", "label": "下", "organs": "心肺", "anatomy": "舌尖", "left": 0.22, "top": 0.70, "right": 0.78, "bottom": 0.98},
    {"id": "left", "label": "左", "organs": "肝膽", "anatomy": "舌左邊", "left": 0.02, "top": 0.22, "right": 0.28, "bottom": 0.78},
    {"id": "right", "label": "右", "organs": "肝膽", "anatomy": "舌右邊", "left": 0.72, "top": 0.22, "right": 0.98, "bottom": 0.78},
]
TONGUE_COAT_BOX = {"left": 0.24, "top": 0.16, "right": 0.76, "bottom": 0.74}
TONGUE_SIXTH_NOTE = "使用者列上中下左右五塊；第六層為全舌舌苔疊加（非再切一塊空間）。中區不拆中上／中下。"


def tongue_body_reading(stats: dict[str, float]) -> tuple[str, str]:
    if stats["red_ratio"] > 0.18:
        return "偏紅", "實熱證"
    if stats["white_ratio"] > 0.22 or stats["pale_ratio"] > 0.28:
        return "偏白", "虛寒證"
    return "中性", "舌質未見明顯紅白偏色"


def tongue_coat_reading(stats: dict[str, float]) -> tuple[str, str]:
    grayish = stats.get("gray_ratio", 0) + stats.get("dark_ratio", 0)
    if grayish > 0.16 and stats["v"] < 0.48:
        return "黑灰苔", "實寒證"
    if stats["yellow_ratio"] > 0.16:
        return "黃苔", "實熱"
    if stats["white_ratio"] < 0.12:
        return "白苔很少", "胃虛"
    return "苔色中性", "未見黃／黑灰／少白苔"


def analyze_tongue_grid(image: Image.Image) -> tuple[dict[str, Any], list[str], dict[str, str | None]]:
    findings: list[str] = []
    zones: list[dict[str, Any]] = []
    zone_stats: list[dict[str, float]] = []
    for spec in TONGUE_ZONE_LAYOUT:
        crop = crop_box(image, spec["left"], spec["top"], spec["right"], spec["bottom"])
        stats = region_stats(crop)
        zone_stats.append(stats)
        bias, meaning = tongue_body_reading(stats)
        interpretation = (
            f"{spec['label']}（{spec['organs']}／{spec['anatomy']}）舌質{bias} → {meaning}（{TEACHING_NOTE}）"
        )
        if bias != "中性":
            findings.append(interpretation)
        zones.append(
            {
                "id": spec["id"],
                "label": spec["label"],
                "organs": spec["organs"],
                "anatomy": spec["anatomy"],
                "left": spec["left"],
                "top": spec["top"],
                "right": spec["right"],
                "bottom": spec["bottom"],
                "hex": hex_from_stats(stats),
                "hsv": compact_hsv(stats),
                "bias": bias,
                "meaning": meaning,
                "reading": f"舌質{bias} → {meaning}",
                "interpretation": interpretation,
            }
        )

    coat_crop = crop_box(
        image,
        TONGUE_COAT_BOX["left"],
        TONGUE_COAT_BOX["top"],
        TONGUE_COAT_BOX["right"],
        TONGUE_COAT_BOX["bottom"],
    )
    coat_stats = region_stats(coat_crop)
    coat_bias, coat_meaning = tongue_coat_reading(coat_stats)
    coat_text = f"舌苔（全舌疊加）{coat_bias} → {coat_meaning}（{TEACHING_NOTE}）"
    findings.append(coat_text)

    body_stats = average_stats(zone_stats)
    body_bias, body_meaning = tongue_body_reading(body_stats)
    colors = {
        "face_color": None,
        "lip_color": None,
        "tongue_body_color": f"{body_bias}／{body_meaning}",
        "tongue_coat_color": f"{coat_bias}／{coat_meaning}",
    }
    coating = {
        "id": "coating",
        "label": "舌苔",
        "organs": "胃／全舌",
        "layer": 6,
        "hex": hex_from_stats(coat_stats),
        "hsv": compact_hsv(coat_stats),
        "bias": coat_bias,
        "meaning": coat_meaning,
        "reading": f"{coat_bias} → {coat_meaning}",
        "interpretation": coat_text,
        "box": TONGUE_COAT_BOX,
    }
    measurements = [
        {
            "zone_id": zone["id"],
            "part": "body",
            "label": zone["label"],
            "organs": zone["organs"],
            "hex": zone["hex"],
            "hsv": zone["hsv"],
            "bias": zone["bias"],
            "meaning": zone["meaning"],
            "reading": zone["reading"],
        }
        for zone in zones
    ]
    measurements.append(
        {
            "zone_id": "coating",
            "part": "coating",
            "label": "舌苔",
            "organs": "胃／全舌",
            "hex": coating["hex"],
            "hsv": coating["hsv"],
            "bias": coat_bias,
            "meaning": coat_meaning,
            "reading": coating["reading"],
        }
    )
    tongue_grid = {
        "zones": 5,
        "sixth": "coating_overlay",
        "sixth_note": TONGUE_SIXTH_NOTE,
        "orientation": "tip_at_bottom_root_at_top",
        "layout": TONGUE_ZONE_LAYOUT,
        "cells": zones,
        "coating": coating,
        "measurements": measurements,
        "body": {
            "hex": hex_from_stats(body_stats),
            "hsv": compact_hsv(body_stats),
            "bias": body_bias,
            "meaning": body_meaning,
        },
        "disclaimer": TEACHING_NOTE,
    }
    return tongue_grid, findings, colors


def inspect_image(image_bytes: bytes, shot_type: str) -> dict[str, Any]:
    raw_image = Image.open(BytesIO(image_bytes)).convert("RGB")
    image, crop_info = isolate_subject(raw_image, shot_type)
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
    tongue_grid = None
    if shot_type == "tongue":
        tongue_grid, grid_findings, colors = analyze_tongue_grid(image)
        findings.extend(grid_findings)
    else:
        face_grid, grid_findings, colors = analyze_face_grid(image)
        findings.extend(grid_findings)

    if not findings:
        findings.append("未見明顯偏色，先給中間分數 5")

    complexion = (face_grid or {}).get("complexion")
    tongue_body = (tongue_grid or {}).get("body")
    coating = (tongue_grid or {}).get("coating")
    if tongue_grid:
        color_label = f"舌質{tongue_body.get('bias')} → {tongue_body.get('meaning')}；{coating.get('bias')} → {coating.get('meaning')}"
        hsv_out = (tongue_body or {}).get("hsv") or compact_hsv(overall)
        dominant_out = (tongue_body or {}).get("hex") or dominant
    else:
        color_label = (complexion or {}).get("interpretation") or hsv_label(overall)
        hsv_out = (complexion or {}).get("hsv") or {
            "hue": round(overall["h"], 1),
            "saturation": round(overall["s"], 3),
            "value": round(overall["v"], 3),
        }
        dominant_out = (complexion or {}).get("hex") or dominant
    return {
        "shot_type": shot_type,
        "dominant_color": dominant_out,
        "hsv": hsv_out,
        "color_label": color_label,
        "findings": findings,
        "region_colors": colors,
        "face_grid": face_grid,
        "tongue_grid": tongue_grid,
        "crop": crop_info,
        "preview": crop_info.get("preview"),
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
    tongue_grid = None
    face_preview = None
    tongue_preview = None
    crops: dict[str, Any] = {}
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
        if report.get("tongue_grid"):
            tongue_grid = report["tongue_grid"]
        if report.get("crop"):
            crops[report["shot_type"]] = {k: v for k, v in report["crop"].items() if k != "preview"}
        if report["shot_type"] == "face" and report.get("preview"):
            face_preview = report["preview"]
        if report["shot_type"] == "tongue" and report.get("preview"):
            tongue_preview = report["preview"]

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
        "tongue_grid": tongue_grid,
        "complexion": (face_grid or {}).get("complexion"),
        "face_preview": face_preview,
        "tongue_preview": tongue_preview,
        "crop": crops,
        "disclaimer": "此為教學示範用色彩／臟腑對應邏輯，不能取代醫師診斷。CNN 醫學模型可於蒐集標註照片後再訓練。",
    }
