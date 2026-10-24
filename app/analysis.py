from __future__ import annotations

import base64
from collections import Counter
from io import BytesIO
from typing import Any

from PIL import Image, ImageFilter

from .syndrome import (
    ORGAN_META,
    add,
    apply_color_findings,
    apply_pulse,
    apply_text,
    compose_organ_health,
    empty_evidence,
    finalize,
    apply_pattern_scores_to_evidence,
    organ_patterns_from_color_blocks,
    organ_scores_from_color_blocks,
    overlay_from_pattern_label,
    pattern_kinds_gained,
    score_spleen_stomach_symptoms,
    serialize_organ_health,
)


def clamp(value: float, low: int = 1, high: int = 10) -> int:
    return max(low, min(high, int(round(value))))


COLOR_DELTA_TINY = 1.0
DELTA_E_REF = 20.0
TONGUE_COAT_DELTA_E_REF = 24.0
# Inside this ΔE of the teaching normal: scores 7–10. Beyond it: 1–6.
NORMAL_DELTA_E = 3.0
FACE_ZH_TO_ORGAN = {
    "小腸": "small_intestine",
    "大腸": "large_intestine",
    "肺": "lung",
    "肝": "liver",
    "膽": "gallbladder",
    "脾": "spleen",
    "胃": "stomach",
    "心": "heart",
    "腎": "kidney",
}


def organs_from_zh(text: str) -> list[str]:
    organs: list[str] = []
    blob = (text or "").replace("／", "、")
    for zh in sorted(FACE_ZH_TO_ORGAN, key=len, reverse=True):
        if zh in blob:
            key = FACE_ZH_TO_ORGAN[zh]
            if key not in organs:
                organs.append(key)
    return organs


def _lab_channels(stats: dict[str, float]) -> tuple[float, float, float]:
    a_val = stats.get("a_star")
    if a_val is None:
        a_val = stats.get("a") or 0
    b_val = stats.get("b_star")
    if b_val is None:
        b_val = stats.get("b") or 0
    return float(stats.get("L") or 0), float(a_val), float(b_val)


def lab_cie76(sample: dict[str, float], base: dict[str, float]) -> float:
    s_l, s_a, s_b = _lab_channels(sample)
    b_l, b_a, b_b = _lab_channels(base)
    return ((s_l - b_l) ** 2 + (s_a - b_a) ** 2 + (s_b - b_b) ** 2) ** 0.5


def relative_delta_health_score(
    delta_e: float,
    d_min: float,
    d_max: float,
    tiny: float = COLOR_DELTA_TINY,
) -> int:
    span = d_max - d_min
    if span < tiny:
        return 10
    return clamp(10 - 9 * (delta_e - d_min) / span)


def delta_e_ref_health_score(
    delta_e: float,
    ref: float = DELTA_E_REF,
    spec: float = NORMAL_DELTA_E,
) -> int:
    """Inside the normal ΔE spec: 10 at the teaching color, 7 at the spec edge.

    Outside the spec: 6 just past the edge, 1 at ΔE_ref (face/舌質 20, 舌苔 24) or farther.
    """
    delta = max(0.0, float(delta_e))
    if spec <= 0:
        return 10
    if delta <= spec:
        return clamp(10 - 3 * delta / spec)
    span = max(float(ref) - spec, 1e-6)
    outside = min(1.0, (delta - spec) / span)
    return clamp(6 - 5 * outside)


def apply_relative_color_scores(
    blocks: list[dict[str, Any]],
    tiny: float = COLOR_DELTA_TINY,
    ref: float = DELTA_E_REF,
    mode: str = "ref",
) -> dict[str, Any]:
    """1–10 health from ΔE vs teaching normal (ref) or min-max across blocks."""
    deltas = [float(block.get("delta_e") or 0) for block in blocks]
    d_min = min(deltas) if deltas else 0.0
    d_max = max(deltas) if deltas else 0.0
    for block in blocks:
        delta = float(block.get("delta_e") or 0)
        if mode == "minmax":
            block["health_score"] = relative_delta_health_score(delta, d_min, d_max, tiny)
        else:
            block["health_score"] = delta_e_ref_health_score(delta, ref)
    return {
        "formula": (
            "規格內（ΔE≤3）10→7；超出規格 6→1（ΔE_ref 為 1 分）。7–10 正常。"
            if mode != "minmax"
            else "score=round(10-9*(ΔE-d_min)/(d_max-d_min)) clamp 1–10；近基準→10，最大ΔE→1。"
        ),
        "mode": mode,
        "ref": ref,
        "d_min": round(d_min, 3),
        "d_max": round(d_max, 3),
        "tiny": tiny,
        "n_blocks": len(blocks),
        "organ_scores": organ_scores_from_color_blocks(blocks),
        "organ_patterns": organ_patterns_from_color_blocks(blocks),
        "blocks": [
            {
                "label": block.get("label"),
                "organs": block.get("organs") or [],
                "delta_e": block.get("delta_e"),
                "health_score": block.get("health_score"),
                "class_label": block.get("class_label"),
                "api_pattern": block.get("api_pattern"),
            }
            for block in blocks
        ],
    }


def nearest_face_class(stats: dict[str, float]) -> dict[str, Any]:
    best = FACE_COLOR_CLASSES[0]
    best_d = lab_cie76(stats, best["centroid"])
    for spec in FACE_COLOR_CLASSES[1:]:
        dist = lab_cie76(stats, spec["centroid"])
        if dist < best_d:
            best = spec
            best_d = dist
    return {**best, "centroid_delta_e": round(best_d, 2)}


def make_face_block(label: str, stats: dict[str, float], organs: list[str] | tuple[str, ...]) -> dict[str, Any]:
    delta = round(lab_cie76(stats, FACE_NORMAL_LAB), 2)
    hit = nearest_face_class(stats)
    health = delta_e_ref_health_score(delta, DELTA_E_REF)
    overlay = hit["overlay"] if health < 7 and hit["id"] != "normal" else None
    return {
        "label": label,
        "organs": list(organs or []),
        "delta_e": delta,
        "class_id": hit["id"],
        "class_label": hit["label"],
        "bias": hit["bias"],
        "api_pattern": "健康" if hit["id"] == "normal" or health >= 7 else hit["api_pattern"],
        "overlay": overlay,
        "patterns": hit["patterns"] if overlay else (),
        "look": hit["look"],
        "centroid_delta_e": hit["centroid_delta_e"],
    }


def tongue_coating_ratio(seg: dict[str, Any]) -> float:
    body_n = float((seg.get("body_stats") or {}).get("pixel_count") or 0)
    coat_n = float((seg.get("coat_stats") or {}).get("pixel_count") or 0)
    return coat_n / max(1.0, body_n + coat_n)


