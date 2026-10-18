from __future__ import annotations

import base64
from collections import Counter
from io import BytesIO
from typing import Any

from PIL import Image

from .syndrome import ORGAN_META, add, apply_color_findings, apply_pulse, apply_text, empty_evidence, finalize


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
# Cells 4 and 5 are the eyes. Cell 8 is the nose. Cell 12 lips use the redder pixels only.
FACE_CELL_LAYOUT = [
    {"id": 1, "row": 0, "col": 0, "name": "左側面", "organs": "左臉", "targets": []},
    {"id": 2, "row": 0, "col": 1, "name": "額頭", "organs": "咽喉／肺", "targets": ["lung"]},
    {"id": 3, "row": 0, "col": 2, "name": "右側面", "organs": "右臉", "targets": []},
    {"id": 4, "row": 1, "col": 0, "name": "左眼", "organs": "肝", "targets": ["liver"], "kind": "eye"},
    {"id": 5, "row": 1, "col": 1, "name": "眼", "organs": "肝", "targets": ["liver"], "kind": "eye"},
    {"id": 6, "row": 1, "col": 2, "name": "右側面", "organs": "右臉", "targets": []},
    {"id": 7, "row": 2, "col": 0, "name": "左頰", "organs": "小腸／大腸", "targets": ["small_intestine", "large_intestine"]},
    {"id": 8, "row": 2, "col": 1, "name": "鼻子", "organs": "肺", "targets": ["lung"]},
    {"id": 9, "row": 2, "col": 2, "name": "右頰", "organs": "小腸／大腸", "targets": ["small_intestine", "large_intestine"]},
    {"id": 10, "row": 3, "col": 0, "name": "左下頜", "organs": "腎", "targets": ["kidney"]},
    {"id": 12, "row": 3, "col": 1, "name": "唇", "organs": "脾", "targets": ["spleen"], "kind": "lip"},
    {"id": 11, "row": 3, "col": 2, "name": "右下頜", "organs": "腎", "targets": ["kidney"]},
]
COMPLEXION_CELL_IDS = (1, 2, 3, 5, 7, 8, 9, 10, 11)
COMPLEXION_EXCLUDED_IDS = (4, 6, 12)
TEACHING_NOTE = "教學示範，非中醫診斷"
DAMP_OVERLAY = "mositure.png"
# Shared face and lip color table.
SYNDROME_RANGES = (
    {
        "meaning": "實熱",
        "look": "鮮紅、深紅、乾焦",
        "r": (160, 220),
        "g": (20, 50),
        "b": (20, 50),
        "example": "#B82323",
        "overlay": "strong-hot.png",
        "targets": ["large_intestine", "spleen"],
        "patterns": (("實證", 1.6), ("熱證", 1.8)),
    },
    {
        "meaning": "實寒",
        "look": "青紫、暗黑、滯暗",
        "r": (80, 130),
        "g": (40, 80),
        "b": (70, 110),
        "example": "#6A425A",
        "overlay": "strong-cold.png",
        "targets": ["heart", "lung"],
        "patterns": (("實證", 1.6), ("寒證", 1.8)),
    },
    {
        "meaning": "虛熱",
        "look": "嫩紅、顴紅唇赤、少津",
        "r": (220, 255),
        "g": (90, 140),
        "b": (110, 150),
        "example": "#E87D8E",
        "overlay": "weak-hot.png",
        "targets": ["spleen"],
        "patterns": (("虛證", 1.6), ("熱證", 1.8)),
    },
    {
        "meaning": "虛寒",
        "look": "淡白、無血色、多液",
        "r": (210, 240),
        "g": (170, 200),
        "b": (170, 200),
        "example": "#E3B5B5",
        "overlay": "weak-cold.png",
        "targets": ["spleen"],
        "patterns": (("虛證", 1.6), ("寒證", 1.8)),
    },
)


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


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def _color_scores(cell: dict[str, float], base: dict[str, float]) -> dict[str, float]:
    dr = cell["r"] - base["r"]
    dg = cell["g"] - base["g"]
    db = cell["b"] - base["b"]
    return {
        "red": dr - max(dg, db),
        "yellow": min(dr, dg) - db,
        "black": -((dr + dg + db) / 3.0),
        "white": (dr + dg + db) / 3.0,
    }


def compare_to_base(cell: dict[str, float], base: dict[str, float], kind: str) -> dict[str, Any]:
    """Difference from the baseline complexion. Eyes only flag red or yellow."""
    scores = _color_scores(cell, base)
    if kind == "eye":
        if scores["red"] >= 12 and scores["red"] >= scores["yellow"]:
            return {
                "bias": "較紅",
                "meaning": "肝實熱",
                "overlay": "strong-hot.png",
                "patterns": (("實證", 1.6), ("熱證", 1.8)),
                "score": scores["red"],
            }
        if scores["yellow"] >= 12:
            return {
                "bias": "較黃",
                "meaning": "濕氣較重",
                "overlay": DAMP_OVERLAY,
                "patterns": (("實證", 1.4),),
                "score": scores["yellow"],
            }
        return {
            "bias": "白／黑",
            "meaning": "眼色以白與黑為主",
            "overlay": None,
            "patterns": (),
            "score": 0.0,
        }

    choices = (
        ("較紅", "實熱", "strong-hot.png", (("實證", 1.6), ("熱證", 1.8)), scores["red"]),
        ("較黃", "濕氣較重", DAMP_OVERLAY, (("實證", 1.4),), scores["yellow"]),
        ("較黑", "實寒", "strong-cold.png", (("實證", 1.6), ("寒證", 1.8)), scores["black"]),
        ("較白", "虛寒", "weak-cold.png", (("虛證", 1.6), ("寒證", 1.8)), scores["white"]),
    )
    bias, meaning, overlay, patterns, score = max(choices, key=lambda item: item[4])
    if score < 12:
        return {
            "bias": "接近基本色",
            "meaning": "未見明顯色差",
            "overlay": None,
            "patterns": (),
            "score": score,
        }
    return {"bias": bias, "meaning": meaning, "overlay": overlay, "patterns": patterns, "score": score}


def reddish_lip_rgb(image: Image.Image) -> tuple[tuple[int, int, int], dict[str, float]]:
    """Cell 12's redder pixels are the lips; fall back to the whole cell."""
    picked = [pixel for pixel in image.getdata() if pixel[0] >= 90 and pixel[0] >= pixel[1] + 12 and pixel[0] >= pixel[2] + 12]
    if len(picked) < 12:
        stats = region_stats(image)
        return (int(stats["r"]), int(stats["g"]), int(stats["b"])), stats
    count = float(len(picked))
    rgb = tuple(int(round(sum(pixel[i] for pixel in picked) / count)) for i in range(3))
    swatch = Image.new("RGB", (1, 1), rgb)
    return rgb, region_stats(swatch)


def _range_gap(value: int, low: int, high: int) -> int:
    if value < low:
        return low - value
    if value > high:
        return value - high
    return 0


def match_lip_color(rgb: tuple[int, int, int], slack: int = 24) -> dict[str, Any]:
    """Match lip RGB to the 實熱／實寒／虛熱／虛寒 ranges. Inside a range wins."""
    inside = []
    nearest = None
    nearest_gap = 10**9
    for spec in SYNDROME_RANGES:
        gap = (
            _range_gap(rgb[0], *spec["r"])
            + _range_gap(rgb[1], *spec["g"])
            + _range_gap(rgb[2], *spec["b"])
        )
        example = _hex_to_rgb(spec["example"])
        dist = sum((channel - ref) ** 2 for channel, ref in zip(rgb, example)) ** 0.5
        if gap == 0:
            inside.append((dist, spec))
        if gap < nearest_gap or (gap == nearest_gap and nearest and dist < nearest[0]):
            nearest_gap = gap
            nearest = (dist, spec)
    if inside:
        _dist, spec = min(inside, key=lambda item: item[0])
        matched = True
        gap = 0
    else:
        _dist, spec = nearest
        matched = nearest_gap <= slack
        gap = nearest_gap
    if not matched:
        return {
            "bias": "未入色域",
            "meaning": "未落入實熱、實寒、虛熱、虛寒色域",
            "overlay": None,
            "patterns": (),
            "targets": [],
            "score": 0.0,
            "reference": spec["example"],
            "distance": gap,
            "look": spec["look"],
        }
    return {
        "bias": spec["meaning"],
        "meaning": f"{spec['meaning']}（{spec['look']}）",
        "overlay": spec["overlay"],
        "patterns": spec["patterns"],
        "targets": spec["targets"],
        "score": max(1.0, 80.0 - gap),
        "reference": spec["example"],
        "distance": gap,
        "look": spec["look"],
    }


def classify_face_color(stats: dict[str, float], base: dict[str, float], kind: str) -> dict[str, Any]:
    """Prefer the 實熱／實寒／虛熱／虛寒 ranges; otherwise compare with the baseline."""
    rgb = (int(round(stats["r"])), int(round(stats["g"])), int(round(stats["b"])))
    ranged = match_lip_color(rgb, slack=0)
    if ranged.get("overlay"):
        meaning = ranged["bias"]
        if kind == "eye":
            if meaning == "實熱":
                return {
                    "bias": "實熱",
                    "meaning": "肝實熱（鮮紅、深紅、乾焦）",
                    "overlay": "strong-hot.png",
                    "patterns": (("實證", 1.6), ("熱證", 1.8)),
                    "score": ranged["score"],
                    "reference": ranged["reference"],
                    "source": "色域",
                }
            if meaning == "虛熱":
                return {
                    "bias": "虛熱",
                    "meaning": "肝虛熱（嫩紅、少津）",
                    "overlay": "weak-hot.png",
                    "patterns": (("虛證", 1.6), ("熱證", 1.8)),
                    "score": ranged["score"],
                    "reference": ranged["reference"],
                    "source": "色域",
                }
            return {
                "bias": "白／黑",
                "meaning": "眼色以白與黑為主",
                "overlay": None,
                "patterns": (),
                "score": 0.0,
                "reference": ranged["reference"],
                "source": "色域",
            }
        ranged["source"] = "色域"
        return ranged
    reading = compare_to_base(stats, base, kind)
    reading["source"] = "基本色"
    reading["reference"] = None
    return reading