def classify_tongue_bianzheng(
    body: dict[str, float],
    coat: dict[str, float],
    coating_ratio: float,
    surface: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Three core logics: 實熱/虛熱 by coat vs peel; 實寒/虛寒 by L*; 濕 primarily coat."""
    body = body or {}
    coat = coat or {}
    coat_n = float(coat.get("pixel_count") or 0)
    body_de = lab_cie76(body, TONGUE_BODY_NORMAL)
    if coat_n >= TONGUE_LAB_THRESHOLDS["min_mask_pixels"]:
        coat_de = lab_cie76(coat, TONGUE_COAT_NORMAL)
    elif coating_ratio < TONGUE_MIRROR_COAT_MAX:
        coat_de = 8.0 + 12.0 * max(0.0, (TONGUE_MIRROR_COAT_MAX - coating_ratio) / TONGUE_MIRROR_COAT_MAX)
    else:
        coat_de = lab_cie76(coat, TONGUE_COAT_NORMAL)
    da_b = float(body.get("a_star") or 0) - TONGUE_BODY_NORMAL["a_star"]
    dL_b = float(body.get("L") or 0) - TONGUE_BODY_NORMAL["L"]
    db_c = float(coat.get("b_star") or 0) - TONGUE_COAT_NORMAL["b_star"]
    dL_c = float(coat.get("L") or 0) - TONGUE_COAT_NORMAL["L"]
    heat = float(body.get("a_star") or 0) >= TONGUE_LAB_THRESHOLDS["body_heat_a_min"]
    ischemic = da_b <= -6.0
    mirror = coating_ratio < TONGUE_MIRROR_COAT_MAX
    yellow_thick = db_c >= 10.0 and dL_c <= -2.0
    pale_bright = dL_b >= 7.0
    dark_stasis = dL_b <= -8.0
    damp_coat = dL_c <= -10.0 and db_c >= 14.0
    greasy = False
    if surface:
        greasy = surface.get("energy", 0) >= 0.35 and surface.get("highlight", 1) <= 0.03
    label = "正常"
    reason = "近淡紅舌、薄白苔"
    if heat and mirror:
        label, reason = "虛熱", "舌質 a* 升且 coating_ratio<0.20（少苔／鏡面）→ 陰虛火旺"
    elif heat and yellow_thick:
        label, reason = "實熱", "舌質 a* 升且苔 b* 升、苔 L* 降（厚黃）→ 邪熱熾盛"
    elif ischemic and pale_bright:
        label, reason = "虛寒", "舌質 a* 降且 L* 升（淡白晄白）→ 陽虛血虛"
    elif ischemic and dark_stasis:
        label, reason = "實寒", "舌質 a* 降且 L* 降（青紫）→ 寒邪凝滯"
    elif damp_coat and body_de <= 6.0:
        label, reason = "濕症", "苔 L* 降且 b* 升（厚膩）→ 痰濕／濕熱"
        if greasy:
            reason += "；膩苔（GLCM 能量高、高光少）"
    elif heat and coating_ratio < 0.28:
        label, reason = "虛熱", "舌質偏紅、苔偏少"
    elif heat:
        label, reason = "實熱", "舌質偏紅"
    elif ischemic and dL_b > 0:
        label, reason = "虛寒", "舌質淡而偏亮"
    elif ischemic:
        label, reason = "實寒", "舌質暗淡缺血"
    elif damp_coat or (db_c >= 14 and greasy):
        label, reason = "濕症", "苔厚膩偏黃"
    meta = TONGUE_CLASS_META[label]
    body_health = delta_e_ref_health_score(body_de, DELTA_E_REF)
    coat_health = delta_e_ref_health_score(coat_de, TONGUE_COAT_DELTA_E_REF)
    overlay = meta["overlay"] if min(body_health, coat_health) < 7 and label != "正常" else None
    return {
        "label": label,
        "bias": meta["bias"],
        "meaning": reason,
        "api_pattern": "健康" if label == "正常" or min(body_health, coat_health) >= 7 else meta["api_pattern"],
        "overlay": overlay,
        "patterns": meta["patterns"],
        "targets": meta["targets"],
        "body_delta_e": round(body_de, 2),
        "coat_delta_e": round(coat_de, 2),
        "body_health": body_health,
        "coat_health": coat_health,
        "coating_ratio": round(coating_ratio, 3),
        "coating_ratio_def": TONGUE_COATING_RATIO_DEF,
        "discriminators": {
            "heat_body_da": round(da_b, 1),
            "mirror_coat": mirror,
            "yellow_thick_coat": yellow_thick,
            "ischemic_low_a": ischemic,
            "vacuity_cold_high_L": pale_bright,
            "excess_cold_low_L": dark_stasis,
            "damp_coat_low_L_high_b": damp_coat,
            "greasy_texture": greasy,
        },
    }


def crop_box(image: Image.Image, left: float, top: float, right: float, bottom: float) -> Image.Image:
    width, height = image.size
    box = (
        int(width * left),
        int(height * top),
        int(width * right),
        int(height * bottom),
    )
    return image.crop(box)


def _thumbnail_rgb(image: Image.Image, max_side: int = 160) -> Image.Image:
    work = image.convert("RGB")
    work.thumbnail((max_side, max_side))
    return work


def sample_pixels(image: Image.Image, max_side: int = 160) -> list[tuple[int, int, int]]:
    return list(_thumbnail_rgb(image, max_side).getdata())


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def rgb_to_lab_pixels(image: Image.Image, max_side: int = 160) -> list[tuple[float, float, float]]:
    """Pillow LAB: 8-bit L maps to L* 0–100; a/b 128 is CIELAB 0."""
    lab = _thumbnail_rgb(image, max_side).convert("LAB")
    return [(L * 100.0 / 255.0, a - 128.0, b - 128.0) for L, a, b in lab.getdata()]


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


def _empty_region_stats() -> dict[str, float]:
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
        "L": 0,
        "a_star": 0,
        "b_star": 0,
        "L_median": 0,
        "a_median": 0,
        "b_median": 0,
        "pixel_count": 0,
    }


def _stats_from_rgb_lab(
    rgb_pixels: list[tuple[int, int, int]],
    lab_pixels: list[tuple[float, float, float]],
) -> dict[str, float]:
    if not rgb_pixels:
        return _empty_region_stats()

    hues, sats, vals = [], [], []
    red = yellow = green = purple = white = pale = dark = gray = 0
    rs = gs = bs = 0
    for r, g, b in rgb_pixels:
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

    l_vals = [item[0] for item in lab_pixels]
    a_vals = [item[1] for item in lab_pixels]
    b_vals = [item[2] for item in lab_pixels]
    n = float(len(rgb_pixels))
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
        "L": sum(l_vals) / n,
        "a_star": sum(a_vals) / n,
        "b_star": sum(b_vals) / n,
        "L_median": _median(l_vals),
        "a_median": _median(a_vals),
        "b_median": _median(b_vals),
        "pixel_count": float(len(rgb_pixels)),
    }


def region_stats(image: Image.Image) -> dict[str, float]:
    work = _thumbnail_rgb(image)
    rgb = list(work.getdata())
    if not rgb:
        return _empty_region_stats()
    lab = rgb_to_lab_pixels(work, max_side=max(work.size))
    return _stats_from_rgb_lab(rgb, lab)


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
    {"id": 2, "row": 0, "col": 1, "name": "額頭", "organs": "額頭／心／咽喉／肺", "targets": ["heart", "lung"]},
    {"id": 3, "row": 0, "col": 2, "name": "右側面", "organs": "右臉", "targets": []},
    {"id": 4, "row": 1, "col": 0, "name": "左眼", "organs": "白睛／肝膽／肺", "targets": ["liver", "lung", "gallbladder"], "kind": "eye", "side": "left"},
    {"id": 5, "row": 1, "col": 1, "name": "眼", "organs": "肝", "targets": ["liver"], "kind": "eye"},
    {"id": 6, "row": 1, "col": 2, "name": "右眼", "organs": "白睛／肝膽／肺", "targets": ["liver", "lung", "gallbladder"], "kind": "eye", "side": "right"},
    {"id": 7, "row": 2, "col": 0, "name": "左頰", "organs": "顴／小腸／大腸", "targets": ["small_intestine", "large_intestine"], "kind": "cheek"},
    {"id": 8, "row": 2, "col": 1, "name": "鼻子", "organs": "鼻／脾胃／肺", "targets": ["spleen", "stomach", "lung"], "kind": "nose"},
    {"id": 9, "row": 2, "col": 2, "name": "右頰", "organs": "顴／小腸／大腸", "targets": ["small_intestine", "large_intestine"], "kind": "cheek"},
    {"id": 10, "row": 3, "col": 0, "name": "左下頜", "organs": "腎", "targets": ["kidney"]},
    {"id": 12, "row": 3, "col": 1, "name": "唇", "organs": "脾", "targets": ["spleen"], "kind": "lip"},
    {"id": 11, "row": 3, "col": 2, "name": "右下頜", "organs": "腎", "targets": ["kidney"]},
]
COMPLEXION_CELL_IDS = (1, 2, 3, 5, 7, 8, 9, 10, 11)
# Personal Lab baseline if no stored history: cells 1,2,3,5,7,8,9,10,12 (user spec; 11 is 下頜脾腎陽虛 probe, 4/6 eyes/side skipped).
FACE_LAB_BASELINE_IDS = (1, 2, 3, 5, 7, 8, 9, 10, 12)
COMPLEXION_EXCLUDED_IDS = (4, 6)
FACE_CELL_MAPPING = {
    "forehead_heart_fire": {"cell": 2, "name": "額頭", "note": "使用者「區塊3額頭心火」：本格以 cell 2 為額頭；cell 3 是右側面，不當作額頭"},
    "forehead_user_alt_block": 3,
    "nose_tip_stomach_fire": {"cell": 8, "half": "lower", "name": "鼻頭"},
    "nose_wing_damp": {"cell": 8, "half": "lower", "name": "鼻翼"},
    "cheek_yin_vacuity": {"cells": [7, 9], "name": "兩頰"},
    "chin_yang_vacuity": {"cells": [10, 11], "name": "下頜"},
    "lips_cold_stasis": {"cell": 12, "name": "唇"},
    "left_eye": {"cell": 4, "name": "左眼"},
    "right_eye": {"cell": 6, "name": "右眼", "note": "使用者區塊4、6為眼；第5格仍為兩眼之間／肝"},
}
EYE_SUBREGION_MAP = {
    "sclera": {"name": "白睛", "organs": "肺／肝膽", "box": {"left": 0.16, "top": 0.34, "right": 0.84, "bottom": 0.68}},
    "outer_canthus": {"name": "外眥／白睛外環", "organs": "心", "left_eye_box": {"left": 0.0, "top": 0.28, "right": 0.28, "bottom": 0.72}, "right_eye_box": {"left": 0.72, "top": 0.28, "right": 1.0, "bottom": 0.72}},
    "inner_canthus": {"name": "內眥", "organs": "心", "left_eye_box": {"left": 0.72, "top": 0.28, "right": 1.0, "bottom": 0.72}, "right_eye_box": {"left": 0.0, "top": 0.28, "right": 0.28, "bottom": 0.72}},
    "upper_lid": {"name": "上瞼／眶緣", "organs": "脾胃", "box": {"left": 0.0, "top": 0.0, "right": 1.0, "bottom": 0.26}},
    "lower_lid": {"name": "下瞼／眶緣", "organs": "脾胃", "box": {"left": 0.0, "top": 0.74, "right": 1.0, "bottom": 1.0}},
    "inner_lid_proxy": {"name": "瞼內（下瞼內1/3代理）", "organs": "脾", "left_eye_box": {"left": 0.62, "top": 0.74, "right": 1.0, "bottom": 1.0}, "right_eye_box": {"left": 0.0, "top": 0.74, "right": 0.38, "bottom": 1.0}},
}
FACE_LAB_THRESHOLDS = {
    "shi_re_dL": -1.5,
    "shi_re_da": 6.0,
    "xu_re_dL_min": -1.0,
    "xu_re_da_min": 3.5,
    "xu_re_da_max": 6.0,
    "shi_han_dL": -5.0,
    "shi_han_db": -4.0,
    "shi_han_da": -3.0,
    "xu_han_dL": 6.0,
    "xu_han_da": -3.0,
    "xu_han_db": -2.0,
    "damp_dL": -2.5,
    "damp_db": 5.0,
    "damp_dS": -0.04,
    "damp_uneven": 6.0,
    "sclera_heat_da": 6.0,
    "sclera_red_s": 0.32,
    "bloodshot_min": 0.025,
    "bloodshot_max": 0.42,
    "sclera_damp_db": 5.0,
    "sclera_damp_dL": -2.5,
    "sclera_vacuity_dL": 8.0,
    "sclera_a_abs": 4.0,
    "sclera_b_abs": 5.0,
    "canthus_heat_da": 7.0,
    "canthus_heat_s": 0.35,
    "canthus_vacuity_da": -4.0,
    "canthus_vacuity_dL": 4.0,
    "canthus_a_low": 8.0,
    "lid_damp_db": 5.0,
    "lid_damp_dL": -2.5,
    "inner_lid_dL": 6.0,
    "inner_lid_da": -4.0,
    "inner_lid_a_low": 8.0,
    "eye_min_pixels": 8,
}
TEACHING_NOTE = "教學示範，非中醫診斷"
DAMP_OVERLAY = "mositure.png"
FACE_NORMAL_LAB = {"L": 65.0, "a_star": 12.0, "b_star": 20.0, "hex": "#E2AC8A", "look": "紅黃隱隱，明潤含蓄"}
FACE_COLOR_CLASSES = (
    {
        "id": "normal",
        "label": "正常",
        "bias": "接近基本色",
        "api_pattern": "健康",
        "look": "紅黃隱隱，明潤含蓄",
        "hex": "#E2AC8A",
        "centroid": {"L": 65.0, "a_star": 12.0, "b_star": 20.0},
        "delta_e_typical": (0.0, 3.0),
        "overlay": None,
        "patterns": (),
        "damp_family": None,
    },
    {
        "id": "damp_heat",
        "label": "濕熱",
        "bias": "濕熱",
        "api_pattern": "濕熱證",
        "look": "黃而鮮明如橘，油垢毛孔粗",
        "hex": "#CFA060",
        "centroid": {"L": 58.5, "a_star": 16.0, "b_star": 29.0},
        "delta_e_typical": (8.0, 14.0),
        "overlay": DAMP_OVERLAY,
        "patterns": (("實證", 1.5), ("熱證", 1.2)),
        "damp_family": "濕熱",
    },
    {
        "id": "phlegm_damp",
        "label": "寒濕",
        "bias": "寒濕",
        "api_pattern": "寒濕證",
        "look": "黃而晦暗或晄白虛浮",
        "hex": "#A8906F",
        "centroid": {"L": 54.0, "a_star": 8.0, "b_star": 24.0},
        "delta_e_typical": (9.0, 15.0),
        "overlay": DAMP_OVERLAY,
        "patterns": (("實證", 1.4), ("寒證", 1.2)),
        "damp_family": "寒濕",
    },
    {
        "id": "excess_heat",
        "label": "實熱",
        "bias": "實熱",
        "api_pattern": "實證熱證",
        "look": "全臉充血純紅熱",
        "hex": "#C87058",
        "centroid": {"L": 57.5, "a_star": 21.5, "b_star": 20.0},
        "delta_e_typical": (8.0, 15.0),
        "overlay": "strong-hot.png",
        "patterns": (("實證", 1.6), ("熱證", 1.8)),
        "damp_family": None,
    },
    {
        "id": "vacuity_heat",
        "label": "虛熱",
        "bias": "虛熱",
        "api_pattern": "虛證熱證",
        "look": "底色白兩顴潮紅",
        "hex": "#EAB09E",
        "centroid": {"L": 65.5, "a_star": 18.0, "b_star": 16.5},
        "delta_e_typical": (4.0, 8.0),
        "overlay": "weak-hot.png",
        "patterns": (("虛證", 1.6), ("熱證", 1.8)),
        "damp_family": None,
    },
    {
        "id": "excess_cold",
        "label": "實寒",
        "bias": "實寒",
        "api_pattern": "實證寒證",
        "look": "青紫缺氧",
        "hex": "#A2938A",
        "centroid": {"L": 50.0, "a_star": 5.0, "b_star": 10.0},
        "delta_e_typical": (12.0, 20.0),
        "overlay": "strong-cold.png",
        "patterns": (("實證", 1.6), ("寒證", 1.8)),
        "damp_family": None,
    },
    {
        "id": "vacuity_cold",
        "label": "虛寒",
        "bias": "虛寒",
        "api_pattern": "虛證寒證",
        "look": "死白無華",
        "hex": "#F2D1BD",
        "centroid": {"L": 76.0, "a_star": 6.0, "b_star": 14.0},
        "delta_e_typical": (10.0, 16.0),
        "overlay": "weak-cold.png",
        "patterns": (("虛證", 1.6), ("寒證", 1.8)),
        "damp_family": None,
    },
)
TONGUE_BODY_NORMAL = {"L": 53.0, "a_star": 23.0, "b_star": 12.0, "hex": "#C86868", "look": "淡紅舌，紅潤適中"}
TONGUE_COAT_NORMAL = {"L": 70.0, "a_star": 4.0, "b_star": 8.0, "hex": "#D2C8C2", "look": "薄白苔，半透明白"}
TONGUE_MIRROR_COAT_MAX = 0.20
TONGUE_COATING_RATIO_DEF = "coating_ratio = coat_pixels / (body_pixels + coat_pixels)；舌面有苔比例，不含裁切空白"
TONGUE_CLASS_META = {
    "正常": {
        "bias": "接近正常",
        "api_pattern": "健康",
        "overlay": None,
        "patterns": (),
        "targets": (),
    },
    "實熱": {
        "bias": "實熱",
        "api_pattern": "實證熱證",
        "overlay": "strong-hot.png",
        "patterns": (("實證", 1.6), ("熱證", 1.8)),
        "targets": ("stomach", "large_intestine", "heart"),
    },
    "虛熱": {
        "bias": "虛熱",
        "api_pattern": "虛證熱證",
        "overlay": "weak-hot.png",
        "patterns": (("虛證", 1.6), ("熱證", 1.8)),
        "targets": ("heart", "kidney", "stomach"),
    },
    "實寒": {
        "bias": "實寒",
        "api_pattern": "實證寒證",
        "overlay": "strong-cold.png",
        "patterns": (("實證", 1.6), ("寒證", 1.8)),
        "targets": ("heart", "kidney", "stomach"),
    },
    "虛寒": {
        "bias": "虛寒",
        "api_pattern": "虛證寒證",
        "overlay": "weak-cold.png",
        "patterns": (("虛證", 1.6), ("寒證", 1.8)),
        "targets": ("spleen", "kidney"),
    },
    "濕症": {
        "bias": "濕症",
        "api_pattern": "濕氣較重",
        "overlay": DAMP_OVERLAY,
        "patterns": (("實證", 1.5),),
        "targets": ("stomach",),
    },
}
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
        "targets": ["large_intestine", "stomach"],
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


def compact_lab(stats: dict[str, float]) -> dict[str, float]:
    return {
        "L": round(stats.get("L", 0), 1),
        "a": round(stats.get("a_star", 0), 1),
        "b": round(stats.get("b_star", 0), 1),
        "L_median": round(stats.get("L_median", stats.get("L", 0)), 1),
        "a_median": round(stats.get("a_median", stats.get("a_star", 0)), 1),
        "b_median": round(stats.get("b_median", stats.get("b_star", 0)), 1),
    }


def format_lab(stats: dict[str, float]) -> str:
    lab = compact_lab(stats)
    return f"L{lab['L']:.0f} a{lab['a']:+.0f} b{lab['b']:+.0f}"


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
        "L",
        "a_star",
        "b_star",
        "L_median",
        "a_median",
        "b_median",
        "pixel_count",
    )
    n = float(len(items))
    return {key: sum(item.get(key, 0) for item in items) / n for key in keys}


# Face color photo vs the yellow guides. One cell is 1/4 of the analysis frame.
# Web captureFaceFrame and Android FaceFrame.cropVisibleZoom already move the
# face up by 1/4 of a cell and scale it to 0.9 before upload. crop_cell splits
# that image; do not shift or scale it again.
FACE_COLOR_SHIFT_CELLS = 0.25
FACE_COLOR_SCALE = 0.9


def crop_cell(image: Image.Image, row: int, col: int, half: str | None = None) -> Image.Image:
    """One cell of the 4×3 face grid. Rows are equal quarters of the uploaded face photo.

    That photo already has the face 1/4 cell higher than the yellow guides, at 0.9×.
    """
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
    work = image.convert("RGB")
    rgb_pixels = list(work.getdata())
    lab_pixels = rgb_to_lab_pixels(work, max_side=max(work.size) or 1)
    picked_rgb: list[tuple[int, int, int]] = []
    picked_lab: list[tuple[float, float, float]] = []
    for pix, lab in zip(rgb_pixels, lab_pixels):
        if pix[0] >= 90 and pix[0] >= pix[1] + 12 and pix[0] >= pix[2] + 12:
            picked_rgb.append(pix)
            picked_lab.append(lab)
    if len(picked_rgb) < 12:
        stats = region_stats(image)
        return (int(stats["r"]), int(stats["g"]), int(stats["b"])), stats
    stats = _stats_from_rgb_lab(picked_rgb, picked_lab)
    return (int(round(stats["r"])), int(round(stats["g"])), int(round(stats["b"]))), stats


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


def rgb_to_ycrcb(r: float, g: float, b: float) -> tuple[float, float, float]:
    """BT.601 YCbCr. Y carries skin depth; Cr/Cb stay comparable across skin tones."""
    y = 0.299 * r + 0.587 * g + 0.114 * b
    cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b
    cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b
    return y, cb, cr


def _chroma(cr: float, cb: float) -> float:
    return ((cr - 128) ** 2 + (cb - 128) ** 2) ** 0.5


def _ycrcb_reading(
    bias: str,
    meaning: str,
    overlay: str | None,
    patterns: tuple[tuple[str, float], ...],
    score: float,
    cr: float,
    cb: float,
    d_cr: float,
    d_cb: float,
    targets: list[str] | None = None,
) -> dict[str, Any]:
    reading = {
        "bias": bias,
        "meaning": meaning,
        "overlay": overlay,
        "patterns": patterns,
        "score": score,
        "reference": None,
        "source": "YCrCb",
        "cr": round(cr, 1),
        "cb": round(cb, 1),
        "d_cr": round(d_cr, 1),
        "d_cb": round(d_cb, 1),
    }
    if targets is not None:
        reading["targets"] = targets
    return reading


def classify_face_color(stats: dict[str, float], base: dict[str, float], kind: str) -> dict[str, Any]:
    """Cross-race face reading: compare Cr/Cb with this face's own baseline."""
    y, cb, cr = rgb_to_ycrcb(stats["r"], stats["g"], stats["b"])
    _by, base_cb, base_cr = rgb_to_ycrcb(base["r"], base["g"], base["b"])
    d_cr = cr - base_cr
    d_cb = cb - base_cb
    chroma = _chroma(cr, cb)
    base_chroma = _chroma(base_cr, base_cb)
    yellow = _color_scores(stats, base)["yellow"]

    heat = d_cr >= 12 and d_cb <= -6
    cold = d_cb >= 8 and d_cr <= 3
    empty = chroma <= 14 or (base_chroma >= 18 and chroma <= base_chroma - 12 and d_cr < 0 and d_cb > -4)
    # 虛熱 is a zygomatic spike against the rest of this face, even when the spike is strong.
    # 實熱 is a whole-face Cr surge, caught by the baseline when every cell moves together.
    cheek_heat = kind == "cheek" and d_cr >= 6 and d_cb < 4

    if kind == "eye":
        if heat or (d_cr >= 12 and d_cr >= d_cb):
            return _ycrcb_reading("實熱", "肝實熱（Cr 上升、皮下充血）", "strong-hot.png", (("實證", 1.6), ("熱證", 1.8)), d_cr, cr, cb, d_cr, d_cb)
        if cheek_heat or (6 <= d_cr < 12 and d_cb > -6):
            return _ycrcb_reading("虛熱", "肝虛熱（Cr 中度上升）", "weak-hot.png", (("虛證", 1.6), ("熱證", 1.8)), d_cr, cr, cb, d_cr, d_cb)
        if yellow >= 12:
            return _ycrcb_reading("較黃", "濕氣較重", DAMP_OVERLAY, (("實證", 1.4),), yellow, cr, cb, d_cr, d_cb)
        return _ycrcb_reading("白／黑", "眼色以白與黑為主", None, (), 0.0, cr, cb, d_cr, d_cb)

    if heat:
        meaning = "實熱（Cr 極高、Cb 極低）"
        targets = None
        if kind == "lip":
            meaning = "腸胃實熱（Cr 極高、Cb 極低）"
            targets = ["large_intestine", "stomach"]
        return _ycrcb_reading("實熱", meaning, "strong-hot.png", (("實證", 1.6), ("熱證", 1.8)), d_cr - d_cb, cr, cb, d_cr, d_cb, targets)
    if cold:
        meaning = "實寒（Cb 上升、Cr 被抑制）"
        targets = ["heart", "lung"] if kind == "lip" else None
        return _ycrcb_reading("實寒", meaning, "strong-cold.png", (("實證", 1.6), ("寒證", 1.8)), d_cb - d_cr, cr, cb, d_cr, d_cb, targets)
    if empty:
        meaning = "虛寒（Cr、Cb 同時偏低，血色不足）"
        targets = ["spleen"] if kind == "lip" else None
        return _ycrcb_reading("虛寒", meaning, "weak-cold.png", (("虛證", 1.6), ("寒證", 1.8)), base_chroma - chroma, cr, cb, d_cr, d_cb, targets)
    if cheek_heat or (kind == "lip" and 6 <= d_cr < 12 and d_cb > -6):
        meaning = "虛熱（顴部 Cr 中度上升）" if kind == "cheek" else "虛熱（Cr 中度上升）"
        targets = ["spleen"] if kind == "lip" else None
        return _ycrcb_reading("虛熱", meaning, "weak-hot.png", (("虛證", 1.6), ("熱證", 1.8)), d_cr, cr, cb, d_cr, d_cb, targets)
    if yellow >= 14:
        return _ycrcb_reading("較黃", "濕氣較重", DAMP_OVERLAY, (("實證", 1.4),), yellow, cr, cb, d_cr, d_cb)
    return _ycrcb_reading("接近基本色", "未見明顯色差", None, (), 0.0, cr, cb, d_cr, d_cb)


def baseline_ycrcb_pattern(base: dict[str, float]) -> dict[str, Any] | None:
    """Whole-face pattern from the baseline itself, so a uniformly flushed face still counts."""
    _y, cb, cr = rgb_to_ycrcb(base["r"], base["g"], base["b"])
    chroma = _chroma(cr, cb)
    if cr >= 165 and cb <= 112:
        return _ycrcb_reading(
            "實熱",
            "全臉實熱（Cr 異常高、Cb 低，不論膚色深淺）",
            "strong-hot.png",
            (("實證", 1.8), ("熱證", 2.0)),
            cr - cb,
            cr,
            cb,
            0.0,
            0.0,
            ["large_intestine", "spleen"],
        )
    if cb >= 126 and cr <= 158:
        return _ycrcb_reading(
            "實寒",
            "全臉實寒（Cb 上升、Cr 被抑制，面色青紫或暗沉）",
            "strong-cold.png",
            (("實證", 1.8), ("寒證", 2.0)),
            cb - cr,
            cr,
            cb,
            0.0,
            0.0,
            ["heart", "lung"],
        )
    if chroma <= 14:
        return _ycrcb_reading(
            "虛寒",
            "全臉虛寒（Cr 與 Cb 同時接近中性，血色不足）",
            "weak-cold.png",
            (("虛證", 1.8), ("寒證", 2.0)),
            14 - chroma,
            cr,
            cb,
            0.0,
            0.0,
            ["lung", "spleen"],
        )
    return None


def _std(values: list[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return (sum((value - mean) ** 2 for value in values) / len(values)) ** 0.5


def lab_uneven_score(image: Image.Image) -> float:
    width, height = image.size
    if width < 4 or height < 4:
        return 0.0
    parts = []
    for row in range(2):
        for col in range(2):
            crop = image.crop(
                (
                    int(col * width / 2),
                    int(row * height / 2),
                    int((col + 1) * width / 2),
                    int((row + 1) * height / 2),
                )
            )
            parts.append(region_stats(crop))
    return _std([p["L"] for p in parts]) + _std([p["b_star"] for p in parts]) + 40.0 * _std([p["s"] for p in parts])


def stats_from_personal_lab(personal: dict[str, Any]) -> dict[str, float]:
    stats = _empty_region_stats()
    stats["L"] = float(personal.get("L") or 0)
    stats["a_star"] = float(personal.get("a") if personal.get("a") is not None else personal.get("a_star") or 0)
    stats["b_star"] = float(personal.get("b") if personal.get("b") is not None else personal.get("b_star") or 0)
    sat = personal.get("S")
    if sat is None:
        sat = personal.get("s") or 0.0
    stats["s"] = float(sat)
    stats["L_median"] = stats["L"]
    stats["a_median"] = stats["a_star"]
    stats["b_median"] = stats["b_star"]
    return stats


def _lab_delta(cell: dict[str, float], base: dict[str, float]) -> dict[str, float]:
    return {
        "dL": cell.get("L", 0) - base.get("L", 0),
        "da": cell.get("a_star", 0) - base.get("a_star", 0),
        "db": cell.get("b_star", 0) - base.get("b_star", 0),
        "dS": cell.get("s", 0) - base.get("s", 0),
    }


def classify_face_lab(
    stats: dict[str, float],
    base: dict[str, float],
    kind: str,
    uneven: float = 0.0,
) -> dict[str, Any]:
    """CIELAB vs teaching normal L*65 a*12 b*20; eyes still vs personal/intra baseline."""
    t = FACE_LAB_THRESHOLDS
    ref = FACE_NORMAL_LAB if kind != "eye" else base
    d = _lab_delta(stats, ref)
    dL, da, db, dS = d["dL"], d["da"], d["db"], d["dS"]
    damp = dL <= t["damp_dL"] and db >= t["damp_db"] and (dS <= t["damp_dS"] or uneven >= t["damp_uneven"])
    shi_re = dL <= t["shi_re_dL"] and da >= t["shi_re_da"]
    xu_re = t["xu_re_dL_min"] <= dL and t["xu_re_da_min"] <= da < t["xu_re_da_max"]
    shi_han = dL <= t["shi_han_dL"] and (db <= t["shi_han_db"] or da <= t["shi_han_da"])
    xu_han = dL >= t["xu_han_dL"] and da <= t["xu_han_da"] and db <= t["xu_han_db"]

    def pack(bias: str, meaning: str, overlay: str | None, patterns: tuple[tuple[str, float], ...], score: float, targets: list[str] | None = None) -> dict[str, Any]:
        reading = {
            "bias": bias,
            "meaning": meaning,
            "overlay": overlay,
            "patterns": patterns,
            "score": score,
            "reference": None,
            "source": "CIELAB",
            "dL": round(dL, 1),
            "da": round(da, 1),
            "db": round(db, 1),
            "dS": round(dS, 3),
            "uneven": round(uneven, 1),
        }
        if targets is not None:
            reading["targets"] = targets
        return reading

    if kind == "eye":
        if shi_re or da >= t["shi_re_da"]:
            return pack("實熱", "肝實熱（a* 相對基準明顯上升）", "strong-hot.png", (("實證", 1.6), ("熱證", 1.8)), da)
        if damp:
            return pack("濕氣", "濕氣較重（b* 上升、明度下降）", DAMP_OVERLAY, (("實證", 1.4),), db)
        return pack("白／黑", "眼色以白與黑為主", None, (), 0.0)

    hit = nearest_face_class(stats)
    delta = lab_cie76(stats, FACE_NORMAL_LAB)
    health = delta_e_ref_health_score(delta, DELTA_E_REF)
    overlay = hit["overlay"] if health < 7 and hit["id"] != "normal" else None
    meaning = f"{hit['look']}（近 {hit['hex']}，ΔE* {delta:.1f} vs L*65 a*12 b*20）"
    return pack(hit["bias"], meaning, overlay, hit["patterns"] if overlay else (), delta)


def _eye_box(spec: dict[str, Any], side: str) -> dict[str, float]:
    if "box" in spec:
        return spec["box"]
    key = "left_eye_box" if side == "left" else "right_eye_box"
    return spec[key]


def _sclera_filtered_stats(image: Image.Image) -> tuple[dict[str, float], list[float], float, float]:
    work = _thumbnail_rgb(image, 100)
    rgb = list(work.getdata())
    lab = rgb_to_lab_pixels(work, max_side=max(work.size) or 1)
    picked_rgb: list[tuple[int, int, int]] = []
    picked_lab: list[tuple[float, float, float]] = []
    red_sats: list[float] = []
    for pix, lab_px in zip(rgb, lab):
        light, a_star, _b_star = lab_px
        _h, sat, val = rgb_to_hsv_pixel(*pix)
        if light >= 48 and val >= 0.32:
            picked_rgb.append(pix)
            picked_lab.append(lab_px)
            hue, sat, _v = rgb_to_hsv_pixel(*pix)
            if (hue <= 18 or hue >= 345) and sat >= FACE_LAB_THRESHOLDS["sclera_red_s"]:
                red_sats.append(sat)
    if len(picked_rgb) < FACE_LAB_THRESHOLDS["eye_min_pixels"]:
        stats = region_stats(image)
        return stats, [stats.get("a_star", 0)], 0.0, stats.get("s", 0)
    stats = _stats_from_rgb_lab(picked_rgb, picked_lab)
    a_vals = [item[1] for item in picked_lab]
    a_med = _median(a_vals)
    extra = FACE_LAB_THRESHOLDS["sclera_heat_da"]
    peaks = 0
    for pix, lab_px in zip(picked_rgb, picked_lab):
        hue, sat, _v = rgb_to_hsv_pixel(*pix)
        red = (hue <= 18 or hue >= 345) and sat >= FACE_LAB_THRESHOLDS["sclera_red_s"]
        if lab_px[1] >= a_med + extra or red:
            peaks += 1
    ratio = peaks / float(len(picked_lab))
    red_s = sum(red_sats) / len(red_sats) if red_sats else 0.0
    return stats, a_vals, ratio, red_s


def _subregion_pack(
    key: str,
    spec: dict[str, Any],
    stats: dict[str, float],
    reading: dict[str, Any],
    box: dict[str, float],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = {
        "id": key,
        "name": spec["name"],
        "organs": spec["organs"],
        "box": box,
        "hex": hex_from_stats(stats),
        "hsv": compact_hsv(stats),
        "lab": compact_lab(stats),
        "lab_text": format_lab(stats),
        "S": round(stats.get("s", 0), 3),
        "pixel_count": int(stats.get("pixel_count", 0)),
        "bias": reading.get("bias"),
        "meaning": reading.get("meaning"),
        "overlay": reading.get("overlay"),
        "dL": reading.get("dL"),
        "da": reading.get("da"),
        "db": reading.get("db"),
        "dS": reading.get("dS"),
        "uncertain": False,
    }
    if extra:
        item.update(extra)
    return item


def analyze_eye_subregions(
    crop: Image.Image,
    base: dict[str, float],
    side: str,
    cell_id: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    """Sclera / canthus / lids vs face baseline. Teaching demo."""
    t = FACE_LAB_THRESHOLDS
    notes: list[str] = []
    subregions: list[dict[str, Any]] = []
    best = {
        "bias": "白／黑",
        "meaning": "眼色以白與黑為主",
        "overlay": None,
        "patterns": (),
        "score": 0.0,
        "targets": [],
        "dL": 0,
        "da": 0,
        "db": 0,
        "dS": 0,
    }

    def consider(reading: dict[str, Any]) -> None:
        nonlocal best
        if (reading.get("score") or 0) > (best.get("score") or 0) and reading.get("overlay"):
            best = reading

    def delta_reading(
        stats: dict[str, float],
        bias: str,
        meaning: str,
        overlay: str | None,
        patterns: tuple[tuple[str, float], ...],
        score: float,
        targets: list[str],
    ) -> dict[str, Any]:
        d = _lab_delta(stats, base)
        return {
            "bias": bias,
            "meaning": meaning,
            "overlay": overlay,
            "patterns": patterns,
            "score": score,
            "targets": targets,
            "dL": round(d["dL"], 1),
            "da": round(d["da"], 1),
            "db": round(d["db"], 1),
            "dS": round(d["dS"], 3),
            "source": "CIELAB",
        }

    sclera_spec = EYE_SUBREGION_MAP["sclera"]
    sclera_box = _eye_box(sclera_spec, side)
    sclera_crop = crop_box(crop, sclera_box["left"], sclera_box["top"], sclera_box["right"], sclera_box["bottom"])
    sclera_stats, _a_vals, bloodshot, red_s = _sclera_filtered_stats(sclera_crop)
    d = _lab_delta(sclera_stats, base)
    linear = t["bloodshot_min"] <= bloodshot <= t["bloodshot_max"]
    red_hsv = red_s >= t["sclera_red_s"]
    if (d["da"] >= t["sclera_heat_da"] or red_hsv) and linear:
        sclera_read = delta_reading(
            sclera_stats,
            "實熱",
            "白睛血絲／a* 偏高 → 肺實熱",
            "strong-hot.png",
            (("實證", 1.6), ("熱證", 1.8)),
            d["da"] + bloodshot * 10,
            ["lung"],
        )
    elif d["db"] >= t["sclera_damp_db"] and d["dL"] <= t["sclera_damp_dL"]:
        sclera_read = delta_reading(
            sclera_stats,
            "濕氣",
            "白睛晦黃（b* 升、L* 降）→ 肝膽脾胃濕",
            DAMP_OVERLAY,
            (("實證", 1.5),),
            d["db"] - d["dL"],
            ["liver", "gallbladder", "spleen"],
        )
    elif (
        d["dL"] >= t["sclera_vacuity_dL"]
        and abs(sclera_stats.get("a_star", 0)) <= t["sclera_a_abs"]
        and (abs(sclera_stats.get("b_star", 0)) <= t["sclera_b_abs"] or sclera_stats.get("b_star", 0) <= 0)
    ):
        sclera_read = delta_reading(
            sclera_stats,
            "虛寒",
            "白睛淡青白（L* 高、a*／b* 近 0）→ 肺虛寒",
            "weak-cold.png",
            (("虛證", 1.6), ("寒證", 1.6)),
            d["dL"],
            ["lung"],
        )
    else:
        sclera_read = delta_reading(sclera_stats, "白／黑", "白睛未見明顯紅黃偏色", None, (), 0.0, [])
    subregions.append(
        _subregion_pack(
            "sclera",
            sclera_spec,
            sclera_stats,
            sclera_read,
            sclera_box,
            {"bloodshot_ratio": round(bloodshot, 3), "red_S": round(red_s, 3), "linear_red": linear},
        )
    )
    consider(sclera_read)
    if sclera_read.get("overlay"):
        notes.append(f"第{cell_id}格白睛 → {sclera_read['meaning']}（{TEACHING_NOTE}）")

    for key in ("outer_canthus", "inner_canthus"):
        spec = EYE_SUBREGION_MAP[key]
        box = _eye_box(spec, side)
        part = crop_box(crop, box["left"], box["top"], box["right"], box["bottom"])
        stats = region_stats(part)
        d = _lab_delta(stats, base)
        sat = stats.get("s", 0)
        if d["da"] >= t["canthus_heat_da"] and sat >= t["canthus_heat_s"]:
            reading = delta_reading(
                stats,
                "實熱",
                "眼眥 a* 與紅飽和偏高 → 心實熱",
                "strong-hot.png",
                (("實證", 1.4), ("熱證", 1.8)),
                d["da"],
                ["heart"],
            )
        elif d["da"] <= t["canthus_vacuity_da"] and d["dL"] >= t["canthus_vacuity_dL"] and stats.get("a_star", 0) <= t["canthus_a_low"]:
            reading = delta_reading(
                stats,
                "虛寒",
                "眼眥淡白（L* 高、a* 近 0）→ 心虛寒",
                "weak-cold.png",
                (("虛證", 1.6), ("寒證", 1.4)),
                d["dL"],
                ["heart"],
            )
        else:
            reading = delta_reading(stats, "中性", "眼眥未見明顯紅白偏色", None, (), 0.0, [])
        extra = {"ring": key == "outer_canthus"}
        subregions.append(_subregion_pack(key, spec, stats, reading, box, extra))
        consider(reading)
        if reading.get("overlay"):
            notes.append(f"第{cell_id}格{spec['name']} → {reading['meaning']}（{TEACHING_NOTE}）")

    for key in ("upper_lid", "lower_lid"):
        spec = EYE_SUBREGION_MAP[key]
        box = _eye_box(spec, side)
        part = crop_box(crop, box["left"], box["top"], box["right"], box["bottom"])
        stats = region_stats(part)
        d = _lab_delta(stats, base)
        if d["db"] >= t["lid_damp_db"] and d["dL"] <= t["lid_damp_dL"]:
            reading = delta_reading(
                stats,
                "濕氣",
                f"{spec['name']}晦黃黏滯（b* 升、L* 降）→ 脾胃濕",
                DAMP_OVERLAY,
                (("實證", 1.5),),
                d["db"] - d["dL"],
                ["spleen"],
            )
        else:
            reading = delta_reading(stats, "中性", f"{spec['name']}未見晦黃", None, (), 0.0, [])
        subregions.append(_subregion_pack(key, spec, stats, reading, box))
        consider(reading)
        if reading.get("overlay"):
            notes.append(f"第{cell_id}格{spec['name']} → {reading['meaning']}（{TEACHING_NOTE}）")

    proxy_spec = EYE_SUBREGION_MAP["inner_lid_proxy"]
    proxy_box = _eye_box(proxy_spec, side)
    proxy_crop = crop_box(crop, proxy_box["left"], proxy_box["top"], proxy_box["right"], proxy_box["bottom"])
    proxy_stats = region_stats(proxy_crop)
    d = _lab_delta(proxy_stats, base)
    sclera_L = sclera_stats.get("L", 0)
    looks_like_sclera = abs(proxy_stats.get("L", 0) - sclera_L) <= 4 and abs(proxy_stats.get("a_star", 0) - sclera_stats.get("a_star", 0)) <= 3
    too_few = proxy_stats.get("pixel_count", 0) < t["eye_min_pixels"]
    uncertain = too_few or looks_like_sclera
    if uncertain:
        reading = delta_reading(
            proxy_stats,
            "不確定",
            "瞼內未清楚入鏡，以下瞼內側三分之一代理（不確定）",
            None,
            (),
            0.0,
            [],
        )
    elif d["dL"] >= t["inner_lid_dL"] and d["da"] <= t["inner_lid_da"] and proxy_stats.get("a_star", 0) <= t["inner_lid_a_low"]:
        reading = delta_reading(
            proxy_stats,
            "虛寒",
            "瞼內淡白無血色 → 脾虛寒",
            "weak-cold.png",
            (("虛證", 1.8), ("寒證", 1.4)),
            d["dL"],
            ["spleen"],
        )
    else:
        reading = delta_reading(proxy_stats, "中性", "瞼內未見枯白", None, (), 0.0, [])
    subregions.append(
        _subregion_pack("inner_lid_proxy", proxy_spec, proxy_stats, reading, proxy_box, {"uncertain": uncertain, "proxy": True})
    )
    consider(reading)
    if reading.get("overlay"):
        notes.append(f"第{cell_id}格瞼內代理 → {reading['meaning']}（{TEACHING_NOTE}）")
    elif uncertain:
        notes.append(f"第{cell_id}格瞼內未清楚入鏡，已用下瞼內側代理（不確定）（{TEACHING_NOTE}）")

    return subregions, best, notes


def analyze_face_grid(
    image: Image.Image,
    personal_lab: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str], dict[str, str | None]]:
    findings: list[str] = []
    cells: list[dict[str, Any]] = []
    flags: list[dict[str, Any]] = []
    stats_by_id: dict[int, dict[str, float]] = {}
    crops: dict[int, Image.Image] = {}

    for spec in FACE_CELL_LAYOUT:
        crop = crop_cell(image, spec["row"], spec["col"])
        crops[spec["id"]] = crop
        stats_by_id[spec["id"]] = region_stats(crop)

    intra_stats = average_stats([stats_by_id[i] for i in FACE_LAB_BASELINE_IDS if i in stats_by_id])
    complexion_stats = average_stats([stats_by_id[i] for i in COMPLEXION_CELL_IDS if i in stats_by_id])
    cheek_base = average_stats(
        [stats_by_id[i] for i in COMPLEXION_CELL_IDS if i not in (7, 9) and i in stats_by_id]
    )
    if personal_lab and personal_lab.get("L") is not None:
        lab_base = stats_from_personal_lab(personal_lab)
        base_source = "personal_stored"
    else:
        lab_base = intra_stats
        base_source = "intra_face_mean_1_2_3_5_7_8_9_10_12"
    base_hex = hex_from_stats(complexion_stats)
    _base_y, base_cb, base_cr = rgb_to_ycrcb(complexion_stats["r"], complexion_stats["g"], complexion_stats["b"])
    c_text = (
        f"教學正常值 L*65 a*12 b*20 #E2AC8A（紅黃隱隱）。本圖平均 {base_hex}，"
        f"Cr {base_cr:.1f}、Cb {base_cb:.1f}。臉色分數 ΔE*/20 → 1–10（7–10 健康）（{TEACHING_NOTE}）"
    )
    findings.append(c_text)

    best_overlay: dict[str, tuple[float, str, tuple[tuple[str, float], ...]]] = {}
    face_blocks: list[dict[str, Any]] = []

    def remember(targets: list[str], reading: dict[str, Any]) -> None:
        overlay = reading.get("overlay")
        if not overlay:
            return
        for organ in targets:
            previous = best_overlay.get(organ)
            if previous is None or reading["score"] > previous[0]:
                best_overlay[organ] = (reading["score"], overlay, reading["patterns"])

    def read_cell(stats: dict[str, float], base: dict[str, float], kind: str, crop: Image.Image) -> dict[str, Any]:
        ycrcb_kind = "face" if kind == "nose" else kind
        ycrcb_base = cheek_base if ycrcb_kind == "cheek" else complexion_stats
        reading = classify_face_color(stats, ycrcb_base, ycrcb_kind)
        lab = classify_face_lab(stats, base, kind, lab_uneven_score(crop))
        reading["dL"] = lab.get("dL")
        reading["da"] = lab.get("da")
        reading["db"] = lab.get("db")
        reading["dS"] = lab.get("dS")
        reading["uneven"] = lab.get("uneven")
        return reading

    lip_color = None
    for spec in FACE_CELL_LAYOUT:
        cell_id = spec["id"]
        kind = spec.get("kind") or "face"
        split = None
        subregions = None
        if kind == "lip":
            _rgb, stats = reddish_lip_rgb(crops[cell_id])
            stats_by_id[cell_id] = stats
            reading = read_cell(stats, lab_base, "lip", crops[cell_id])
            if reading["bias"] == "實熱":
                reading["meaning"] = "腸胃實熱（Cr 極高、Cb 極低）"
                reading["targets"] = ["large_intestine", "stomach"]
            elif reading["bias"] == "實寒":
                reading["meaning"] = "心和肺實寒（Cb 上升、Cr 被抑制）"
                reading["targets"] = ["heart", "lung"]
            elif reading["bias"] == "虛熱":
                reading["targets"] = ["spleen"]
            elif reading["bias"] == "虛寒":
                reading["targets"] = ["spleen"]
            lip_color = f"唇{reading['meaning']}"
            targets = reading.get("targets") or (spec["targets"] if reading.get("overlay") else [])
            lip_organs = list(targets or spec["targets"] or ["spleen"])
            if "spleen" in lip_organs and "stomach" in lip_organs:
                drop = "spleen" if reading.get("bias") == "實熱" else "stomach"
                lip_organs = [organ for organ in lip_organs if organ != drop]
            face_blocks.append(make_face_block(f"face-{cell_id}", stats, lip_organs))
        elif kind == "nose":
            upper_crop = crop_cell(image, spec["row"], spec["col"], "upper")
            lower_crop = crop_cell(image, spec["row"], spec["col"], "lower")
            upper_stats = region_stats(upper_crop)
            lower_stats = region_stats(lower_crop)
            stats_by_id[cell_id] = lower_stats
            stats = lower_stats
            upper_read = read_cell(upper_stats, lab_base, "face", upper_crop)
            lower_read = read_cell(lower_stats, lab_base, "face", lower_crop)
            if lower_read["bias"] == "實熱":
                lower_read["meaning"] = "鼻頭實熱 → 胃火"
                lower_read["targets"] = ["stomach"]
            elif lower_read["bias"] == "濕氣":
                lower_read["meaning"] = "鼻翼濕氣 → 脾胃濕證"
                lower_read["targets"] = ["spleen"]
            reading = lower_read if (lower_read.get("score") or 0) >= (upper_read.get("score") or 0) else upper_read
            targets = reading.get("targets") or (spec["targets"] if reading.get("overlay") else [])
            split = [
                {
                    "part": "upper",
                    "organs": "鼻上／肺",
                    "hex": hex_from_stats(upper_stats),
                    "lab": compact_lab(upper_stats),
                    "bias": upper_read["bias"],
                    "meaning": upper_read["meaning"],
                    "overlay": upper_read.get("overlay"),
                },
                {
                    "part": "lower",
                    "organs": "鼻頭／脾胃",
                    "hex": hex_from_stats(lower_stats),
                    "lab": compact_lab(lower_stats),
                    "bias": lower_read["bias"],
                    "meaning": lower_read["meaning"],
                    "overlay": lower_read.get("overlay"),
                },
            ]
            remember(upper_read.get("targets") or (["lung"] if upper_read.get("overlay") else []), upper_read)
            lower_targets = list(lower_read.get("targets") or [])
            if not lower_targets and lower_read.get("overlay"):
                lower_targets = ["stomach"] if lower_read.get("bias") == "實熱" else ["spleen"]
            if "spleen" in lower_targets and "stomach" in lower_targets:
                drop = "spleen" if lower_read.get("bias") == "實熱" else "stomach"
                lower_targets = [organ for organ in lower_targets if organ != drop]
            lower_read["targets"] = lower_targets
            if reading is lower_read:
                targets = list(lower_targets) if lower_read.get("overlay") else []
            else:
                targets = list(upper_read.get("targets") or (["lung"] if upper_read.get("overlay") else []))
            remember(lower_targets, lower_read)
            face_blocks.append(make_face_block(f"face-{cell_id}-upper", upper_stats, organs_from_zh("鼻上／肺") or ["lung"]))
            face_blocks.append(make_face_block(f"face-{cell_id}-lower", lower_stats, lower_targets or ["spleen"]))
        elif kind == "eye" and spec.get("side") in ("left", "right"):
            stats = stats_by_id[cell_id]
            subregions, reading, eye_notes = analyze_eye_subregions(crops[cell_id], lab_base, spec["side"], cell_id)
            findings.extend(eye_notes)
            targets = list(reading.get("targets") or [])
            for part in subregions:
                overlay = part.get("overlay")
                if not overlay:
                    continue
                organ_names = {"肺": "lung", "肝": "liver", "膽": "gallbladder", "脾": "spleen", "胃": "stomach", "心": "heart"}
                organs = []
                for token in part["organs"].replace("／", "、").split("、"):
                    for zh, key in organ_names.items():
                        if zh in token and key not in organs:
                            organs.append(key)
                if "spleen" in organs and "stomach" in organs:
                    organs = [organ for organ in organs if organ != "stomach"]
                fake = {
                    "overlay": overlay,
                    "patterns": (("熱證", 1.4),) if part["bias"] == "實熱" else (("虛證", 1.4), ("寒證", 1.2)) if part["bias"] == "虛寒" else (("實證", 1.4),),
                    "score": abs(part.get("da") or part.get("db") or part.get("dL") or 4),
                }
                if part["bias"] == "濕氣":
                    fake["overlay"] = DAMP_OVERLAY
                    fake["patterns"] = (("實證", 1.5),)
                remember(organs, fake)
                if not part.get("uncertain"):
                    face_blocks.append(
                        {
                            "label": f"face-{cell_id}-{part.get('id')}",
                            "organs": organs,
                            "delta_e": round(lab_cie76(part.get("lab") or {}, lab_base), 2),
                            "class_label": part.get("bias"),
                            "api_pattern": part.get("bias"),
                        }
                    )
        else:
            stats = stats_by_id[cell_id]
            base = cheek_base if kind == "cheek" else lab_base
            reading = read_cell(stats, base, kind, crops[cell_id])
            face_blocks.append(make_face_block(f"face-{cell_id}", stats, spec["targets"] or []))
            if cell_id == 2 and reading["bias"] == "實熱":
                reading["meaning"] = "額頭實熱 → 心火（區塊對應第2格；使用者所稱區塊3為本格右側面）"
                reading["targets"] = ["heart"]
            targets = reading.get("targets") or (spec["targets"] if reading.get("overlay") else [])

        lab_stats = stats_by_id[cell_id]
        interpretation = (
            f"第{cell_id}格{spec['name']}（{spec['organs']}）{hex_from_stats(lab_stats)} "
            f"Cr {reading.get('cr')} Cb {reading.get('cb')}（ΔCr {reading.get('d_cr')} ΔCb {reading.get('d_cb')}）"
            f" → {reading['meaning']}（{TEACHING_NOTE}）"
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
                "hex": hex_from_stats(lab_stats),
                "hsv": compact_hsv(lab_stats),
                "lab": compact_lab(lab_stats),
                "lab_text": format_lab(lab_stats),
                "bias": reading["bias"],
                "meaning": reading["meaning"],
                "reading": f"{reading['bias']} → {reading['meaning']}",
                "interpretation": interpretation,
                "overlay": reading.get("overlay"),
                "dL": reading.get("dL"),
                "da": reading.get("da"),
                "db": reading.get("db"),
                "dS": reading.get("dS"),
                "split": split,
                "subregions": subregions if kind == "eye" and spec.get("side") else None,
            }
        )

    by_id = {cell["id"]: cell for cell in cells}
    color_health = apply_relative_color_scores(face_blocks)
    score_by_label = {block["label"]: block for block in face_blocks}

    def attach_face_health(cell: dict[str, Any]) -> None:
        whole = score_by_label.get(f"face-{cell['id']}")
        if whole:
            cell["delta_e"] = whole["delta_e"]
            cell["health_score"] = whole["health_score"]
            cell["class_label"] = whole.get("class_label")
            cell["api_pattern"] = whole.get("api_pattern")
        for part in cell.get("split") or []:
            item = score_by_label.get(f"face-{cell['id']}-{part.get('part')}")
            if item:
                part["delta_e"] = item["delta_e"]
                part["health_score"] = item["health_score"]
                part["class_label"] = item.get("class_label")
        for part in cell.get("subregions") or []:
            item = score_by_label.get(f"face-{cell['id']}-{part.get('id')}")
            if item:
                part["delta_e"] = item["delta_e"]
                part["health_score"] = item["health_score"]
        extras = [
            part.get("health_score")
            for part in (cell.get("split") or []) + (cell.get("subregions") or [])
            if part.get("health_score") is not None
        ]
        if cell.get("health_score") is None and extras:
            cell["health_score"] = min(extras)

    for cell in cells:
        attach_face_health(cell)

    def bias_of(cell_id: int, half: str | None = None) -> str:
        cell = by_id.get(cell_id) or {}
        if half and cell.get("split"):
            for part in cell["split"]:
                if part["part"] == half:
                    return part.get("bias") or ""
        return cell.get("bias") or ""

    nose_lower = bias_of(8, "lower")
    if nose_lower == "實熱":
        flags.append({"id": "stomach_fire", "cells": [8], "half": "lower", "pattern": "實熱", "text": "鼻頭實熱 → 胃火"})
        remember(["stomach"], {"overlay": "strong-hot.png", "patterns": (("實證", 1.6), ("熱證", 2.0)), "score": 9.0})
        findings.append(f"鼻頭（第8格下段）實熱 → 胃火（{TEACHING_NOTE}）")
    if bias_of(2) == "實熱":
        flags.append({"id": "heart_fire_forehead", "cells": [2], "pattern": "實熱", "text": "額頭（第2格）實熱 → 心火"})
        remember(["heart"], {"overlay": "strong-hot.png", "patterns": (("實證", 1.6), ("熱證", 2.0)), "score": 9.0})
        findings.append(f"額頭（第2格，非第3格右臉）實熱 → 心火（{TEACHING_NOTE}）")
    if bias_of(7) == "虛熱" and bias_of(9) == "虛熱":
        flags.append({"id": "liver_kidney_yin", "cells": [7, 9], "pattern": "虛熱", "text": "兩頰嫩紅 → 肝腎陰虛"})
        remember(["liver", "kidney"], {"overlay": "weak-hot.png", "patterns": (("虛證", 1.8), ("熱證", 1.6)), "score": 8.0})
        findings.append(f"第7、9格兩頰孤立嫩紅 → 肝腎陰虛（{TEACHING_NOTE}）")
    if bias_of(12) == "實寒" or sum(1 for cid in (1, 2, 3, 7, 8, 9, 10, 11, 12) if bias_of(cid) == "實寒") >= 4:
        flags.append({"id": "cold_stasis", "cells": [12], "pattern": "實寒", "text": "唇或滿面青黑 → 寒凝"})
        remember(["heart", "kidney"], {"overlay": "strong-cold.png", "patterns": (("實證", 1.6), ("寒證", 1.8)), "score": 8.0})
        findings.append(f"唇或滿面青黑實寒 → 寒凝（{TEACHING_NOTE}）")
    if bias_of(10) == "虛寒" and bias_of(11) == "虛寒":
        flags.append({"id": "spleen_kidney_yang", "cells": [10, 11], "pattern": "虛寒", "text": "下頜枯白 → 脾腎陽虛"})
        remember(["spleen", "kidney"], {"overlay": "weak-cold.png", "patterns": (("虛證", 1.8), ("寒證", 1.6)), "score": 8.0})
        findings.append(f"第10、11格下頜枯白 → 脾腎陽虛（{TEACHING_NOTE}）")
    damp_names = ("濕氣", "濕熱", "寒濕")
    if nose_lower in damp_names and bias_of(7) in damp_names and bias_of(9) in damp_names:
        flags.append({"id": "spleen_damp", "cells": [7, 8, 9], "half": "lower", "pattern": "濕氣", "text": "鼻翼與兩頰晦黃低飽和 → 脾胃濕證"})
        remember(["spleen"], {"overlay": DAMP_OVERLAY, "patterns": (("實證", 1.8),), "score": 9.0})
        findings.append(f"鼻翼（第8格下）與第7、9格晦黃低S → 脾胃濕證（{TEACHING_NOTE}）")

    def sub_bias(cell_id: int, sub_id: str) -> str:
        for part in (by_id.get(cell_id) or {}).get("subregions") or []:
            if part.get("id") == sub_id:
                return part.get("bias") or ""
        return ""

    if any(sub_bias(cid, "sclera") == "實熱" for cid in (4, 6)):
        flags.append({"id": "eye_lung_heat", "cells": [4, 6], "subregion": "sclera", "pattern": "實熱", "text": "白睛血絲／a* 偏高 → 肺實熱"})
    if any(sub_bias(cid, "sclera") == "濕氣" for cid in (4, 6)):
        flags.append({"id": "eye_damp_yellow", "cells": [4, 6], "subregion": "sclera", "pattern": "濕氣", "text": "白睛晦黃 → 肝膽脾胃濕"})
    if any(sub_bias(cid, "sclera") == "虛寒" for cid in (4, 6)):
        flags.append({"id": "eye_lung_vacuity", "cells": [4, 6], "subregion": "sclera", "pattern": "虛寒", "text": "白睛淡青白 → 肺虛寒"})
    if any(sub_bias(cid, "outer_canthus") == "實熱" or sub_bias(cid, "inner_canthus") == "實熱" for cid in (4, 6)):
        flags.append({"id": "canthus_heart_heat", "cells": [4, 6], "subregion": "outer_canthus", "pattern": "實熱", "text": "眼眥紅 → 心實熱"})
    if any(sub_bias(cid, "outer_canthus") == "虛寒" or sub_bias(cid, "inner_canthus") == "虛寒" for cid in (4, 6)):
        flags.append({"id": "canthus_heart_vacuity", "cells": [4, 6], "subregion": "outer_canthus", "pattern": "虛寒", "text": "眼眥淡白 → 心虛寒"})
    if any(sub_bias(cid, "upper_lid") == "濕氣" or sub_bias(cid, "lower_lid") == "濕氣" for cid in (4, 6)):
        flags.append({"id": "lid_spleen_damp", "cells": [4, 6], "subregion": "lower_lid", "pattern": "濕氣", "text": "眼瞼眶緣晦黃 → 脾胃濕"})
    if any(sub_bias(cid, "inner_lid_proxy") == "虛寒" for cid in (4, 6)):
        flags.append({"id": "inner_lid_spleen_vacuity", "cells": [4, 6], "subregion": "inner_lid_proxy", "pattern": "虛寒", "text": "瞼內淡白 → 脾虛寒"})

    overall = baseline_ycrcb_pattern(complexion_stats)
    if overall:
        findings.append(overall["meaning"] + f"（{TEACHING_NOTE}）")
        remember(overall.get("targets") or [], overall)
    else:
        overall = {"bias": "基本色", "overlay": None, "meaning": "未見全臉色偏"}

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
            "lab": cell.get("lab"),
            "bias": cell["bias"],
            "meaning": cell.get("meaning"),
            "reading": cell.get("reading"),
            "delta_e": cell.get("delta_e"),
            "health_score": cell.get("health_score"),
        }
        for cell in cells
    ]
    complexion_hsv = compact_hsv(intra_stats)
    complexion_lab = compact_lab(intra_stats)
    measurements.append(
        {
            "cell_id": 0,
            "part": "complexion",
            "name": "基本色",
            "organs": "1,2,3,5,7,8,9,10,11",
            "hex": base_hex,
            "hsv": complexion_hsv,
            "lab": complexion_lab,
            "bias": "基本色",
            "meaning": "各區 YCrCb 的比較基準",
            "reading": c_text,
        }
    )
    face_grid = {
        "rows": 4,
        "cols": 3,
        "layout": "4x3",
        "numbering": "row4 visual 10 | 12 lips | 11",
        "cell_mapping": FACE_CELL_MAPPING,
        "cells": cells,
        "measurements": measurements,
        "marks": marks,
        "flags": flags,
        "organ_overlays": organ_overlays,
        "complexion": {
            "hex": base_hex,
            "hsv": complexion_hsv,
            "lab": complexion_lab,
            "S": round(intra_stats.get("s", 0), 3),
            "baseline_lab": compact_lab(lab_base),
            "bias": overall.get("bias") if overall.get("overlay") else "基本色",
            "pattern": overall.get("bias") if overall.get("overlay") else "色差基準",
            "interpretation": c_text,
            "included_cells": list(COMPLEXION_CELL_IDS),
            "excluded_cells": list(COMPLEXION_EXCLUDED_IDS),
            "baseline_source": base_source,
            "teaching_normal": {**FACE_NORMAL_LAB, "classes": [
                {"id": spec["id"], "label": spec["label"], "hex": spec["hex"], "centroid": spec["centroid"]}
                for spec in FACE_COLOR_CLASSES
            ]},
            "thresholds": FACE_LAB_THRESHOLDS,
        },
        "color_health": color_health,
        "disclaimer": TEACHING_NOTE,
    }
    return face_grid, findings, colors


# Photo orientation: tongue tip toward BOTTOM (lips), root toward TOP.
# User listed 上中下左右 (5). The 6th layer is whole-tongue coating overlay,
# not a sixth spatial tile (中 is not split into 中上/中下).
# Equal height 0.28. 左右 share 中. 上 spans the outer edges of 左右.
# The stack is shifted up by half a cell (0.14) from 上's previous top 0.22.
TONGUE_ZONE_LAYOUT = [
    {"id": "top", "label": "上", "organs": "腎", "anatomy": "舌根", "left": 0.02, "top": 0.08, "right": 0.98, "bottom": 0.36},
    {"id": "center", "label": "中", "organs": "脾胃", "anatomy": "舌中", "left": 0.28, "top": 0.36, "right": 0.72, "bottom": 0.64},
    {"id": "bottom", "label": "下", "organs": "心肺", "anatomy": "舌尖", "left": 0.22, "top": 0.64, "right": 0.78, "bottom": 0.92},
    {"id": "left", "label": "左", "organs": "肝膽", "anatomy": "舌左邊", "left": 0.02, "top": 0.36, "right": 0.28, "bottom": 0.64},
    {"id": "right", "label": "右", "organs": "肝膽", "anatomy": "舌右邊", "left": 0.72, "top": 0.36, "right": 0.98, "bottom": 0.64},
]
TONGUE_COAT_BOX = {"left": 0.24, "top": 0.16, "right": 0.76, "bottom": 0.74}
TONGUE_SIXTH_NOTE = "使用者列上中下左右五塊；第六層為全舌舌苔疊加（非再切一塊空間）。中區不拆中上／中下。"
TONGUE_TIP_HEAT_FLAG = "心肺區偏紅，提示心火偏旺"
TONGUE_ZONE_TARGETS = {
    "top": ("kidney",),
    "center": ("spleen",),
    "bottom": ("heart", "lung"),
    "left": ("liver", "gallbladder"),
    "right": ("liver", "gallbladder"),
}
# Intra-image relative Lab/HSV teaching thresholds (CIELAB units unless noted).
TONGUE_LAB_THRESHOLDS = {
    "baseline": "whole_tongue_median_Lab; tip also vs mid-zone; center coat vs non-center peers",
    "tip_heat_da_vs_center": 4.0,
    "tip_heat_da_vs_baseline": 3.0,
    "tip_speckle_da_vs_tip_median": 8.0,
    "tip_speckle_min_ratio": 0.02,
    "tip_speckle_max_ratio": 0.22,
    "tip_vacuity_dL_vs_baseline": 8.0,
    "tip_vacuity_da_vs_baseline": -4.0,
    "center_cold_abs_b": 8.0,
    "center_cold_db_vs_peer": 1.5,
    "center_cold_dL_vs_peer": 4.0,
    "center_cold_s_max": 0.22,
    "center_heat_db_vs_peer": 6.0,
    "center_scorch_dL_vs_peer": -5.0,
    "body_red_da": 4.0,
    # Normal tongue pink is #FFB6C1 (a*~28) through #F2B2B7 (a*~25) and #E88B95 (a*~37).
    # 偏紅 starts past that flesh-red end, so a red hue alone is not heat.
    "body_heat_a_min": 41.0,
    "body_heat_red_ratio": 0.45,
    "body_pale_da": -4.0,
    "body_stasis_db": -6.0,
    "coat_yellow_db": 5.0,
    "delta_a_tip_minus_center": 4.0,
    "side_heat_da_vs_center": 4.0,
    "side_purple_db_vs_center": -3.5,
    "side_pale_da_vs_center": -4.0,
    "side_thin_aspect": 0.52,
    "root_peel_coat_max": 0.18,
    "root_peel_coat_gap": 0.20,
    "root_yin_da": 8.0,
    "root_yin_a_min": 40.0,
    "root_yin_dL_gap": 8.0,
    "root_thick_coat_min": 0.55,
    "root_yang_coat_s_max": 0.28,
    "root_yang_coat_b_max": 16.0,
    "root_yang_dL_vs_center": 6.0,
    "root_yang_da_vs_center": -4.0,
    "coat_yellow_b": 18.0,
    "coat_scorch_b": 28.0,
    "coat_yellow_L_low": 58.0,
    "coat_yellow_L_high": 78.0,
    "coat_white_b": 10.0,
    "coat_white_L": 72.0,
    "coat_mirror_a": 28.0,
    "coat_mirror_ratio_max": 0.12,
    "coat_thick_energy": 0.35,
    "coat_smooth_energy": 0.55,
    "coat_crack_contrast": 9.0,
    "coat_greasy_highlight_max": 0.03,
    "coat_slip_highlight_min": 0.04,
    "coat_mirror_highlight_min": 0.03,
    "seg_white_s_rel": 0.85,
    "seg_white_s_cap": 0.20,
    "seg_yellow_db": 6.0,
    "seg_yellow_dL_floor": -8.0,
    "seg_body_da": 6.0,
    "seg_body_s_min": 0.28,
    "morph_kernel": 3,
    "min_mask_pixels": 8,
}


def _channel_pack(stats: dict[str, float]) -> dict[str, Any]:
    hsv = compact_hsv(stats)
    return {
        "hex": hex_from_stats(stats),
        "hsv": hsv,
        "lab": compact_lab(stats),
        "S": hsv["saturation"],
        "pixel_count": int(stats.get("pixel_count", 0)),
    }


def tongue_body_reading(stats: dict[str, float]) -> tuple[str, str]:
    a_star = float(stats.get("a_star") or 0)
    past_flesh = a_star >= TONGUE_LAB_THRESHOLDS["body_heat_a_min"]
    if past_flesh and stats["red_ratio"] > TONGUE_LAB_THRESHOLDS["body_heat_red_ratio"]:
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


def tongue_body_from_lab(stats: dict[str, float], baseline: dict[str, float]) -> tuple[str, str]:
    if stats.get("pixel_count", 0) < TONGUE_LAB_THRESHOLDS["min_mask_pixels"]:
        return tongue_body_reading(stats) if stats.get("pixel_count", 0) else ("中性", "舌質像素不足")
    da = stats["a_star"] - baseline["a_star"]
    db = stats["b_star"] - baseline["b_star"]
    dL = stats["L"] - baseline["L"]
    if db <= TONGUE_LAB_THRESHOLDS["body_stasis_db"] and da >= 1.0:
        return "偏青紫", "血瘀傾向"
    if da >= TONGUE_LAB_THRESHOLDS["body_red_da"] and stats["a_star"] >= TONGUE_LAB_THRESHOLDS["body_heat_a_min"]:
        return "偏紅", "實熱證"
    if da <= TONGUE_LAB_THRESHOLDS["body_pale_da"] and dL >= 3.0:
        return "偏白", "虛寒證"
    return tongue_body_reading(stats)


def tongue_coat_from_lab(stats: dict[str, float], peer: dict[str, float]) -> tuple[str, str]:
    hsv_bias, hsv_meaning = tongue_coat_reading(stats)
    if hsv_bias == "黑灰苔":
        return hsv_bias, hsv_meaning
    if stats.get("pixel_count", 0) >= TONGUE_LAB_THRESHOLDS["min_mask_pixels"]:
        db = stats["b_star"] - peer["b_star"]
        dL = stats["L"] - peer["L"]
        if db >= TONGUE_LAB_THRESHOLDS["center_heat_db_vs_peer"] and dL <= TONGUE_LAB_THRESHOLDS["center_scorch_dL_vs_peer"]:
            return "焦黃苔", "熱盛傷津"
        if db >= TONGUE_LAB_THRESHOLDS["coat_yellow_db"]:
            return "黃苔", "實熱"
    return hsv_bias, hsv_meaning


def tongue_surface_metrics(seg: dict[str, Any]) -> dict[str, float]:
    """LAB plus texture. Energy is GLCM uniformity (thick or smooth); contrast is cracks; highlights are sheen."""
    rgb = seg["rgb"]
    lab = seg["lab"]
    width, height = seg["width"], seg["height"]
    total = max(1, width * height)
    bins = 8
    hist = [[0] * bins for _ in range(bins)]
    pairs = 0
    contrast_sum = 0.0
    highlight_n = 0
    light = [px[0] for px in lab]

    def level(value: float) -> int:
        return min(bins - 1, max(0, int(value / 100.0 * bins)))

    for y in range(height):
        row = y * width
        for x in range(width):
            i = row + x
            lv = light[i]
            neigh: list[float] = []
            if x + 1 < width:
                rv = light[i + 1]
                contrast_sum += abs(lv - rv)
                pairs += 1
                hist[level(lv)][level(rv)] += 1
                neigh.append(rv)
            if y + 1 < height:
                dv = light[i + width]
                contrast_sum += abs(lv - dv)
                pairs += 1
                hist[level(lv)][level(dv)] += 1
                neigh.append(dv)
            if x > 0:
                neigh.append(light[i - 1])
            if y > 0:
                neigh.append(light[i - width])
            if not neigh:
                continue
            local = sum(neigh) / len(neigh)
            _h, sat, _v = rgb_to_hsv_pixel(*rgb[i])
            if lv >= local + 8 and lv >= 68 and sat <= 0.28:
                highlight_n += 1
    energy = 0.0
    if pairs:
        for row_hist in hist:
            for count in row_hist:
                share = count / pairs
                energy += share * share
    coat = seg["coat_stats"]
    body = seg["body_stats"]
    whole = seg["all_stats"]
    body_n = float(body.get("pixel_count") or 0)
    coat_n = float(coat.get("pixel_count") or 0)
    return {
        "coat_ratio": coat.get("pixel_count", 0) / total,
        "coating_ratio": coat_n / max(1.0, body_n + coat_n),
        "coat_L": coat.get("L", 0.0),
        "coat_a": coat.get("a_star", 0.0),
        "coat_b": coat.get("b_star", 0.0),
        "coat_s": coat.get("s", 0.0),
        "body_L": body.get("L", 0.0),
        "body_a": body.get("a_star", 0.0),
        "all_L": whole.get("L", 0.0),
        "all_b": whole.get("b_star", 0.0),
        "energy": energy,
        "contrast": contrast_sum / pairs if pairs else 0.0,
        "highlight": highlight_n / total,
    }


def classify_tongue_coat_appearance(metrics: dict[str, float]) -> dict[str, Any] | None:
    """Four coat appearances from LAB color plus thickness, cracks, and sheen."""
    t = TONGUE_LAB_THRESHOLDS
    coat_ratio = metrics["coat_ratio"]
    coating_ratio = metrics.get("coating_ratio", coat_ratio)
    energy = metrics["energy"]
    contrast = metrics["contrast"]
    highlight = metrics["highlight"]
    # A coat that fills the frame has no pink body to segment against, so use the whole surface.
    covered = coating_ratio >= TONGUE_MIRROR_COAT_MAX or coat_ratio >= 0.15
    color_L = metrics["coat_L"] if covered else metrics["all_L"]
    color_b = metrics["coat_b"] if covered else metrics["all_b"]
    mirror = coating_ratio < TONGUE_MIRROR_COAT_MAX and (
        metrics["body_a"] >= t["coat_mirror_a"]
        or energy >= t["coat_smooth_energy"]
        or highlight >= t["coat_mirror_highlight_min"]
        or coating_ratio <= 0.05
    )
    if mirror:
        return {
            "bias": "光剝無苔",
            "meaning": "胃陰枯竭、全身大虛",
            "overlay": "weak-hot.png",
            "patterns": (("虛證", 2.0), ("熱證", 1.4)),
            "targets": ("stomach",),
            "score": 9.0,
        }
    yellow_dry = (
        color_b >= t["coat_scorch_b"]
        and color_L <= t["coat_yellow_L_low"]
        and contrast >= t["coat_crack_contrast"]
        and highlight <= t["coat_greasy_highlight_max"]
    )
    if yellow_dry:
        return {
            "bias": "黃燥裂苔",
            "meaning": "實熱亢盛、熱極傷津",
            "overlay": "strong-hot.png",
            "patterns": (("熱證", 2.2), ("實證", 1.8)),
            "targets": ("stomach", "large_intestine"),
            "score": 9.0,
        }
    yellow_greasy = (
        color_b >= t["coat_yellow_b"]
        and t["coat_yellow_L_low"] < color_L <= t["coat_yellow_L_high"]
        and energy >= t["coat_thick_energy"]
        and contrast < t["coat_crack_contrast"]
        and highlight <= t["coat_greasy_highlight_max"]
    )
    if yellow_greasy:
        return {
            "bias": "黃厚膩苔",
            "meaning": "胃腸濕熱、積食化火",
            "overlay": "strong-hot.png",
            "patterns": (("熱證", 2.0), ("實證", 1.6)),
            "damp": True,
            "targets": ("stomach", "large_intestine"),
            "score": 9.0,
        }
    white_slip = (
        abs(color_b) <= t["coat_white_b"]
        and color_L >= t["coat_white_L"]
        and energy >= t["coat_thick_energy"]
        and highlight >= t["coat_slip_highlight_min"]
        and metrics["body_a"] < t["coat_mirror_a"]
    )
    if white_slip:
        return {
            "bias": "白厚滑苔",
            "meaning": "胃虛寒、寒濕內停",
            "overlay": "weak-cold.png",
            "patterns": (("虛證", 1.8), ("寒證", 2.0)),
            "targets": ("stomach",),
            "score": 9.0,
        }
    return None


def _coat_feature_text(metrics: dict[str, float]) -> str:
    covered = metrics["coat_ratio"] >= 0.15
    color_L = metrics["coat_L"] if covered else metrics["all_L"]
    color_b = metrics["coat_b"] if covered else metrics["all_b"]
    return (
        f"L* {color_L:.1f} a* {metrics['body_a']:.1f} b* {color_b:.1f}，"
        f"能量 {metrics['energy']:.2f}、對比 {metrics['contrast']:.1f}、高光 {metrics['highlight']:.2f}"
    )


def _speckle_ratio(a_vals: list[float], extra: float) -> float:
    if not a_vals:
        return 0.0
    med = _median(a_vals)
    return sum(1 for value in a_vals if value >= med + extra) / float(len(a_vals))


def _morph_open_close(mask_img: Image.Image, kernel: int) -> Image.Image:
    opened = mask_img.filter(ImageFilter.MinFilter(kernel)).filter(ImageFilter.MaxFilter(kernel))
    return opened.filter(ImageFilter.MaxFilter(kernel)).filter(ImageFilter.MinFilter(kernel))


def _box_xy(spec: dict[str, float], width: int, height: int) -> tuple[int, int, int, int]:
    x0 = max(0, int(spec["left"] * width))
    y0 = max(0, int(spec["top"] * height))
    x1 = min(width, max(x0 + 1, int(spec["right"] * width)))
    y1 = min(height, max(y0 + 1, int(spec["bottom"] * height)))
    return x0, y0, x1, y1


def _gather_masked(
    rgb: list[tuple[int, int, int]],
    lab: list[tuple[float, float, float]],
    coat_mask: list[int],
    width: int,
    height: int,
    spec: dict[str, float],
    want_coat: bool | None,
) -> tuple[dict[str, float], list[float]]:
    x0, y0, x1, y1 = _box_xy(spec, width, height)
    picked_rgb: list[tuple[int, int, int]] = []
    picked_lab: list[tuple[float, float, float]] = []
    a_vals: list[float] = []
    for y in range(y0, y1):
        row = y * width
        for x in range(x0, x1):
            idx = row + x
            is_coat = coat_mask[idx] >= 128
            if want_coat is None or is_coat is want_coat:
                picked_rgb.append(rgb[idx])
                picked_lab.append(lab[idx])
                a_vals.append(lab[idx][1])
    return _stats_from_rgb_lab(picked_rgb, picked_lab), a_vals


def segment_tongue_body_coat(image: Image.Image) -> dict[str, Any]:
    """ML-free coat vs body split: S + b* + L* thresholds, then 3×3 open/close."""
    work = _thumbnail_rgb(image, 160)
    width, height = work.size
    rgb = list(work.getdata())
    lab = [(L * 100.0 / 255.0, a - 128.0, bch - 128.0) for L, a, bch in work.convert("LAB").getdata()]
    hsvs = [rgb_to_hsv_pixel(*pixel) for pixel in rgb]
    s_med = _median([item[1] for item in hsvs])
    l_med = _median([item[0] for item in lab])
    a_med = _median([item[1] for item in lab])
    b_med = _median([item[2] for item in lab])
    s_white = max(TONGUE_LAB_THRESHOLDS["seg_white_s_cap"], s_med * TONGUE_LAB_THRESHOLDS["seg_white_s_rel"])
    raw = []
    for (_h, sat, _v), (light, a_star, b_star) in zip(hsvs, lab):
        white = sat <= s_white and light >= l_med
        yellow = (b_star - b_med) >= TONGUE_LAB_THRESHOLDS["seg_yellow_db"] and light >= l_med + TONGUE_LAB_THRESHOLDS["seg_yellow_dL_floor"]
        strong_body = (a_star - a_med) >= TONGUE_LAB_THRESHOLDS["seg_body_da"] and sat >= TONGUE_LAB_THRESHOLDS["seg_body_s_min"]
        raw.append(255 if (white or yellow) and not strong_body else 0)
    coat_img = Image.new("L", (width, height))
    coat_img.putdata(raw)
    if sum(1 for value in raw if value) >= TONGUE_LAB_THRESHOLDS["min_mask_pixels"]:
        coat_img = _morph_open_close(coat_img, int(TONGUE_LAB_THRESHOLDS["morph_kernel"]))
    coat_mask = list(coat_img.getdata())
    body_stats, _ = _gather_masked(rgb, lab, coat_mask, width, height, {"left": 0, "top": 0, "right": 1, "bottom": 1}, False)
    coat_stats, _ = _gather_masked(rgb, lab, coat_mask, width, height, {"left": 0, "top": 0, "right": 1, "bottom": 1}, True)
    all_stats = _stats_from_rgb_lab(rgb, lab)
    total = max(1, width * height)
    body_n = float(body_stats.get("pixel_count") or 0)
    coat_n = float(coat_stats.get("pixel_count") or 0)
    return {
        "width": width,
        "height": height,
        "rgb": rgb,
        "lab": lab,
        "coat_mask": coat_mask,
        "body_stats": body_stats,
        "coat_stats": coat_stats,
        "all_stats": all_stats,
        "body_ratio": round(body_n / total, 3),
        "coat_ratio": round(coat_n / total, 3),
        "coating_ratio": round(coat_n / max(1.0, body_n + coat_n), 3),
        "coating_ratio_def": TONGUE_COATING_RATIO_DEF,
        "s_median": round(s_med, 3),
        "L_median": round(l_med, 1),
        "a_median": round(a_med, 1),
        "b_median": round(b_med, 1),
        "method": "hsv_lab_S_b_L_threshold_then_morph_open_close",
    }


def _lab_baseline(stats: dict[str, float]) -> dict[str, float]:
    return {
        "L": stats.get("L_median", stats.get("L", 0)),
        "a_star": stats.get("a_median", stats.get("a_star", 0)),
        "b_star": stats.get("b_median", stats.get("b_star", 0)),
        "s": stats.get("s", 0),
    }


def analyze_tongue_grid(image: Image.Image) -> tuple[dict[str, Any], list[str], dict[str, str | None]]:
    findings: list[str] = []
    marks: list[dict[str, Any]] = []
    best_overlay: dict[str, tuple[float, str, tuple[tuple[str, float], ...]]] = {}
    thresh = TONGUE_LAB_THRESHOLDS
    seg = segment_tongue_body_coat(image)
    baseline = _lab_baseline(seg["all_stats"])
    coating_ratio = float(seg.get("coating_ratio") or tongue_coating_ratio(seg))

    def remember(
        targets: tuple[str, ...],
        overlay: str | None,
        patterns: tuple[tuple[str, float], ...],
        score: float,
        source: str = "body",
    ) -> None:
        for name, weight in patterns:
            for organ in targets:
                marks.append({"organ": organ, "pattern": name, "weight": weight, "source": source})
        if not overlay:
            return
        for organ in targets:
            previous = best_overlay.get(organ)
            if previous is None or score > previous[0]:
                best_overlay[organ] = (score, overlay, patterns)

    def zone_layers(spec: dict[str, Any]) -> dict[str, Any]:
        all_stats, all_a = _gather_masked(seg["rgb"], seg["lab"], seg["coat_mask"], seg["width"], seg["height"], spec, None)
        body_stats, body_a = _gather_masked(seg["rgb"], seg["lab"], seg["coat_mask"], seg["width"], seg["height"], spec, False)
        coat_stats, _coat_a = _gather_masked(seg["rgb"], seg["lab"], seg["coat_mask"], seg["width"], seg["height"], spec, True)
        raw_body_count = body_stats.get("pixel_count", 0)
        raw_coat_count = coat_stats.get("pixel_count", 0)
        raw_body = body_stats
        raw_coat = coat_stats
        if raw_body_count < thresh["min_mask_pixels"]:
            body_stats, body_a = all_stats, all_a
        if raw_coat_count < thresh["min_mask_pixels"]:
            coat_stats = all_stats
        return {
            "all": all_stats,
            "body": body_stats,
            "coat": coat_stats,
            "body_a": body_a,
            "raw_body": raw_body,
            "raw_coat": raw_coat,
            "raw_body_count": raw_body_count,
            "raw_coat_count": raw_coat_count,
        }

    packed: dict[str, dict[str, Any]] = {spec["id"]: zone_layers(spec) for spec in TONGUE_ZONE_LAYOUT}
    body_blocks: list[dict[str, Any]] = []
    coat_blocks: list[dict[str, Any]] = []
    peer_coats = [packed[zid]["coat"] for zid in ("top", "left", "right", "bottom") if zid in packed]
    peer = average_stats(peer_coats) if peer_coats else seg["all_stats"]
    center_coat = packed["center"]["coat"]
    tip_body = packed["bottom"]["body"]
    center_body = packed["center"]["body"]
    if center_body.get("pixel_count", 0) < thresh["min_mask_pixels"]:
        center_body = packed["center"]["all"]
    if tip_body.get("pixel_count", 0) < thresh["min_mask_pixels"]:
        tip_body = packed["bottom"]["all"]
    delta_a = round(tip_body["a_star"] - center_body["a_star"], 2)
    tip_heat_flag = delta_a >= thresh["delta_a_tip_minus_center"]
    speckle = _speckle_ratio(packed["bottom"]["body_a"], thresh["tip_speckle_da_vs_tip_median"])
    tongue_aspect = image.width / max(1, image.height)
    thin_tongue = tongue_aspect <= thresh["side_thin_aspect"]
    side_flags: list[str] = []
    root_flags: list[str] = []

    zones: list[dict[str, Any]] = []
    for spec in TONGUE_ZONE_LAYOUT:
        layers = packed[spec["id"]]
        body_stats = layers["body"]
        coat_stats = layers["coat"]
        bias, meaning = tongue_body_from_lab(body_stats, baseline)
        interpretation = (
            f"{spec['label']}（{spec['organs']}／{spec['anatomy']}）舌質{bias} → {meaning}（{TEACHING_NOTE}）"
        )
        zone_findings: list[str] = []

        if spec["id"] == "bottom":
            da_center = tip_body["a_star"] - center_body["a_star"]
            da_base = tip_body["a_star"] - baseline["a_star"]
            dL_base = tip_body["L"] - baseline["L"]
            vacuity = dL_base >= thresh["tip_vacuity_dL_vs_baseline"] and da_base <= thresh["tip_vacuity_da_vs_baseline"]
            heat = da_center >= thresh["tip_heat_da_vs_center"] and da_base >= thresh["tip_heat_da_vs_baseline"]
            dots = thresh["tip_speckle_min_ratio"] <= speckle <= thresh["tip_speckle_max_ratio"]
            if heat:
                bias, meaning = "偏紅", "心火盛（實熱）"
                extra = "，點刺（舌尖高 a* 斑點）" if dots else ""
                interpretation = (
                    f"下（心肺／舌尖）a* 相對舌中 {da_center:+.1f}、相對全舌中位 {da_base:+.1f}"
                    f"{extra} → 心火盛（實熱）（{TEACHING_NOTE}）"
                )
                zone_findings.append(interpretation)
                remember(("heart",), "strong-hot.png", (("熱證", 2.2), ("實證", 1.6)), 8.0)
                remember(("lung",), "strong-hot.png", (("熱證", 1.2),), 5.0)
                if dots:
                    remember(("heart",), "strong-hot.png", (("熱證", 0.8),), 3.0)
            elif vacuity:
                bias, meaning = "淡白無血色", "心肺氣虛（虛寒）"
                interpretation = (
                    f"下（心肺／舌尖）L* 相對全舌中位 {dL_base:+.1f} 且 a* {da_base:+.1f} → "
                    f"心肺氣虛（虛寒）、淡白無血色（{TEACHING_NOTE}）"
                )
                zone_findings.append(interpretation)
                remember(("heart", "lung"), "weak-cold.png", (("虛證", 2.0), ("寒證", 1.6)), 8.0)
        elif spec["id"] == "center":
            db_peer = center_coat["b_star"] - peer["b_star"]
            dL_peer = center_coat["L"] - peer["L"]
            s_center = center_coat["s"]
            heat_coat = db_peer >= thresh["center_heat_db_vs_peer"]
            cold_coat = (
                abs(center_coat["b_star"]) <= thresh["center_cold_abs_b"]
                and db_peer <= thresh["center_cold_db_vs_peer"]
                and dL_peer >= thresh["center_cold_dL_vs_peer"]
                and s_center <= thresh["center_cold_s_max"]
            )
            if heat_coat:
                scorch = dL_peer <= thresh["center_scorch_dL_vs_peer"]
                bias = "焦黃苔" if scorch else "黃苔"
                meaning = "胃腸實熱／濕熱（熱盛傷津）" if scorch else "胃腸實熱／濕熱"
                interpretation = (
                    f"中（脾胃／舌中）舌苔 b* 相對他區 {db_peer:+.1f}、L* {dL_peer:+.1f} → {meaning}（{TEACHING_NOTE}）"
                )
                zone_findings.append(interpretation)
                remember(("stomach", "large_intestine"), "strong-hot.png", (("熱證", 2.0), ("實證", 1.6)), 8.0, "coat")
                remember(("gallbladder",), "strong-hot.png", (("熱證", 1.3),), 4.0, "coat")
                if not scorch:
                    remember(("stomach",), DAMP_OVERLAY, (("熱證", 1.4), ("實證", 1.2)), 9.0, "coat")
            elif cold_coat:
                bias, meaning = "白厚苔", "胃虛寒（寒濕）"
                interpretation = (
                    f"中（脾胃／舌中）舌苔 b*={center_coat['b_star']:.1f} 近 0、L* 相對 {dL_peer:+.1f}、S={s_center:.2f} → "
                    f"胃虛寒（寒濕）、白厚苔（{TEACHING_NOTE}）"
                )
                zone_findings.append(interpretation)
                remember(("stomach",), "weak-cold.png", (("虛證", 1.8), ("寒證", 2.0)), 8.0, "coat")
            else:
                coat_bias, coat_meaning = tongue_coat_from_lab(center_coat, peer)
                if coat_bias != "苔色中性":
                    bias, meaning = coat_bias, coat_meaning
                    interpretation = (
                        f"中（脾胃／舌中）主要觀察舌苔 {coat_bias} → {coat_meaning}（{TEACHING_NOTE}）"
                    )
                    zone_findings.append(interpretation)
        elif spec["id"] == "top":
            root_n = max(1.0, layers["all"].get("pixel_count", 1))
            root_coat_ratio = layers["raw_coat_count"] / root_n
            other_ratios = []
            coated_parts = []
            for zid in ("center", "left", "right", "bottom"):
                other_n = max(1.0, packed[zid]["all"].get("pixel_count", 1))
                other_ratios.append(packed[zid]["raw_coat_count"] / other_n)
                if packed[zid]["raw_coat_count"] >= thresh["min_mask_pixels"]:
                    coated_parts.append(packed[zid]["raw_coat"])
            other_coat = sum(other_ratios) / len(other_ratios)
            coated = average_stats(coated_parts) if coated_parts else None
            exposed = layers["raw_body"] if layers["raw_body_count"] >= thresh["min_mask_pixels"] else body_stats
            peeled = (
                root_coat_ratio <= thresh["root_peel_coat_max"]
                and coated is not None
                and other_coat >= root_coat_ratio + thresh["root_peel_coat_gap"]
            )
            da_coat = (exposed["a_star"] - coated["a_star"]) if coated is not None else 0.0
            dL_gap = abs(exposed["L"] - coated["L"]) if coated is not None else 0.0
            coat_visible = layers["raw_coat"] if layers["raw_coat_count"] >= thresh["min_mask_pixels"] else None
            thick_white = False
            if coat_visible is not None and root_coat_ratio >= thresh["root_thick_coat_min"]:
                dL_coat = coat_visible["L"] - center_body["L"]
                da_pale = body_stats["a_star"] - center_body["a_star"]
                thick_white = (
                    dL_coat >= thresh["root_yang_dL_vs_center"]
                    and coat_visible["s"] <= thresh["root_yang_coat_s_max"]
                    and coat_visible["b_star"] <= thresh["root_yang_coat_b_max"]
                    and da_pale <= thresh["root_yang_da_vs_center"]
                    and body_stats["L"] >= center_body["L"] + 3.0
                )
            if (
                peeled
                and exposed["a_star"] >= thresh["root_yin_a_min"]
                and da_coat >= thresh["root_yin_da"]
                and dL_gap >= thresh["root_yin_dL_gap"]
            ):
                bias, meaning = "剝苔", "腎陰虛（虛熱）"
                interpretation = (
                    f"上（腎／舌根）剝苔，露出舌質 a* {exposed['a_star']:.1f}（高於有苔區 {da_coat:+.1f}），"
                    f"L* 與有苔區相差 {dL_gap:.1f} → 腎陰虛（虛熱）（{TEACHING_NOTE}）"
                )
                zone_findings.append(interpretation)
                root_flags.append(interpretation)
                remember(("kidney",), "weak-hot.png", (("虛證", 1.8), ("熱證", 2.0)), 8.0)
            elif thick_white and coat_visible is not None:
                bias, meaning = "白厚苔", "命門火衰（腎陽虛）"
                interpretation = (
                    f"上（腎／舌根）苔厚白，苔 L* {coat_visible['L']:.1f}、S {coat_visible['s']:.2f}，"
                    f"舌質 a* 相對舌中 {body_stats['a_star'] - center_body['a_star']:+.1f}、偏淡嫩"
                    f" → 命門火衰（腎陽虛）（{TEACHING_NOTE}）"
                )
                zone_findings.append(interpretation)
                root_flags.append(interpretation)
                remember(("kidney",), "weak-cold.png", (("虛證", 1.8), ("寒證", 2.0)), 8.0, "coat")
            else:
                bias, meaning = "接近周圍", "舌根未見剝苔或厚白苔"
                interpretation = f"上（腎／舌根）未見剝苔或厚白苔（{TEACHING_NOTE}）"
        elif spec["id"] in ("left", "right"):
            da_center = body_stats["a_star"] - center_body["a_star"]
            db_center = body_stats["b_star"] - center_body["b_star"]
            purple = db_center <= thresh["side_purple_db_vs_center"]
            side_name = "左" if spec["id"] == "left" else "右"
            if da_center >= thresh["side_heat_da_vs_center"]:
                if purple:
                    bias, meaning = "邊紅暗紫", "肝膽濕熱（氣鬱化火）"
                    interpretation = (
                        f"{side_name}（肝膽／舌邊）a* 高於舌中 {da_center:+.1f}，b* {db_center:+.1f} 略偏暗紫"
                        f" → 肝膽濕熱、氣鬱化火（{TEACHING_NOTE}）"
                    )
                    remember(("liver", "gallbladder"), "strong-hot.png", (("熱證", 2.0), ("實證", 1.6)), 8.0)
                    remember(("liver", "gallbladder"), DAMP_OVERLAY, (("熱證", 1.2), ("實證", 1.0)), 6.0)
                else:
                    bias, meaning = "邊紅", "肝火旺"
                    interpretation = (
                        f"{side_name}（肝膽／舌邊）a* 高於舌中 {da_center:+.1f} → 肝火旺（{TEACHING_NOTE}）"
                    )
                    remember(("liver", "gallbladder"), "strong-hot.png", (("熱證", 2.0), ("實證", 1.5)), 8.0)
                zone_findings.append(interpretation)
                side_flags.append(interpretation)
            elif da_center <= thresh["side_pale_da_vs_center"]:
                thin_note = "，並見舌體瘦小" if thin_tongue else ""
                bias, meaning = "邊淡白", "肝血虛" + ("（舌體瘦小）" if thin_tongue else "")
                interpretation = (
                    f"{side_name}（肝膽／舌邊）a* 低於舌中 {da_center:+.1f}{thin_note} → 肝血虛（{TEACHING_NOTE}）"
                )
                zone_findings.append(interpretation)
                side_flags.append(interpretation)
                remember(("liver",), "weak-cold.png", (("虛證", 1.8),), 7.0)
            elif bias == "偏青紫":
                zone_findings.append(interpretation)
                remember(("liver", "gallbladder"), "strong-cold.png", (("實證", 1.8),), 6.0)
        else:
            if bias == "偏青紫":
                zone_findings.append(interpretation)
                remember(TONGUE_ZONE_TARGETS[spec["id"]], "strong-cold.png", (("實證", 1.8),), 6.0)
            elif bias == "偏紅":
                zone_findings.append(interpretation)
                remember(TONGUE_ZONE_TARGETS[spec["id"]], "strong-hot.png", (("熱證", 1.5), ("實證", 1.2)), 5.0)
            elif bias == "偏白":
                zone_findings.append(interpretation)
                remember(TONGUE_ZONE_TARGETS[spec["id"]], "weak-cold.png", (("虛證", 1.4), ("寒證", 1.5)), 5.0)

        findings.extend(zone_findings)
        zone_organs = list(TONGUE_ZONE_TARGETS.get(spec["id"]) or organs_from_zh(spec["organs"]))
        if spec["id"] == "center":
            body_organs = ["spleen"]
            coat_organs = ["stomach"]
        else:
            body_organs = zone_organs
            coat_organs = zone_organs
        body_blocks.append(
            {
                "label": spec["id"],
                "organs": body_organs,
                "delta_e": round(lab_cie76(body_stats, TONGUE_BODY_NORMAL), 2),
            }
        )
        zone_coat_n = float(coat_stats.get("pixel_count") or 0)
        if zone_coat_n < thresh["min_mask_pixels"] and coating_ratio < TONGUE_MIRROR_COAT_MAX:
            coat_delta = 8.0 + 12.0 * max(0.0, (TONGUE_MIRROR_COAT_MAX - coating_ratio) / TONGUE_MIRROR_COAT_MAX)
        else:
            coat_delta = lab_cie76(coat_stats, TONGUE_COAT_NORMAL)
        coat_blocks.append(
            {
                "label": spec["id"],
                "organs": coat_organs,
                "delta_e": round(coat_delta, 2),
            }
        )
        total_px = max(1.0, layers["all"].get("pixel_count", 1))
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
                "hex": hex_from_stats(body_stats),
                "hsv": compact_hsv(body_stats),
                "lab": compact_lab(body_stats),
                "lab_text": format_lab(body_stats),
                "body": _channel_pack(body_stats),
                "coat": _channel_pack(coat_stats),
                "body_ratio": round(body_stats.get("pixel_count", 0) / total_px, 3),
                "coat_ratio": round(coat_stats.get("pixel_count", 0) / total_px, 3),
                "bias": bias,
                "meaning": meaning,
                "reading": f"{bias} → {meaning}",
                "interpretation": interpretation,
            }
        )

    if tip_heat_flag:
        flag_text = (
            f"{TONGUE_TIP_HEAT_FLAG}（Δa* 舌尖−舌中 = {delta_a:+.1f}，門檻 {thresh['delta_a_tip_minus_center']}）（{TEACHING_NOTE}）"
        )
        findings.append(flag_text)
        remember(("heart",), "strong-hot.png", (("熱證", 1.4),), 4.0)

    coat_box_stats, _ = _gather_masked(
        seg["rgb"], seg["lab"], seg["coat_mask"], seg["width"], seg["height"], TONGUE_COAT_BOX, True
    )
    if coat_box_stats.get("pixel_count", 0) < thresh["min_mask_pixels"]:
        coat_box_stats = seg["coat_stats"] if seg["coat_stats"].get("pixel_count", 0) else packed["center"]["all"]
    surface = tongue_surface_metrics(seg)
    appearance = classify_tongue_coat_appearance(surface)
    if appearance:
        coat_bias, coat_meaning = appearance["bias"], appearance["meaning"]
        coat_text = (
            f"{coat_bias}（{_coat_feature_text(surface)}）→ {coat_meaning}（{TEACHING_NOTE}）"
        )
        remember(appearance["targets"], appearance["overlay"], appearance["patterns"], appearance["score"], "coat")
        if appearance.get("damp"):
            remember(("stomach",), DAMP_OVERLAY, (("熱證", 1.4), ("實證", 1.2)), 7.0, "coat")
    else:
        coat_bias, coat_meaning = tongue_coat_from_lab(coat_box_stats, peer)
        coat_text = f"舌苔（全舌疊加，分離後苔像素）{coat_bias} → {coat_meaning}（{TEACHING_NOTE}）"
        if coat_bias == "黑灰苔":
            remember(("kidney",), "strong-cold.png", (("寒證", 1.8), ("實證", 1.4)), 6.0, "coat")
        elif coat_bias in ("黃苔", "焦黃苔"):
            remember(("stomach",), "strong-hot.png", (("熱證", 1.5),), 5.0, "coat")
        elif coat_bias == "白苔很少":
            remember(("stomach",), "weak-cold.png", (("虛證", 1.8),), 5.0, "coat")
    findings.append(coat_text)

    body_all = seg["body_stats"] if seg["body_stats"].get("pixel_count", 0) else average_stats([packed[z]["body"] for z in packed])
    body_bias, body_meaning = tongue_body_from_lab(body_all, baseline)
    colors = {
        "face_color": None,
        "lip_color": None,
        "tongue_body_color": f"{body_bias}／{body_meaning}",
        "tongue_coat_color": f"{coat_bias}／{coat_meaning}",
    }
    center_cell = next(cell for cell in zones if cell["id"] == "center")
    coating = {
        "id": "coating",
        "label": "舌苔",
        "organs": "胃／膽／大腸",
        "layer": 6,
        "hex": hex_from_stats(coat_box_stats),
        "hsv": compact_hsv(coat_box_stats),
        "lab": compact_lab(coat_box_stats),
        "lab_text": format_lab(coat_box_stats),
        "S": round(coat_box_stats.get("s", 0), 3),
        "pixel_count": int(coat_box_stats.get("pixel_count", 0)),
        "bias": coat_bias,
        "meaning": coat_meaning,
        "reading": f"{coat_bias} → {coat_meaning}",
        "interpretation": coat_text,
        "texture": {
            "energy": round(surface["energy"], 3),
            "contrast": round(surface["contrast"], 2),
            "highlight": round(surface["highlight"], 3),
        },
        "box": TONGUE_COAT_BOX,
    }
    coat_blocks.append(
        {
            "label": "coating",
            "organs": ["stomach", "gallbladder", "large_intestine"],
            "delta_e": round(lab_cie76(coat_box_stats, TONGUE_COAT_NORMAL), 2),
        }
    )
    bianzheng = classify_tongue_bianzheng(body_all, coat_box_stats, coating_ratio, surface)
    for block in body_blocks + coat_blocks:
        block["class_label"] = bianzheng.get("label")
        block["api_pattern"] = bianzheng.get("api_pattern")
    colors["tongue_body_color"] = f"{bianzheng['bias']}／{bianzheng['meaning']}"
    remember(
        bianzheng.get("targets") or (),
        bianzheng.get("overlay"),
        bianzheng.get("patterns") or (),
        float(20 - min(bianzheng["body_health"], bianzheng["coat_health"])),
        "coat" if bianzheng["label"] in ("濕症", "實熱") else "body",
    )
    body_color_health = apply_relative_color_scores(body_blocks, ref=DELTA_E_REF)
    coat_color_health = apply_relative_color_scores(coat_blocks, ref=TONGUE_COAT_DELTA_E_REF)
    body_by_label = {block["label"]: block for block in body_blocks}
    coat_by_label = {block["label"]: block for block in coat_blocks}
    for zone in zones:
        body_hit = body_by_label.get(zone["id"])
        coat_hit = coat_by_label.get(zone["id"])
        if body_hit:
            zone["delta_e"] = body_hit["delta_e"]
            zone["health_score"] = body_hit["health_score"]
            zone["body"]["delta_e"] = body_hit["delta_e"]
            zone["body"]["health_score"] = body_hit["health_score"]
        if coat_hit:
            zone["coat_delta_e"] = coat_hit["delta_e"]
            zone["coat_health_score"] = coat_hit["health_score"]
            zone["coat"]["delta_e"] = coat_hit["delta_e"]
            zone["coat"]["health_score"] = coat_hit["health_score"]
    coat_hit = coat_by_label.get("coating")
    if coat_hit:
        coating["delta_e"] = coat_hit["delta_e"]
        coating["health_score"] = coat_hit["health_score"]
    measurements = []
    for zone in zones:
        measurements.append(
            {
                "zone_id": zone["id"],
                "part": "body",
                "label": zone["label"],
                "organs": zone["organs"],
                "hex": zone["hex"],
                "hsv": zone["hsv"],
                "lab": zone["lab"],
                "bias": zone["bias"],
                "meaning": zone["meaning"],
                "reading": zone["reading"],
                "delta_e": zone.get("delta_e"),
                "health_score": zone.get("health_score"),
            }
        )
        measurements.append(
            {
                "zone_id": zone["id"],
                "part": "coat",
                "label": zone["label"],
                "organs": zone["organs"],
                "hex": zone["coat"]["hex"],
                "hsv": zone["coat"]["hsv"],
                "lab": zone["coat"]["lab"],
                "S": zone["coat"]["S"],
                "delta_e": zone.get("coat_delta_e"),
                "health_score": zone.get("coat_health_score"),
            }
        )
    measurements.append(
        {
            "zone_id": "coating",
            "part": "coating",
            "label": "舌苔",
            "organs": "胃／膽／大腸",
            "hex": coating["hex"],
            "hsv": coating["hsv"],
            "lab": coating["lab"],
            "S": coating["S"],
            "bias": coat_bias,
            "meaning": coat_meaning,
            "reading": coating["reading"],
            "delta_e": coating.get("delta_e"),
            "health_score": coating.get("health_score"),
        }
    )
    organ_overlays = {organ: filename for organ, (_score, filename, _patterns) in best_overlay.items()}
    tongue_grid = {
        "zones": 5,
        "sixth": "coating_overlay",
        "sixth_note": TONGUE_SIXTH_NOTE,
        "orientation": "tip_at_bottom_root_at_top",
        "layout": TONGUE_ZONE_LAYOUT,
        "cells": zones,
        "coating": coating,
        "measurements": measurements,
        "marks": marks,
        "organ_overlays": organ_overlays,
        "body": {
            "hex": hex_from_stats(body_all),
            "hsv": compact_hsv(body_all),
            "lab": compact_lab(body_all),
            "bias": body_bias,
            "meaning": body_meaning,
            "pixel_count": int(body_all.get("pixel_count", 0)),
        },
        "segmentation": {
            "method": seg["method"],
            "body_ratio": seg["body_ratio"],
            "coat_ratio": seg["coat_ratio"],
            "body": _channel_pack(seg["body_stats"]),
            "coat": _channel_pack(seg["coat_stats"]),
            "s_median": seg["s_median"],
            "L_median": seg["L_median"],
            "a_median": seg["a_median"],
            "b_median": seg["b_median"],
        },
        "center_coat": {
            "L": center_cell["coat"]["lab"]["L"],
            "a": center_cell["coat"]["lab"]["a"],
            "b": center_cell["coat"]["lab"]["b"],
            "S": center_cell["coat"]["S"],
            "pixel_count": center_cell["coat"]["pixel_count"],
        },
        "delta_a_tip_minus_center": delta_a,
        "delta_a_threshold": thresh["delta_a_tip_minus_center"],
        "tip_heat_flag": tip_heat_flag,
        "tip_heat_flag_text": TONGUE_TIP_HEAT_FLAG if tip_heat_flag else None,
        "liver_side_flags": side_flags,
        "liver_side_flag_text": " ".join(side_flags) if side_flags else None,
        "root_flags": root_flags,
        "root_flag_text": " ".join(root_flags) if root_flags else None,
        "tongue_aspect": round(tongue_aspect, 3),
        "tongue_thin": thin_tongue,
        "tip_speckle_ratio": round(speckle, 3),
        "baseline": compact_lab(seg["all_stats"]),
        "thresholds": thresh,
        "body_color_health": body_color_health,
        "coat_color_health": coat_color_health,
        "bianzheng": bianzheng,
        "teaching_normal": {"body": TONGUE_BODY_NORMAL, "coat": TONGUE_COAT_NORMAL},
        "coating_ratio": coating_ratio,
        "coating_ratio_def": TONGUE_COATING_RATIO_DEF,
        "disclaimer": TEACHING_NOTE,
    }
    return tongue_grid, findings, colors