def analyze_face_grid(image: Image.Image) -> tuple[dict[str, Any], list[str], dict[str, str | None]]:
    findings: list[str] = []
    cells: list[dict[str, Any]] = []
    stats_by_id: dict[int, dict[str, float]] = {}
    crops: dict[int, Image.Image] = {}

    for spec in FACE_CELL_LAYOUT:
        crop = crop_cell(image, spec["row"], spec["col"])
        crops[spec["id"]] = crop
        stats_by_id[spec["id"]] = region_stats(crop)

    complexion_stats = average_stats([stats_by_id[i] for i in COMPLEXION_CELL_IDS if i in stats_by_id])
    base_hex = hex_from_stats(complexion_stats)
    c_text = (
        f"基本色取第 1、2、3、5、7、8、9、10、11 格平均 {base_hex}，"
        f"各區先對照實熱、實寒、虛熱、虛寒色域，沒入色域再跟基本色比色差（{TEACHING_NOTE}）"
    )
    findings.append(c_text)

    best_overlay: dict[str, tuple[float, str, tuple[tuple[str, float], ...]]] = {}

    def remember(targets: list[str], reading: dict[str, Any]) -> None:
        overlay = reading.get("overlay")
        if not overlay:
            return
        for organ in targets:
            previous = best_overlay.get(organ)
            if previous is None or reading["score"] > previous[0]:
                best_overlay[organ] = (reading["score"], overlay, reading["patterns"])

    lip_color = None
    for spec in FACE_CELL_LAYOUT:
        cell_id = spec["id"]
        kind = spec.get("kind")
        if kind == "lip":
            rgb, stats = reddish_lip_rgb(crops[cell_id])
            stats_by_id[cell_id] = stats
            reading = match_lip_color(rgb)
            targets = reading["targets"]
            interpretation = (
                f"第12格唇較紅區域 {hex_from_stats(stats)} "
                f"對照色域，參考 {reading['reference']} → {reading['meaning']}（{TEACHING_NOTE}）"
            )
            lip_color = f"唇{reading['meaning']}（參考 {reading['reference']}）"
        else:
            stats = stats_by_id[cell_id]
            reading = classify_face_color(stats, complexion_stats, kind or "face")
            targets = spec["targets"] if reading.get("overlay") else []
            how = "落入色域" if reading.get("source") == "色域" else "相對基本色"
            ref = f"，參考 {reading['reference']}" if reading.get("reference") else ""
            interpretation = (
                f"第{cell_id}格{spec['name']}（{spec['organs']}）{hex_from_stats(stats)} "
                f"{how}{reading['bias']}{ref} → {reading['meaning']}（{TEACHING_NOTE}）"
            )
        if reading["meaning"] not in ("未見明顯色差", "眼色以白與黑為主"):
            findings.append(interpretation)
        remember(targets, reading)
        cells.append(
            {
                "id": cell_id,
                "row": spec["row"],
                "col": spec["col"],
                "name": spec["name"],
                "organs": spec["organs"],
                "hex": hex_from_stats(stats_by_id[cell_id]),
                "hsv": compact_hsv(stats_by_id[cell_id]),
                "bias": reading["bias"],
                "meaning": reading["meaning"],
                "reading": f"{reading['bias']} → {reading['meaning']}",
                "interpretation": interpretation,
                "overlay": reading.get("overlay"),
                "split": None,
            }
        )

    organ_overlays = {organ: filename for organ, (_score, filename, _patterns) in best_overlay.items()}
    marks = [
        {"organ": organ, "pattern": name, "weight": weight}
        for organ, (_score, _filename, patterns) in best_overlay.items()
        for name, weight in patterns
    ]
    colors = {
        "face_color": f"基本色 {base_hex}",
        "lip_color": lip_color,
        "tongue_body_color": None,
        "tongue_coat_color": None,
    }
    measurements = [
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
        for cell in cells
    ]
    complexion_hsv = compact_hsv(complexion_stats)
    measurements.append(
        {
            "cell_id": 0,
            "part": "complexion",
            "name": "基本色",
            "organs": "1,2,3,5,7,8,9,10,11",
            "hex": base_hex,
            "hsv": complexion_hsv,
            "bias": "基本色",
            "meaning": "各區色差的比較基準",
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
        "marks": marks,
        "organ_overlays": organ_overlays,
        "complexion": {
            "hex": base_hex,
            "hsv": complexion_hsv,
            "bias": "基本色",
            "pattern": "色差基準",
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
    for mark in (face_grid or {}).get("marks") or []:
        add(evidence, mark["organ"], mark["pattern"], mark["weight"])
    pulse_notes = apply_pulse(evidence, pulse)
    scores, patterns, overlays = finalize(evidence)
    for organ, filename in ((face_grid or {}).get("organ_overlays") or {}).items():
        overlays[organ] = filename
        if filename == DAMP_OVERLAY:
            for key, _name, _score_key, pattern_key in ORGAN_META:
                if key == organ:
                    patterns[pattern_key] = "濕氣較重"
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