def frame_tongue_image(image: Image.Image) -> tuple[Image.Image, dict[str, Any]]:
    """Client already cropped the yellow frame: teeth line → bottom arc, full width.

    Keep that rectangle. Zone fractions are of this image, so the grid matches the frame.
    """
    rgb = image.convert("RGB")
    return rgb, {
        "method": "yellow_frame",
        "box": [0.0, 0.0, 1.0, 1.0],
        "preview": _encode_preview_png(rgb),
    }


def inspect_image(
    image_bytes: bytes,
    shot_type: str,
    personal_lab: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw_image = Image.open(BytesIO(image_bytes)).convert("RGB")
    if shot_type == "tongue":
        image, crop_info = frame_tongue_image(raw_image)
    else:
        # Uploaded JPEG already moved the face up by 1/4 of a cell and scaled it
        # to 0.9. Cells sample that image (after the existing background crop).
        image, crop_info = isolate_subject(raw_image, shot_type)
        crop_info = dict(crop_info)
        crop_info["color_shift_cells"] = FACE_COLOR_SHIFT_CELLS
        crop_info["color_scale"] = FACE_COLOR_SCALE
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
        face_grid, grid_findings, colors = analyze_face_grid(image, personal_lab=personal_lab)
        findings.extend(grid_findings)

    if not findings:
        findings.append("未見明顯偏色，相對基本色健康分接近 10")

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
    personal_lab: dict[str, Any] | None = None,
    confirm_with_pulse: bool = False,
) -> dict[str, Any]:
    color_reports = [
        inspect_image(raw, shot_type, personal_lab=personal_lab if shot_type == "face" else None)
        for shot_type, raw in images
    ]
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
    pattern_scores, pattern_notes = score_spleen_stomach_symptoms(f"{symptoms} {discomfort}")
    apply_pattern_scores_to_evidence(evidence, pattern_scores)
    text_notes.extend(pattern_notes)
    pattern_baseline = {
        organ: dict(evidence[organ])
        for organ in ("spleen", "stomach")
    }
    apply_color_findings(evidence, findings)
    for mark in (face_grid or {}).get("marks") or []:
        add(evidence, mark["organ"], mark["pattern"], mark["weight"])
    for mark in (tongue_grid or {}).get("marks") or []:
        add(evidence, mark["organ"], mark["pattern"], mark["weight"])
    pulse_notes = apply_pulse(evidence, pulse)
    for organ, name in (("spleen", "脾"), ("stomach", "胃")):
        for kind in pattern_kinds_gained(evidence[organ], pattern_baseline[organ]):
            pattern_scores[f"{name}{kind}"] += 1
    _combined_scores, patterns, overlays = finalize(evidence)

    face_color = (face_grid or {}).get("color_health") or {}
    body_color = (tongue_grid or {}).get("body_color_health") or {}
    coat_color = (tongue_grid or {}).get("coat_color_health") or {}
    face_scores = face_color.get("organ_scores") if face_grid else None
    body_scores = body_color.get("organ_scores") if tongue_grid else None
    coat_scores = coat_color.get("organ_scores") if tongue_grid else None
    source_maps = {
        "face": face_scores,
        "tongue_body": body_scores,
        "tongue_coat": coat_scores,
    }
    scores, breakdown = compose_organ_health(source_maps)
    used_sources = [key for key, value in source_maps.items() if value is not None]
    organ_health = serialize_organ_health(scores, breakdown, used_sources)
    organ_health["pattern_scores"] = pattern_scores

    def merge_color_patterns(pattern_map: dict[str, str] | None) -> None:
        for organ, label in (pattern_map or {}).items():
            if not label or label in ("健康", "待觀察", "未定"):
                continue
            for key, _name, _score_key, pattern_key in ORGAN_META:
                if key == organ:
                    patterns[pattern_key] = label
                    overlay = overlay_from_pattern_label(label)
                    if overlay:
                        overlays[organ] = overlay

    merge_color_patterns(((face_grid or {}).get("color_health") or {}).get("organ_patterns"))
    merge_color_patterns(((tongue_grid or {}).get("body_color_health") or {}).get("organ_patterns"))
    merge_color_patterns(((tongue_grid or {}).get("coat_color_health") or {}).get("organ_patterns"))
    for grid in (face_grid, tongue_grid):
        for organ, filename in ((grid or {}).get("organ_overlays") or {}).items():
            overlays[organ] = filename
            if filename == DAMP_OVERLAY:
                for key, _name, _score_key, pattern_key in ORGAN_META:
                    if key == organ and patterns.get(pattern_key) in ("待觀察", "未定", "健康", None, ""):
                        patterns[pattern_key] = "濕氣較重"
    healthy_labels = {"健康", "待觀察", "未定", "正常", "接近正常", "接近基本色", "", None}
    color_sources = (
        (face_scores, face_color.get("organ_patterns") or {}),
        (body_scores, body_color.get("organ_patterns") or {}),
        (coat_scores, coat_color.get("organ_patterns") or {}),
    )
    for key, _name, score_key, pattern_key in ORGAN_META:
        score = scores[score_key]
        if score >= 7:
            patterns[pattern_key] = "健康"
            overlays[key] = None
            continue
        ranked: list[tuple[int, str]] = []
        for src_scores, src_patterns in color_sources:
            if not src_scores or score_key not in src_scores:
                continue
            label = src_patterns.get(key) or ""
            ranked.append((int(src_scores[score_key]), str(label)))
        if not ranked:
            continue
        _worst_score, worst_label = min(ranked, key=lambda item: item[0])
        if worst_label not in healthy_labels:
            patterns[pattern_key] = worst_label
            overlay = overlay_from_pattern_label(worst_label)
            if overlay:
                overlays[key] = overlay
    all_findings = findings + text_notes + pulse_notes
    if not all_findings:
        all_findings = ["資料不足，各臟腑先記 10 分（正常），不放置證型圖"]

    return {
        "dominant_color": dominant,
        "hsv": hsv,
        "color_label": color_label,
        "region_colors": region_colors,
        "findings": all_findings,
        "scores": scores,
        "pattern_scores": pattern_scores,
        "organ_health": organ_health,
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
