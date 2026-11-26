"""Teaching-demo stool / urine notes from a yellow-circle camera crop.

Text-only findings. No diagnosis. Images are analyzed in memory and not stored.
Optional numeric organ_scores feed compose_organ_health when present.
"""

from __future__ import annotations

from typing import Any

from PIL import Image, ImageFilter

TEACHING_TAG = "教學示範，非診斷"

# Static teaching note (web shows under stool/urine result; no checkbox questionnaire).
DYE_CONFUSION_NOTE = (
    "火龍果, 紅色蔬果, 豬血, 深綠色蔬菜, 鐵劑, 制酸劑, 鋇劑等皆有可能染色排泄物造成混淆"
)

STOOL_DANGER_NOTE = (
    "教育提醒（非診斷）：若排除飲食／藥物染色後，異常糞色超過約兩日，"
    "或合併發燒、暈眩、黃疸、尿如濃茶、劇痛、嘔吐、排便習慣明顯改變，請儘速就醫。"
)

URINE_CARE_NOTE = (
    "就醫參考（教育，非診斷）：若泡沫久不消＋水腫／高血壓／貧血疲倦等，"
    "請以尿液檢驗為準；目視≠檢驗。教學上約三分之一泡沫主訴確為蛋白尿。"
)

URINE_FOAM_TEACHING = (
    "泡沫教學：正常多為大小不一、約１～２分鐘消散（水柱衝擊、晨起濃縮、飲水少）；"
    "細密均勻且持續５～１０分鐘以上者，教學上提示蛋白尿／糖尿／泌尿道感染可能，"
    "西醫聯想腎／胰島素內分泌，中醫聯想精微下泄（腎脾）；"
    "若尿黃且口乾口苦，教學上亦可聯想肝膽／膀胱濕熱。"
)

URINE_FOAM_V1_LIMIT = (
    "泡沫時序限制（v1）：本版僅單張畫面估算泡沫面積與粗細；"
    "臨床教學上「持續５～１０分鐘以上」需 t=0 與 t≈5min 兩張才能量半衰期，尚未實測衰減。"
)

URINE_PHONE_LIMIT = (
    "取景限制：馬桶上方手機拍攝易受水深／稀釋／反光影響；白平衡以畫面近白瓷磚／亮點作軟參考，"
    "並排除高光眩光；結果僅供教學色調示範，不能取代檢驗。"
)

# Steatorrhea teaching score (v1): specular + water texture + pale Lab + float split.
# Soft image cues only — not depth sensing, not medical diagnosis.
STEATORRHEA_W_SPECULAR = 0.35
STEATORRHEA_W_WATER = 0.20
STEATORRHEA_W_PALE_LAB = 0.30
STEATORRHEA_W_FLOAT = 0.15
STEATORRHEA_SCORE_THRESHOLD = 0.48

STEATORRHEA_TEACHING = (
    "胰臟、膽囊、小腸；脂肪消化不良／膽汁不足可能；酸臭易浮水面；"
    "高油脂飲食干擾；教學示範，非診斷"
)

STEATORRHEA_FLOAT_NOTE = (
    "浮水／水面線（軟啟發式）：上半部較亮且邊緣能量較高時略加分；"
    "僅為教學對照，非深度或浮力感測"
)

STOOL_CONFOUNDER_LABELS = {
    "pitaya": "火龍果／紅色蔬果",
    "pig_blood": "豬血／血品",
    "dark_greens": "深綠色蔬菜",
    "iron": "鐵劑",
    "antacid": "制酸劑／鋇劑",
    "bismuth": "鉍劑",
    "oily": "油膩飲食",
    "antibiotics": "抗生素",
}

URINE_CONFOUNDER_LABELS = {
    "pitaya": "火龍果／甜菜",
    "beet": "甜菜",
    "b_vitamins": "Ｂ群維生素",
    "drug_stain": "藥物染色",
}

# Medical-style urine teaching palette (CIELAB centers) + HSV soft gates.
# Names: transparent / pale yellow / dehydrated / tea / bilirubin / hematuria.
URINE_PALETTE = {
    "clear_colorless": (90.0, 0.0, 5.0),       # transparent
    "pale_goose_yellow": (80.0, 0.0, 25.0),    # pale yellow
    "deep_yellow": (67.0, 5.0, 50.0),          # dehydrated
    "dark_tea": (38.0, 18.0, 30.0),            # tea / cola
    "bilirubin": (48.0, 20.0, 48.0),           # bilirubin orange-brown
    "red_pink": (55.0, 28.0, 8.0),             # hematuria
    "milky_cloudy": (70.0, 0.0, 8.0),
}
URINE_OUTSIDE_PALETTE_DE00 = 18.0
URINE_PALETTE_LABELS = {
    "clear_colorless": "透明無色",
    "pale_goose_yellow": "淡／鵝黃色",
    "deep_yellow": "深黃色（脫水）",
    "dark_tea": "濃茶／可樂色",
    "bilirubin": "膽紅素橘褐",
    "red_pink": "紅色／粉紅色（血尿）",
    "milky_cloudy": "乳白色／混濁",
}
# Soft HSV gates (H degrees, S, V) — dual-space confirm beside Lab.
URINE_HSV_GATES = {
    "clear_colorless": {"s_max": 0.18, "v_min": 0.72},
    "pale_goose_yellow": {"h_lo": 35.0, "h_hi": 75.0, "s_lo": 0.12, "s_hi": 0.55, "v_min": 0.55},
    "deep_yellow": {"h_lo": 30.0, "h_hi": 70.0, "s_lo": 0.28, "s_hi": 0.85, "v_lo": 0.35, "v_hi": 0.78},
    "dark_tea": {"h_lo": 15.0, "h_hi": 55.0, "s_lo": 0.25, "v_max": 0.55},
    "bilirubin": {"h_lo": 18.0, "h_hi": 55.0, "s_lo": 0.35, "v_lo": 0.30, "v_hi": 0.70},
    "red_pink": {"h_lo": 330.0, "h_hi": 25.0, "s_lo": 0.22, "v_min": 0.35},  # wrap hue
    "milky_cloudy": {"s_max": 0.22, "v_lo": 0.45, "v_hi": 0.88},
}

# Stool teaching palette centers — off-palette must NOT force 黃褐／正常.
STOOL_PALETTE = {
    "black_tarry": (12.0, 1.0, 2.0),
    "clay_gray": (78.0, 0.0, 6.0),
    "bright_dark_red": (40.0, 32.0, 14.0),
    "dark_green": (38.0, -10.0, 18.0),
    "normal_yellow_brown": (48.0, 12.0, 32.0),
    "pale_oily": (66.0, 3.0, 30.0),
}
STOOL_OUTSIDE_PALETTE_DE = 22.0
STOOL_PALETTE_LABELS = {
    "black_tarry": "黑色／瀝青色",
    "clay_gray": "灰白色／陶土色",
    "bright_dark_red": "鮮紅色／暗紅色",
    "dark_green": "墨綠色／深綠色",
    "normal_yellow_brown": "黃褐色／金黃色",
    "pale_oily": "淡黃色／帶油光",
}


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _variance(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / len(values)


def _lab_pixels(image: Image.Image, max_side: int = 160) -> list[tuple[float, float, float]]:
    """Pillow LAB → CIELAB (same mapping as analysis.rgb_to_lab_pixels)."""
    work = image.convert("RGB")
    largest = max(work.size)
    if largest > max_side:
        scale = max_side / float(largest)
        work = work.resize(
            (max(1, int(round(work.size[0] * scale))), max(1, int(round(work.size[1] * scale)))),
            Image.Resampling.BILINEAR,
        )
    lab = work.convert("LAB")
    return [(L * 100.0 / 255.0, a - 128.0, b - 128.0) for L, a, b in lab.getdata()]


def _hsv_pixels(image: Image.Image, max_side: int = 160) -> list[tuple[float, float, float]]:
    work = image.convert("RGB")
    largest = max(work.size)
    if largest > max_side:
        scale = max_side / float(largest)
        work = work.resize(
            (max(1, int(round(work.size[0] * scale))), max(1, int(round(work.size[1] * scale)))),
            Image.Resampling.BILINEAR,
        )
    hsv = work.convert("HSV")
    return [(h * 360.0 / 255.0, s / 255.0, v / 255.0) for h, s, v in hsv.getdata()]


def _dominant_hex(image: Image.Image) -> str:
    from collections import Counter

    work = image.convert("RGB")
    largest = max(work.size)
    if largest > 80:
        scale = 80 / float(largest)
        work = work.resize(
            (max(1, int(round(work.size[0] * scale))), max(1, int(round(work.size[1] * scale)))),
            Image.Resampling.BILINEAR,
        )
    quantized = [((r // 16) * 16, (g // 16) * 16, (b // 16) * 16) for r, g, b in work.getdata()]
    (r, g, b), _ = Counter(quantized).most_common(1)[0]
    return f"#{r:02x}{g:02x}{b:02x}"


def _delta_e76(lab1: tuple[float, float, float], lab2: tuple[float, float, float]) -> float:
    return (
        (lab1[0] - lab2[0]) ** 2 + (lab1[1] - lab2[1]) ** 2 + (lab1[2] - lab2[2]) ** 2
    ) ** 0.5


def _delta_e00(lab1: tuple[float, float, float], lab2: tuple[float, float, float]) -> float:
    """CIEDE2000 (ΔE00) — teaching palette distance for urine/stool soft match."""
    import math

    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    kL = kC = kH = 1.0
    c1 = math.sqrt(a1 * a1 + b1 * b1)
    c2 = math.sqrt(a2 * a2 + b2 * b2)
    c_bar = (c1 + c2) / 2.0
    c_bar7 = c_bar ** 7
    g = 0.5 * (1.0 - math.sqrt(c_bar7 / (c_bar7 + 25.0 ** 7)))
    a1p = (1.0 + g) * a1
    a2p = (1.0 + g) * a2
    c1p = math.sqrt(a1p * a1p + b1 * b1)
    c2p = math.sqrt(a2p * a2p + b2 * b2)
    h1p = 0.0 if (a1p == 0 and b1 == 0) else math.degrees(math.atan2(b1, a1p)) % 360.0
    h2p = 0.0 if (a2p == 0 and b2 == 0) else math.degrees(math.atan2(b2, a2p)) % 360.0
    dLp = L2 - L1
    dCp = c2p - c1p
    if c1p * c2p == 0:
        dhp = 0.0
    else:
        raw = h2p - h1p
        if raw > 180:
            raw -= 360
        elif raw < -180:
            raw += 360
        dhp = raw
    dHp = 2.0 * math.sqrt(c1p * c2p) * math.sin(math.radians(dhp) / 2.0)
    L_bar = (L1 + L2) / 2.0
    C_bar_p = (c1p + c2p) / 2.0
    if c1p * c2p == 0:
        H_bar = h1p + h2p
    else:
        if abs(h1p - h2p) > 180:
            H_bar = (h1p + h2p + 360.0) / 2.0 if (h1p + h2p) < 360 else (h1p + h2p - 360.0) / 2.0
        else:
            H_bar = (h1p + h2p) / 2.0
    t = (
        1.0
        - 0.17 * math.cos(math.radians(H_bar - 30.0))
        + 0.24 * math.cos(math.radians(2.0 * H_bar))
        + 0.32 * math.cos(math.radians(3.0 * H_bar + 6.0))
        - 0.20 * math.cos(math.radians(4.0 * H_bar - 63.0))
    )
    sL = 1.0 + (0.015 * (L_bar - 50.0) ** 2) / math.sqrt(20.0 + (L_bar - 50.0) ** 2)
    sC = 1.0 + 0.045 * C_bar_p
    sH = 1.0 + 0.015 * C_bar_p * t
    delta_theta = 30.0 * math.exp(-(((H_bar - 275.0) / 25.0) ** 2))
    c_bar_p7 = C_bar_p ** 7
    rC = 2.0 * math.sqrt(c_bar_p7 / (c_bar_p7 + 25.0 ** 7))
    rT = -math.sin(math.radians(2.0 * delta_theta)) * rC
    return math.sqrt(
        (dLp / (kL * sL)) ** 2
        + (dCp / (kC * sC)) ** 2
        + (dHp / (kH * sH)) ** 2
        + rT * (dCp / (kC * sC)) * (dHp / (kH * sH))
    )


def _lab_from_roi(
    image: Image.Image,
    *,
    prefer_dark_cluster: bool = False,
) -> tuple[float, float, float, dict[str, Any]]:
    """Median CIELAB of circle-crop pixels; soft white-ref WB; drop specular (high L / low S).

    When prefer_dark_cluster=True (stool), ignore porcelain/water and yellow-guide
    pixels so a black stool on a bright toilet is not diluted to 黃褐色.
    """
    work = image.convert("RGB")
    rgb = list(work.getdata())
    whites: list[tuple[int, int, int]] = []
    for r, g, b in rgb:
        peak = max(r, g, b)
        low = min(r, g, b)
        if peak < 180:
            continue
        sat = 0.0 if peak <= 0 else (peak - low) / float(peak)
        # Porcelain-like / near-white soft ref
        if sat <= 0.12 and peak >= 200:
            whites.append((r, g, b))
    white_ref = None
    if len(whites) >= max(40, len(rgb) // 40):
        wr = _median([p[0] for p in whites])
        wg = _median([p[1] for p in whites])
        wb = _median([p[2] for p in whites])
        white_ref = (wr, wg, wb)
        peak_gain = max(0.85, min(1.25, 235.0 / max(wr, wg, wb, 1.0)))
        mean_w = (wr + wg + wb) / 3.0
        gr = max(0.85, min(1.25, mean_w / max(wr, 1.0))) * peak_gain
        gg = max(0.85, min(1.25, mean_w / max(wg, 1.0))) * peak_gain
        gb = max(0.85, min(1.25, mean_w / max(wb, 1.0))) * peak_gain
        adjusted = [
            (
                min(255, int(round(r * gr))),
                min(255, int(round(g * gg))),
                min(255, int(round(b * gb))),
            )
            for r, g, b in rgb
        ]
        work = Image.new("RGB", work.size)
        work.putdata(adjusted)

    lab = _lab_pixels(work, max_side=max(work.size) or 1)
    hsv = _hsv_pixels(work, max_side=max(work.size) or 1)
    rgb2 = list(work.getdata())
    kept: list[tuple[float, float, float]] = []
    for (r, g, b), (L, a, bb), (_h, s, _v) in zip(rgb2, lab, hsv):
        # Specular / glare: very high L or very bright low-sat
        if max(r, g, b) >= 245 and min(r, g, b) >= 220:
            continue
        if L >= 92 and abs(a) < 4 and abs(bb) < 6:
            continue
        if L >= 88 and s <= 0.08:
            continue
        if prefer_dark_cluster:
            chroma = (a * a + bb * bb) ** 0.5
            # Drop toilet porcelain / water and yellow UI ring contamination.
            if L >= 68 and chroma < 18:
                continue
            if L >= 62 and chroma < 10:
                continue
            if L >= 55 and bb > 28 and a > 8 and s > 0.35:
                # Saturated yellow (guide ring / urine splash), not stool body.
                continue
        kept.append((L, a, bb))
    if not kept:
        kept = [(p[0], p[1], p[2]) for p in lab]
    cluster = kept
    cluster_mode = "all"
    if prefer_dark_cluster and kept:
        dark = [p for p in kept if p[0] < 40]
        mid = [p for p in kept if p[0] < 55]
        need = max(60, len(kept) // 12)
        if len(dark) >= need:
            cluster = dark
            cluster_mode = "dark"
        elif len(mid) >= need:
            cluster = mid
            cluster_mode = "mid"
        elif _variance([p[0] for p in kept]) > 180:
            # Bimodal porcelain+stool: use darkest quartile.
            ordered = sorted(kept, key=lambda p: p[0])
            q = max(40, len(ordered) // 4)
            cluster = ordered[:q]
            cluster_mode = "dark_quartile"
    kept_l = [p[0] for p in cluster]
    kept_a = [p[1] for p in cluster]
    kept_b = [p[2] for p in cluster]
    med = (_median(kept_l), _median(kept_a), _median(kept_b))
    meta = {
        "pixels_used": len(kept_l),
        "cluster_mode": cluster_mode,
        "white_ref": (
            None
            if white_ref is None
            else {
                "r": round(white_ref[0], 1),
                "g": round(white_ref[1], 1),
                "b": round(white_ref[2], 1),
            }
        ),
        "L": round(med[0], 1),
        "a_star": round(med[1], 1),
        "b_star": round(med[2], 1),
        "L_var": round(_variance(kept_l), 2),
    }
    return med[0], med[1], med[2], meta


def _surrounding_water_a_bloom(image: Image.Image) -> dict[str, Any]:
    """Ring a* vs stool core: pink water bloom → fresh blood more likely than diet pigment."""
    work = image.convert("RGB").resize((96, 96), Image.Resampling.BILINEAR)
    w, h = work.size
    cx0, cy0, cx1, cy1 = int(w * 0.32), int(h * 0.32), int(w * 0.68), int(h * 0.68)
    center: list[tuple[int, int, int]] = []
    ring: list[tuple[int, int, int]] = []
    pixels = work.load()
    for y in range(h):
        for x in range(w):
            pix = pixels[x, y]
            if cx0 <= x < cx1 and cy0 <= y < cy1:
                center.append(pix)
            else:
                ring.append(pix)
    empty = {
        "pink_bloom": False,
        "clear_water": True,
        "da_ring_minus_center": 0.0,
        "ring_a": 0.0,
        "center_a": 0.0,
    }
    if len(center) < 20 or len(ring) < 20:
        return empty

    def median_lab_a(samples: list[tuple[int, int, int]]) -> float:
        patch = Image.new("RGB", (len(samples), 1))
        patch.putdata(samples)
        labs = _lab_pixels(patch, max_side=max(len(samples), 1))
        return _median([item[1] for item in labs])

    center_a = median_lab_a(center)
    ring_a = median_lab_a(ring)
    da = ring_a - center_a
    c_l = _median([max(p) for p in center])
    r_l = _median([max(p) for p in ring])
    # Water usually lighter than stool core; skip if ring is darker debris.
    if r_l + 6 < c_l:
        return {
            **empty,
            "da_ring_minus_center": round(da, 2),
            "ring_a": round(ring_a, 2),
            "center_a": round(center_a, 2),
        }
    pink_bloom = da >= 8.0 and ring_a >= 6.0
    clear_water = (not pink_bloom) and abs(da) < 5.0 and ring_a < 8.0
    return {
        "pink_bloom": pink_bloom,
        "clear_water": clear_water,
        "da_ring_minus_center": round(da, 2),
        "ring_a": round(ring_a, 2),
        "center_a": round(center_a, 2),
    }


def _surrounding_water_reddish(image: Image.Image) -> bool:
    return bool(_surrounding_water_a_bloom(image).get("pink_bloom"))


def _black_surface_metrics(image: Image.Image) -> dict[str, Any]:
    """GLCM-like contrast + specular: glossy tar vs matte diet/iron black (teaching)."""
    work = image.convert("RGB")
    largest = max(work.size)
    if largest > 128:
        scale = 128 / float(largest)
        work = work.resize(
            (max(1, int(round(work.size[0] * scale))), max(1, int(round(work.size[1] * scale)))),
            Image.Resampling.BILINEAR,
        )
    gray = work.convert("L")
    # Keep darker stool-like pixels for texture (exclude porcelain).
    mask = []
    for L, _a, _b in _lab_pixels(work, max_side=max(work.size) or 1):
        mask.append(L < 48)
    vals = list(gray.getdata())
    w, h = gray.size
    # Horizontal neighbor co-occurrence contrast / energy (1-px offset, 8-level quantize).
    levels = 8
    bins = [[0] * levels for _ in range(levels)]
    pairs = 0
    for y in range(h):
        for x in range(w - 1):
            i = y * w + x
            if not mask[i] or not mask[i + 1]:
                continue
            g0 = min(levels - 1, vals[i] * levels // 256)
            g1 = min(levels - 1, vals[i + 1] * levels // 256)
            bins[g0][g1] += 1
            bins[g1][g0] += 1
            pairs += 2
    contrast = 0.0
    energy = 0.0
    if pairs > 0:
        for i in range(levels):
            for j in range(levels):
                p = bins[i][j] / float(pairs)
                contrast += p * ((i - j) ** 2)
                energy += p * p
    spec = _specular_oil_metrics(work)
    # Glossy tar: higher specular + moderate contrast; matte iron/diet: low specular.
    glossy_score = max(
        0.0,
        min(
            1.0,
            0.55 * float(spec.get("specular_score") or 0.0)
            + 0.45 * min(1.0, contrast / 6.0),
        ),
    )
    surface = "glossy_tar" if glossy_score >= 0.42 else "matte"
    return {
        "glcm_contrast": round(contrast, 3),
        "glcm_energy": round(energy, 4),
        "specular_score": spec.get("specular_score"),
        "specular_ratio": spec.get("specular_ratio"),
        "glossy_score": round(glossy_score, 3),
        "surface": surface,
        "pairs": pairs,
    }


def _laplacian_var(gray: Image.Image) -> float:
    """Approx Laplacian variance via FIND_EDGES energy (Pillow has no cv2 Laplacian)."""
    edges = gray.filter(ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=1))
    vals = [p / 255.0 for p in edges.getdata()]
    return _variance(vals)


def _turbidity_heuristic(image: Image.Image) -> dict[str, Any]:
    """Turbidity via luminance std + Laplacian variance (milky/cloudy teaching cue)."""
    gray = image.convert("L").resize((96, 96), Image.Resampling.BILINEAR)
    vals = [p / 255.0 for p in gray.getdata()]
    lum_std = _variance(vals) ** 0.5
    lap_var = _laplacian_var(gray)
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_vals = [p / 255.0 for p in edges.getdata()]
    edge_mean = sum(edge_vals) / max(1, len(edge_vals))
    # Cloudy: elevated std with muted sharp edges / mid Laplacian energy.
    cloudy = lum_std >= 0.085 and lap_var <= 0.012 and edge_mean <= 0.14
    return {
        "local_var": round(_variance(vals), 4),
        "lum_std": round(lum_std, 4),
        "laplacian_var": round(lap_var, 5),
        "edge_mean": round(edge_mean, 4),
        "cloudy": cloudy,
    }


def _foam_glcm_and_roundness(
    foam_xy: list[tuple[int, int]],
    w: int,
    h: int,
) -> dict[str, Any]:
    """GLCM-like contrast on foam mask + Hough-ish roundness of foam blobs."""
    if not foam_xy:
        return {
            "glcm_contrast": 0.0,
            "glcm_energy": 0.0,
            "mean_roundness": 0.0,
            "blob_count": 0,
        }
    mask = [[0] * w for _ in range(h)]
    for x, y in foam_xy:
        if 0 <= x < w and 0 <= y < h:
            mask[y][x] = 1
    levels = 2
    bins = [[0, 0], [0, 0]]
    pairs = 0
    for y in range(h):
        for x in range(w - 1):
            g0 = mask[y][x]
            g1 = mask[y][x + 1]
            bins[g0][g1] += 1
            bins[g1][g0] += 1
            pairs += 2
    contrast = 0.0
    energy = 0.0
    if pairs > 0:
        for i in range(levels):
            for j in range(levels):
                p = bins[i][j] / float(pairs)
                contrast += p * ((i - j) ** 2)
                energy += p * p
    # Connected components → roundness (4πA/P²); foam bubbles ≈ round.
    visited = [[False] * w for _ in range(h)]
    roundnesses: list[float] = []
    foam_set = set(foam_xy)
    for sx, sy in foam_xy:
        if visited[sy][sx]:
            continue
        stack = [(sx, sy)]
        visited[sy][sx] = True
        cells: list[tuple[int, int]] = []
        while stack:
            x, y = stack.pop()
            cells.append((x, y))
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if (nx, ny) in foam_set and not visited[ny][nx]:
                    visited[ny][nx] = True
                    stack.append((nx, ny))
        if len(cells) < 4:
            continue
        peri = 0
        for x, y in cells:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if (x + dx, y + dy) not in foam_set:
                    peri += 1
        area = float(len(cells))
        if peri <= 0:
            continue
        roundness = min(1.5, (12.566 * area) / (peri * peri))  # 4π≈12.566
        roundnesses.append(roundness)
    mean_r = sum(roundnesses) / len(roundnesses) if roundnesses else 0.0
    return {
        "glcm_contrast": round(contrast, 4),
        "glcm_energy": round(energy, 4),
        "mean_roundness": round(mean_r, 3),
        "blob_count": len(roundnesses),
    }


def _foam_metrics(
    image: Image.Image,
    prior_frames: list[Image.Image] | None = None,
) -> dict[str, Any]:
    """Foam area ratio + GLCM/Hough-ish granularity; optional multi-frame decay."""
    work = image.convert("RGB").resize((128, 128), Image.Resampling.BILINEAR)
    hsv = work.convert("HSV")
    lab = work.convert("LAB")
    edges = work.convert("L").filter(ImageFilter.FIND_EDGES)
    w, h = work.size
    foam_xy: list[tuple[int, int]] = []
    hsv_data = list(hsv.getdata())
    lab_data = list(lab.getdata())
    edge_data = list(edges.getdata())
    for i, ((_hh, s, v), (Lraw, _a, _b), e) in enumerate(zip(hsv_data, lab_data, edge_data)):
        L = Lraw * 100.0 / 255.0
        sat = s / 255.0
        val = v / 255.0
        if L < 72 or sat > 0.28 or val < 0.55:
            continue
        if e < 18 and L < 88:
            continue
        foam_xy.append((i % w, i // w))
    total = w * h
    ratio = len(foam_xy) / float(total) if total else 0.0
    tex = _foam_glcm_and_roundness(foam_xy, w, h)
    granularity = "none"
    if foam_xy:
        foam_set = set(foam_xy)
        neighbors = 0
        for x, y in foam_xy:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if (x + dx, y + dy) in foam_set:
                    neighbors += 1
        dens = neighbors / max(1, len(foam_xy))
        # Fine dense: high neighbor dens + rounder blobs + higher GLCM energy on mask.
        if dens >= 2.2 and ratio >= 0.08 and tex["mean_roundness"] >= 0.35:
            granularity = "fine_dense"
        elif dens >= 2.0 and ratio >= 0.08:
            granularity = "fine_dense"
        elif dens >= 1.2 or tex["blob_count"] >= 6:
            granularity = "mixed"
        else:
            granularity = "coarse_sparse"
    # Optional multi-frame decay: ratio drop between first and last frame.
    decay_measured = False
    decay_half_life_hint = None
    if prior_frames and len(prior_frames) >= 1:
        ratios = [ratio]
        for fr in prior_frames[:3]:
            try:
                ratios.append(float(_foam_metrics(fr).get("foam_ratio") or 0.0))
            except Exception:
                continue
        if len(ratios) >= 2 and ratios[0] > 0.02:
            decay_measured = True
            drop = ratios[0] - ratios[-1]
            decay_half_life_hint = "fast" if drop >= ratios[0] * 0.5 else "slow"
    persistent_alert = granularity == "fine_dense" and ratio >= 0.12
    if decay_measured and decay_half_life_hint == "slow" and ratio >= 0.08:
        persistent_alert = True
    return {
        "foam_ratio": round(ratio, 4),
        "granularity": granularity,
        "persistent_foam_teaching_alert": persistent_alert,
        "decay_measured": decay_measured,
        "decay_half_life_hint": decay_half_life_hint,
        "glcm_contrast": tex["glcm_contrast"],
        "glcm_energy": tex["glcm_energy"],
        "mean_roundness": tex["mean_roundness"],
        "blob_count": tex["blob_count"],
    }


def _pale_lab_fat_match(L: float, a: float, b: float) -> float:
    """Soft 0–1 match for fat-pale stool: L>60, b>+25, a≈-2..+8 (teaching band)."""
    # Soft ramps around the preferred box
    l_score = 0.0
    if L >= 60:
        l_score = min(1.0, (L - 55.0) / 10.0)  # ramp 55→65
    elif L >= 50:
        l_score = (L - 50.0) / 10.0 * 0.45

    b_score = 0.0
    if b >= 25:
        b_score = min(1.0, (b - 18.0) / 12.0)  # ramp ~18→30
    elif b >= 12:
        b_score = (b - 12.0) / 13.0 * 0.5

    if -2.0 <= a <= 8.0:
        a_score = 1.0
    elif -5.0 <= a < -2.0:
        a_score = (a + 5.0) / 3.0
    elif 8.0 < a <= 12.0:
        a_score = (12.0 - a) / 4.0
    else:
        a_score = 0.0

    return max(0.0, min(1.0, 0.40 * l_score + 0.40 * b_score + 0.20 * a_score))


def _stool_pale_oily_class(*, approx: bool = False) -> dict[str, Any]:
    suffix = "（近似）" if approx else ""
    return {
        "id": "pale_oily",
        "label": f"淡黃色／帶油光{suffix}",
        "organs": "胰臟／膽囊／小腸",
        "organ_keys": ["gallbladder", "spleen", "small_intestine"],
        "hint": "脂肪消化不良／膽汁不足可能；酸臭易浮水面（教學）",
        "confounders": "高油脂飲食",
        "abnormal": True,
        "health_score": 5,
    }


def _specular_oil_metrics(image: Image.Image) -> dict[str, Any]:
    """HSV high-V / low-S specular highlights → oily sheen density on stool surface."""
    work = image.convert("RGB")
    largest = max(work.size)
    if largest > 160:
        scale = 160 / float(largest)
        work = work.resize(
            (max(1, int(round(work.size[0] * scale))), max(1, int(round(work.size[1] * scale)))),
            Image.Resampling.BILINEAR,
        )
    hsv = work.convert("HSV")
    total = work.size[0] * work.size[1]
    if total <= 0:
        return {"specular_ratio": 0.0, "specular_score": 0.0, "highlight_count": 0}
    hard = 0
    soft = 0
    for _h, s, v in hsv.getdata():
        # Hard specular: V>0.9 (~230/255), S<0.12 (~30/255)
        if v >= 230 and s <= 30:
            hard += 1
        # Soft oil sheen (half weight): still bright / low-sat
        elif v >= 217 and s <= 46:
            soft += 1
    highlights = hard + 0.5 * soft
    ratio = highlights / float(total)
    # ~5% effective highlight area → near-full specular weight
    score = max(0.0, min(1.0, ratio / 0.05))
    return {
        "specular_ratio": round(ratio, 4),
        "specular_score": round(score, 4),
        "highlight_count": int(round(highlights)),
        "hard_count": hard,
        "soft_count": soft,
    }


def _water_oil_texture_metrics(image: Image.Image) -> dict[str, Any]:
    """Ring outside denser stool core: gradient / high-frequency energy as oil-film proxy (no OpenCV)."""
    work = image.convert("RGB").resize((96, 96), Image.Resampling.BILINEAR)
    gray = work.convert("L")
    w, h = gray.size
    # Dense core ≈ darker / lower-L central disk; surround = outside ~0.55 radius
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    max_r = ((w / 2.0) ** 2 + (h / 2.0) ** 2) ** 0.5
    core_r = 0.42 * max_r
    ring_outer = 0.92 * max_r

    lum = list(gray.getdata())
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_vals = list(edges.getdata())
    # High-pass via |pixel - box blur|
    blur = gray.filter(ImageFilter.BoxBlur(2))
    blur_vals = list(blur.getdata())

    ring_edge: list[float] = []
    ring_hf: list[float] = []
    ring_lum: list[float] = []
    core_lum: list[float] = []
    for y in range(h):
        for x in range(w):
            i = y * w + x
            dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            if dist <= core_r:
                core_lum.append(lum[i] / 255.0)
            elif dist <= ring_outer:
                ring_edge.append(edge_vals[i] / 255.0)
                ring_hf.append(abs(lum[i] - blur_vals[i]) / 255.0)
                ring_lum.append(lum[i] / 255.0)

    if len(ring_edge) < 30:
        return {
            "water_texture_score": 0.0,
            "ring_edge_mean": 0.0,
            "ring_hf_mean": 0.0,
            "core_L_mean": 0.0,
        }

    edge_mean = sum(ring_edge) / len(ring_edge)
    hf_mean = sum(ring_hf) / len(ring_hf)
    core_mean = (sum(core_lum) / len(core_lum)) if core_lum else 0.0
    ring_L = sum(ring_lum) / len(ring_lum)
    # Prefer visible water surround (not much darker than core)
    surround_brighter = 1.0 if ring_L + 0.02 >= core_mean * 0.85 else 0.55

    # Typical toilet-water oil film: edge_mean ~0.04–0.14, hf ~0.02–0.08
    raw = 0.55 * min(1.0, edge_mean / 0.10) + 0.45 * min(1.0, hf_mean / 0.055)
    score = max(0.0, min(1.0, raw * surround_brighter))
    return {
        "water_texture_score": round(score, 4),
        "ring_edge_mean": round(edge_mean, 4),
        "ring_hf_mean": round(hf_mean, 4),
        "core_L_mean": round(core_mean, 4),
    }


def _float_waterline_metrics(image: Image.Image) -> dict[str, Any]:
    """Upper vs lower ROI: brighter/sharper top bumps float score (teaching heuristic, not depth)."""
    work = image.convert("RGB").resize((96, 96), Image.Resampling.BILINEAR)
    gray = work.convert("L")
    w, h = gray.size
    mid = h // 2
    lum = list(gray.getdata())
    edges = list(gray.filter(ImageFilter.FIND_EDGES).getdata())

    def half_stats(y0: int, y1: int) -> tuple[float, float]:
        ls: list[float] = []
        es: list[float] = []
        for y in range(y0, y1):
            for x in range(w):
                i = y * w + x
                ls.append(lum[i] / 255.0)
                es.append(edges[i] / 255.0)
        if not ls:
            return 0.0, 0.0
        return sum(ls) / len(ls), sum(es) / len(es)

    up_L, up_e = half_stats(0, mid)
    lo_L, lo_e = half_stats(mid, h)
    dL = up_L - lo_L
    dE = up_e - lo_e
    # Soft: need upper brighter and/or sharper
    l_part = max(0.0, min(1.0, dL / 0.12))
    e_part = max(0.0, min(1.0, dE / 0.06))
    score = max(0.0, min(1.0, 0.65 * l_part + 0.35 * e_part))
    return {
        "float_score": round(score, 4),
        "upper_L": round(up_L, 4),
        "lower_L": round(lo_L, 4),
        "upper_edge": round(up_e, 4),
        "lower_edge": round(lo_e, 4),
        "note": STEATORRHEA_FLOAT_NOTE,
    }


def steatorrhea_score_v1(
    image: Image.Image,
    L: float,
    a: float,
    b: float,
) -> dict[str, Any]:
    """Lightweight oily/pale stool teaching score from circle ROI (PIL only, no ML).

    Score = 0.35*specular + 0.20*water_texture + 0.30*pale_lab + 0.15*float_split
    Trigger when Score >= 0.48 (v1 threshold).
    """
    specular = _specular_oil_metrics(image)
    water = _water_oil_texture_metrics(image)
    pale = _pale_lab_fat_match(L, a, b)
    float_m = _float_waterline_metrics(image)

    score = (
        STEATORRHEA_W_SPECULAR * specular["specular_score"]
        + STEATORRHEA_W_WATER * water["water_texture_score"]
        + STEATORRHEA_W_PALE_LAB * pale
        + STEATORRHEA_W_FLOAT * float_m["float_score"]
    )
    triggered = score >= STEATORRHEA_SCORE_THRESHOLD
    return {
        "score": round(score, 4),
        "threshold": STEATORRHEA_SCORE_THRESHOLD,
        "triggered": triggered,
        "weights": {
            "specular": STEATORRHEA_W_SPECULAR,
            "water_texture": STEATORRHEA_W_WATER,
            "pale_lab_match": STEATORRHEA_W_PALE_LAB,
            "float_split": STEATORRHEA_W_FLOAT,
        },
        "components": {
            "specular": specular,
            "water_texture": water,
            "pale_lab_match": round(pale, 4),
            "float_split": float_m,
        },
        "formula": (
            "Score = 0.35*specular + 0.20*water_texture + 0.30*pale_lab_match "
            "+ 0.15*float_split; trigger ≥ 0.48"
        ),
    }


def _nearest_stool_palette(L: float, a: float, b: float) -> tuple[str | None, float]:
    nearest_id: str | None = None
    nearest_de = 1e9
    for pid, center in STOOL_PALETTE.items():
        de = _delta_e76((L, a, b), center)
        if de < nearest_de:
            nearest_de = de
            nearest_id = pid
    return nearest_id, float(nearest_de)


def _stool_outside_palette_class(L: float, a: float, b: float) -> dict[str, Any]:
    nearest_id, nearest_de = _nearest_stool_palette(L, a, b)
    nearest_label = STOOL_PALETTE_LABELS.get(nearest_id or "", nearest_id or "未知")
    measured = f"測得 L*{L:.0f} a*{a:.0f} b*{b:.0f}"
    return {
        "id": "outside_palette",
        "label": "偏離教學色盤（無法對照已知糞色）",
        "organs": "未對照",
        "organ_keys": [],
        "hint": f"{measured}；最近教學色「{nearest_label}」ΔE≈{nearest_de:.0f}，不強制黃褐／正常",
        "confounders": "飲食／藥物染色、光線、取景",
        "abnormal": True,
        "health_score": 5,
        "far_from_palette": True,
        "palette_delta_e": round(nearest_de, 1),
        "nearest_palette_id": nearest_id,
        "measured_lab": {"L": round(L, 1), "a_star": round(a, 1), "b_star": round(b, 1)},
    }


def classify_stool_lab(L: float, a: float, b: float) -> dict[str, Any]:
    chroma = (a * a + b * b) ** 0.5

    if L < 20 and -2 <= a <= 5 and -2 <= b <= 8:
        return {
            "id": "black_tarry",
            "label": "黑色／瀝青色",
            "organs": "食道／胃／十二指腸",
            "organ_keys": ["stomach", "small_intestine"],
            "hint": "上消化道出血教學提示",
            "confounders": "血品食物、鐵劑、鉍劑",
            "abnormal": True,
            "health_score": 3,
        }
    if L > 70 and -3 <= a <= 5 and b < 12:
        return {
            "id": "clay_gray",
            "label": "灰白色／陶土色",
            "organs": "肝／膽道／胰",
            "organ_keys": ["liver", "gallbladder", "spleen"],
            "hint": "膽汁排出受阻教學警示",
            "confounders": "鋇劑、制酸劑",
            "abnormal": True,
            "health_score": 3,
        }
    if 25 <= L <= 55 and a > 25 and 5 <= b <= 25 and a >= b + 5:
        return {
            "id": "bright_dark_red",
            "label": "鮮紅色／暗紅色",
            "organs": "結腸／直腸／肛門",
            "organ_keys": ["large_intestine"],
            "hint": "下消化道出血教學提示",
            "confounders": "紅色蔬果（如火龍果）",
            "abnormal": True,
            "health_score": 3,
        }
    if 25 <= L <= 50 and a < -5 and 10 <= b <= 30:
        return {
            "id": "dark_green",
            "label": "墨綠色／深綠色",
            "organs": "小腸／大腸",
            "organ_keys": ["small_intestine", "large_intestine"],
            "hint": "感染／發炎／通過過快教學提示",
            "confounders": "深綠色蔬菜、鐵劑、抗生素",
            "abnormal": True,
            "health_score": 5,
        }
    if 35 <= L <= 68 and 5 <= a <= 20 and 20 <= b <= 50 and b >= a + 5:
        return {
            "id": "normal_yellow_brown",
            "label": "黃褐色／金黃色",
            "organs": "肝膽膽汁正常、腸道通暢（教學）",
            "organ_keys": ["liver", "gallbladder", "large_intestine", "small_intestine"],
            "hint": "相對健康糞色教學示範",
            "confounders": "一般飲食",
            "abnormal": False,
            "health_score": 9,
        }
    # Fat-pale Lab band only (steatorrhea teaching): L>60, b>+25, a≈-2..+6 (low a*).
    # Do NOT use a wide mid-L pale band — that locked solid yellow-brown → 淡黃色帶油光.
    if L > 62 and b > 28 and -2 <= a <= 6:
        return _stool_pale_oily_class()
    # Dark / tarry approximate — catch black stool diluted by toilet lighting.
    if L < 36 and chroma < 18:
        return {
            "id": "black_tarry",
            "label": "黑色／瀝青色（近似）",
            "organs": "食道／胃／十二指腸",
            "organ_keys": ["stomach", "small_intestine"],
            "hint": "上消化道出血教學提示",
            "confounders": "血品食物、鐵劑、鉍劑",
            "abnormal": True,
            "health_score": 3,
        }
    if L < 32:
        return {
            "id": "black_tarry",
            "label": "黑色／瀝青色（近似）",
            "organs": "食道／胃／十二指腸",
            "organ_keys": ["stomach", "small_intestine"],
            "hint": "上消化道出血教學提示",
            "confounders": "血品食物、鐵劑、鉍劑",
            "abnormal": True,
            "health_score": 3,
        }
    # Red approx: require a*>+20 and a*≥b* with b* not purple-negative.
    if a > 20 and a >= b and b > -5 and L < 70:
        return {
            "id": "bright_dark_red",
            "label": "鮮紅色／暗紅色（近似）",
            "organs": "結腸／直腸／肛門",
            "organ_keys": ["large_intestine"],
            "hint": "下消化道出血教學提示",
            "confounders": "紅色蔬果",
            "abnormal": True,
            "health_score": 3,
        }
    if a < -3 and b > 8:
        return {
            "id": "dark_green",
            "label": "墨綠色／深綠色（近似）",
            "organs": "小腸／大腸",
            "organ_keys": ["small_intestine", "large_intestine"],
            "hint": "感染／發炎／通過過快教學提示",
            "confounders": "深綠色蔬菜、鐵劑、抗生素",
            "abnormal": True,
            "health_score": 5,
        }
    if L > 65 and chroma < 16:
        return {
            "id": "clay_gray",
            "label": "灰白色／陶土色（近似）",
            "organs": "肝／膽道／胰",
            "organ_keys": ["liver", "gallbladder", "spleen"],
            "hint": "膽汁排出受阻教學警示",
            "confounders": "鋇劑、制酸劑",
            "abnormal": True,
            "health_score": 3,
        }
    # Soft near-match only when close to a known center — never invent 黃褐／正常.
    nearest_id, nearest_de = _nearest_stool_palette(L, a, b)
    # Prefer 黃褐 over 淡脂 when chroma is warm (a*≥5) even if nearest center is pale_oily.
    if 30 <= L <= 72 and a >= 5 and 18 <= b <= 52 and b >= a + 4:
        de_yb = _delta_e76((L, a, b), STOOL_PALETTE["normal_yellow_brown"])
        if de_yb <= 22.0:
            return {
                "id": "normal_yellow_brown",
                "label": "黃褐色／金黃色（近似）",
                "organs": "肝膽膽汁正常、腸道通暢（教學）",
                "organ_keys": ["liver", "gallbladder", "large_intestine", "small_intestine"],
                "hint": f"相對健康糞色教學示範（ΔE≈{de_yb:.0f}）",
                "confounders": "一般飲食",
                "abnormal": False,
                "health_score": 8,
                "palette_delta_e": round(de_yb, 1),
            }
    if nearest_id == "normal_yellow_brown" and nearest_de <= 14.0 and 30 <= L <= 70:
        return {
            "id": "normal_yellow_brown",
            "label": "黃褐色／金黃色（近似）",
            "organs": "肝膽膽汁正常、腸道通暢（教學）",
            "organ_keys": ["liver", "gallbladder", "large_intestine", "small_intestine"],
            "hint": f"相對健康糞色教學示範（ΔE≈{nearest_de:.0f}）",
            "confounders": "一般飲食",
            "abnormal": False,
            "health_score": 8,
            "palette_delta_e": round(nearest_de, 1),
        }
    if nearest_de <= STOOL_OUTSIDE_PALETTE_DE and nearest_id in {
        "black_tarry",
        "clay_gray",
        "bright_dark_red",
        "dark_green",
        "pale_oily",
    }:
        approx_map = {
            "black_tarry": (
                "黑色／瀝青色（近似）",
                "食道／胃／十二指腸",
                ["stomach", "small_intestine"],
                "上消化道出血教學提示",
                "血品食物、鐵劑、鉍劑",
                3,
            ),
            "clay_gray": (
                "灰白色／陶土色（近似）",
                "肝／膽道／胰",
                ["liver", "gallbladder", "spleen"],
                "膽汁排出受阻教學警示",
                "鋇劑、制酸劑",
                3,
            ),
            "bright_dark_red": (
                "鮮紅色／暗紅色（近似）",
                "結腸／直腸／肛門",
                ["large_intestine"],
                "下消化道出血教學提示",
                "紅色蔬果",
                3,
            ),
            "dark_green": (
                "墨綠色／深綠色（近似）",
                "小腸／大腸",
                ["small_intestine", "large_intestine"],
                "感染／發炎／通過過快教學提示",
                "深綠色蔬菜、鐵劑、抗生素",
                5,
            ),
        }
        if nearest_id == "pale_oily":
            hit = _stool_pale_oily_class(approx=True)
            hit["palette_delta_e"] = round(nearest_de, 1)
            return hit
        label, organs, keys, hint, conf, score = approx_map[nearest_id]
        return {
            "id": nearest_id,
            "label": label,
            "organs": organs,
            "organ_keys": keys,
            "hint": f"{hint}（ΔE≈{nearest_de:.0f}）",
            "confounders": conf,
            "abnormal": True,
            "health_score": score,
            "palette_delta_e": round(nearest_de, 1),
        }
    return _stool_outside_palette_class(L, a, b)


def _hsv_gate_ok(pid: str, h: float, s: float, v: float) -> bool:
    g = URINE_HSV_GATES.get(pid) or {}
    if not g:
        return True
    if "s_max" in g and s > float(g["s_max"]):
        return False
    if "s_lo" in g and s < float(g["s_lo"]):
        return False
    if "s_hi" in g and s > float(g["s_hi"]):
        return False
    if "v_min" in g and v < float(g["v_min"]):
        return False
    if "v_max" in g and v > float(g["v_max"]):
        return False
    if "v_lo" in g and v < float(g["v_lo"]):
        return False
    if "v_hi" in g and v > float(g["v_hi"]):
        return False
    if "h_lo" in g and "h_hi" in g:
        lo = float(g["h_lo"])
        hi = float(g["h_hi"])
        if lo <= hi:
            if not (lo <= h <= hi):
                return False
        else:
            # wrap (e.g. red 330–25)
            if not (h >= lo or h <= hi):
                return False
    return True


def _urine_class_payload(
    pid: str,
    *,
    approx: bool = False,
    de00: float = 0.0,
    far: bool = False,
) -> dict[str, Any]:
    labels = {
        "clear_colorless": (
            "透明無色",
            "飲水過多教學；若持續清澈且多尿、飲水不多，教學上聯想腦垂體／腎或腎陽虛",
            True,
            6,
            ["kidney", "bladder"],
        ),
        "pale_goose_yellow": (
            "淡／鵝黃色",
            "相對健康尿色教學示範",
            False,
            9 if not approx else 8,
            ["kidney", "bladder"],
        ),
        "deep_yellow": (
            "深黃色（脫水）",
            "脫水／內熱／心火旺教學提示",
            True,
            6,
            ["heart", "bladder", "kidney"],
        ),
        "dark_tea": (
            "濃茶／可樂色",
            "肝膽膽紅素教學，或劇烈運動後可樂色橫紋肌溶解／腎風險教學",
            True,
            3,
            ["liver", "gallbladder", "kidney"],
        ),
        "bilirubin": (
            "膽紅素橘褐",
            "肝膽膽紅素教學警示；需排除藥物／飲食染色",
            True,
            3,
            ["liver", "gallbladder"],
        ),
        "red_pink": (
            "紅色／粉紅色（血尿）",
            "血尿教學（腎／輸尿管／膀胱／攝護腺）；劇烈腰痛教學聯想結石，無痛則腫瘤警覺教學",
            True,
            3,
            ["kidney", "bladder"],
        ),
        "milky_cloudy": (
            "乳白色／混濁",
            "泌尿道感染／膿尿或結晶（痛風／結石）教學提示",
            True,
            5,
            ["bladder", "kidney"],
        ),
    }
    label, hint, abnormal, score, keys = labels[pid]
    if approx:
        label = f"{label}（近似）"
        hint = f"{hint}（ΔE00≈{de00:.0f}）"
    return {
        "id": pid,
        "label": label,
        "hint": hint,
        "abnormal": abnormal,
        "health_score": score,
        "organ_keys": keys,
        "palette_delta_e": round(de00, 1),
        "palette_delta_e00": round(de00, 1),
        "far_from_palette": far,
    }


def _urine_lab_hsv_from_roi(
    image: Image.Image,
) -> tuple[float, float, float, float, float, float, dict[str, Any]]:
    """Toilet-white WB; mask specular L*>95 & S<5%; median Lab+HSV of urine body ROI."""
    work = image.convert("RGB")
    rgb = list(work.getdata())
    whites: list[tuple[int, int, int]] = []
    for r, g, b in rgb:
        peak = max(r, g, b)
        low = min(r, g, b)
        if peak < 180:
            continue
        sat = 0.0 if peak <= 0 else (peak - low) / float(peak)
        if sat <= 0.12 and peak >= 200:
            whites.append((r, g, b))
    white_ref = None
    if len(whites) >= max(40, len(rgb) // 40):
        wr = _median([p[0] for p in whites])
        wg = _median([p[1] for p in whites])
        wb = _median([p[2] for p in whites])
        white_ref = (wr, wg, wb)
        peak_gain = max(0.85, min(1.25, 235.0 / max(wr, wg, wb, 1.0)))
        mean_w = (wr + wg + wb) / 3.0
        gr = max(0.85, min(1.25, mean_w / max(wr, 1.0))) * peak_gain
        gg = max(0.85, min(1.25, mean_w / max(wg, 1.0))) * peak_gain
        gb = max(0.85, min(1.25, mean_w / max(wb, 1.0))) * peak_gain
        adjusted = [
            (
                min(255, int(round(r * gr))),
                min(255, int(round(g * gg))),
                min(255, int(round(b * gb))),
            )
            for r, g, b in rgb
        ]
        work = Image.new("RGB", work.size)
        work.putdata(adjusted)

    ww, hh = work.size
    lab = _lab_pixels(work, max_side=max(ww, hh) or 1)
    hsv = _hsv_pixels(work, max_side=max(ww, hh) or 1)
    # Resize factors for index mapping if max_side shrinks.
    side = max(ww, hh)
    if side > max(ww, hh):  # unreachable; keep simple index on resized
        pass
    # Recompute on same resized work used by helpers.
    work_s = work
    largest = max(work.size)
    if largest > 160:
        scale = 160 / float(largest)
        work_s = work.resize(
            (max(1, int(round(work.size[0] * scale))), max(1, int(round(work.size[1] * scale)))),
            Image.Resampling.BILINEAR,
        )
        lab = _lab_pixels(work_s, max_side=max(work_s.size) or 1)
        hsv = _hsv_pixels(work_s, max_side=max(work_s.size) or 1)
    sw, sh = work_s.size
    kept_lab: list[tuple[float, float, float]] = []
    kept_hsv: list[tuple[float, float, float]] = []
    cx0, cy0, cx1, cy1 = int(sw * 0.18), int(sh * 0.18), int(sw * 0.82), int(sh * 0.82)
    for i, ((L, a, bb), (h, s, v)) in enumerate(zip(lab, hsv)):
        x = i % sw
        y = i // sw
        # Specular mask: L*>95 and S<5%
        if L > 95 and s < 0.05:
            continue
        if L >= 97 and s < 0.08:
            continue
        # Drop porcelain rim (outside soft ROI or ultra-white low chroma)
        chroma = (a * a + bb * bb) ** 0.5
        if L >= 92 and chroma < 8:
            continue
        in_body = cx0 <= x < cx1 and cy0 <= y < cy1
        if not in_body and not (L < 88 and chroma >= 6):
            continue
        kept_lab.append((L, a, bb))
        kept_hsv.append((h, s, v))
    if len(kept_lab) < 30:
        kept_lab = list(lab)
        kept_hsv = list(hsv)
    med_l = _median([p[0] for p in kept_lab])
    med_a = _median([p[1] for p in kept_lab])
    med_b = _median([p[2] for p in kept_lab])
    med_h = _median([p[0] for p in kept_hsv])
    med_s = _median([p[1] for p in kept_hsv])
    med_v = _median([p[2] for p in kept_hsv])
    meta = {
        "pixels_used": len(kept_lab),
        "cluster_mode": "urine_body",
        "white_ref": (
            None
            if white_ref is None
            else {
                "r": round(white_ref[0], 1),
                "g": round(white_ref[1], 1),
                "b": round(white_ref[2], 1),
            }
        ),
        "L": round(med_l, 1),
        "a_star": round(med_a, 1),
        "b_star": round(med_b, 1),
        "H": round(med_h, 1),
        "S": round(med_s, 3),
        "V": round(med_v, 3),
        "specular_mask": "L>95 & S<5%",
        "roi": "urine_body_center",
    }
    return med_l, med_a, med_b, med_h, med_s, med_v, meta


def classify_urine_lab(
    L: float,
    a: float,
    b: float,
    turbidity: dict[str, Any] | None = None,
    hsv: tuple[float, float, float] | None = None,
) -> dict[str, Any]:
    """Medical-style urine: dual CIELAB+HSV, ΔE00 to palette; off-palette if all ΔE00>thr."""
    chroma = (a * a + b * b) ** 0.5
    turb = turbidity or {}
    h = s = v = None
    if hsv is not None:
        h, s, v = float(hsv[0]), float(hsv[1]), float(hsv[2])

    distances: list[tuple[str, float]] = []
    for pid, center in URINE_PALETTE.items():
        de = _delta_e00((L, a, b), center)
        distances.append((pid, de))
    distances.sort(key=lambda t: t[1])
    nearest_id, nearest_de = distances[0]
    far_from_palette = nearest_de > URINE_OUTSIDE_PALETTE_DE00

    # Turbidity can promote milky even when Lab is pale.
    if turb.get("cloudy") and chroma <= 16 and 45 <= L <= 88:
        hit = _urine_class_payload("milky_cloudy", de00=nearest_de if nearest_id == "milky_cloudy" else _delta_e00((L, a, b), URINE_PALETTE["milky_cloudy"]))
        hit["via"] = "turbidity_laplacian_std"
        return hit

    def _hematuria_lab_ok() -> bool:
        # Require red-dominant with non-purple b* (avoid magenta → 血尿 lock).
        return 40 <= L <= 72 and a > 22 and -5 <= b < 16 and a >= abs(b) + 4

    # Magenta / blue-purple stain: never force hematuria.
    purple_stain = a > 15 and b < -12 and a + b < 20

    # If all ΔE00 above threshold → staining / off-palette (keep 無法對照 wording).
    if far_from_palette or purple_stain:
        if (not purple_stain) and _hematuria_lab_ok():
            return _urine_class_payload("red_pink", approx=True, de00=nearest_de, far=False)
        nearest_label = URINE_PALETTE_LABELS.get(nearest_id or "", nearest_id or "—")
        return {
            "id": "outside_palette",
            "label": "偏離教學色盤（無法對照已知尿色／可能染色）",
            "hint": (
                f"測得 L*{L:.0f} a*{a:.0f} b*{b:.0f}；最近「{nearest_label}」ΔE00≈{nearest_de:.0f}，"
                "超過門檻 → 教學上先排除火龍果／甜菜／Ｂ群／藥物染色，不強制套色"
            ),
            "abnormal": True,
            "health_score": 6,
            "organ_keys": ["kidney", "bladder"],
            "palette_delta_e": round(nearest_de, 1),
            "palette_delta_e00": round(nearest_de, 1),
            "far_from_palette": True,
            "nearest_palette_id": nearest_id,
            "measured_lab": {"L": round(L, 1), "a_star": round(a, 1), "b_star": round(b, 1)},
        }

    # Prefer nearest ΔE00 class; soft-confirm with HSV gate when available.
    for pid, de in distances:
        if de > URINE_OUTSIDE_PALETTE_DE00:
            break
        if pid == "red_pink" and not _hematuria_lab_ok():
            continue
        if h is not None and not _hsv_gate_ok(pid, h, s or 0.0, v or 0.0):
            continue
        approx = de > 10.0
        return _urine_class_payload(pid, approx=approx, de00=de, far=False)

    # HSV rejected nearest — still accept nearest Lab within threshold (except bad hematuria).
    if nearest_id == "red_pink" and not _hematuria_lab_ok():
        for pid, de in distances[1:]:
            if de > URINE_OUTSIDE_PALETTE_DE00:
                break
            return _urine_class_payload(pid, approx=True, de00=de, far=False)
        nearest_label = URINE_PALETTE_LABELS.get(nearest_id or "", nearest_id or "—")
        return {
            "id": "outside_palette",
            "label": "偏離教學色盤（無法對照已知尿色／可能染色）",
            "hint": (
                f"測得 L*{L:.0f} a*{a:.0f} b*{b:.0f}；最近「{nearest_label}」ΔE00≈{nearest_de:.0f}，"
                "不強制血尿／套色"
            ),
            "abnormal": True,
            "health_score": 6,
            "organ_keys": ["kidney", "bladder"],
            "palette_delta_e": round(nearest_de, 1),
            "palette_delta_e00": round(nearest_de, 1),
            "far_from_palette": True,
            "nearest_palette_id": nearest_id,
        }
    approx = nearest_de > 10.0
    return _urine_class_payload(nearest_id, approx=approx, de00=nearest_de, far=False)


def _organ_scores_from_keys(
    organ_keys: list[str],
    health_score: int,
    severe_gate: bool = False,
) -> dict[str, int]:
    """Map organ keys → *_score ints for compose_organ_health.

    Without severe_gate, teaching class scores of 1–3 are floored to 4 so stool/urine
    cannot reopen the severe band for quiet cohorts.
    """
    from .syndrome import ORGAN_META

    score = max(1, min(10, int(health_score)))
    if not severe_gate and score < 4:
        score = 4
    out: dict[str, int] = {}
    for organ in organ_keys:
        for key, _name, score_key, _pk in ORGAN_META:
            if key == organ:
                out[score_key] = score
                break
    return out


_CONFOUNDER_FREE_TIPS: dict[str, tuple[str, ...]] = {
    "pitaya": ("火龍", "紅色蔬"),
    "pig_blood": ("豬血", "血品"),
    "dark_greens": ("深綠",),
    "iron": ("鐵劑", "鐵片"),
    "antacid": ("制酸", "鋇"),
    "bismuth": ("鉍",),
    "oily": ("油脂", "油膩"),
    "antibiotics": ("抗生",),
}


def _parse_confounder_keys(raw: str | None, labels: dict[str, str]) -> list[str]:
    """Return known confounder keys (pitaya, iron, …) from CSV / free-text."""
    if not raw:
        return []
    text = str(raw)
    keys: list[str] = []
    seen: set[str] = set()
    for token in text.replace("，", ",").replace("、", ",").split(","):
        key = token.strip().lower()
        if not key:
            continue
        if key in labels and key not in seen:
            seen.add(key)
            keys.append(key)
            continue
        for cand, label in labels.items():
            if cand in seen:
                continue
            tips = _CONFOUNDER_FREE_TIPS.get(cand, ())
            if cand in key or label in token or any(tip in token for tip in tips):
                seen.add(cand)
                keys.append(cand)
    # Broad App checkbox: 「近24小時飲食或藥物可能染色」
    if "染色" in text or "近24" in text or "24小時" in text or "24h" in text.lower():
        for cand in ("pitaya", "pig_blood", "dark_greens", "iron", "antacid", "bismuth"):
            if cand not in seen:
                seen.add(cand)
                keys.append(cand)
    return keys


def _parse_confounders(raw: str | None, labels: dict[str, str]) -> list[str]:
    keys = _parse_confounder_keys(raw, labels)
    return [labels.get(k, k) for k in keys]


def _confirm_stool_class(
    hit: dict[str, Any],
    *,
    surface: dict[str, Any],
    water: dict[str, Any],
    conf_keys: list[str],
) -> tuple[dict[str, Any], list[str]]:
    """Image-based anti-false-positive notes (no checkbox questionnaire required)."""
    out = dict(hit)
    notes: list[str] = []
    cid = out.get("id") or ""
    # Optional API confounders still accepted for backward compat; UI no longer collects them.
    conf_set = set(conf_keys)

    if cid == "black_tarry":
        surf = surface.get("surface") or "matte"
        glossy = float(surface.get("glossy_score") or 0.0)
        diet_black = bool(conf_set & {"iron", "pig_blood", "bismuth"})
        if surf == "matte" and diet_black:
            out["label"] = "黑色／瀝青色（近似・飲食／鐵劑染色較可能）"
            out["hint"] = (
                f"表面偏啞光（glossy≈{glossy:.2f}）；"
                "教學上先排除飲食／鐵劑／鉍劑染色再解讀上消化道出血"
            )
            out["confirm"] = "diet_or_drug_matte_black"
            notes.append(
                f"黑色確認：啞光＋可能染色因子 → 飲食／藥物染色較可能"
                f"（GLCM對比≈{surface.get('glcm_contrast')}）（{TEACHING_TAG}）"
            )
        elif surf == "glossy_tar" and not diet_black:
            out["hint"] = (
                f"{out.get('hint')}；表面偏油亮（glossy≈{glossy:.2f}），"
                "教學上較接近瀝青樣黑便；仍須排除染色"
            )
            out["confirm"] = "glossy_tar_like"
            notes.append(
                f"黑色確認：高光／紋理偏油亮 → 瀝青樣黑便較可能（教學）（{TEACHING_TAG}）"
            )
        elif surf == "matte":
            out["hint"] = (
                f"{out.get('hint')}；表面偏啞光（glossy≈{glossy:.2f}），"
                "教學上亦可能為飲食／鐵劑染色"
            )
            out["confirm"] = "diet_or_drug_matte_black"
            notes.append(
                f"黑色確認：啞光表面 → 飲食／藥物染色亦可能"
                f"（GLCM對比≈{surface.get('glcm_contrast')}）（{TEACHING_TAG}）"
            )
        elif diet_black:
            notes.append(f"可能致黑便染色因子存在時，請先排除染色再解讀（{TEACHING_TAG}）")

    if cid == "bright_dark_red":
        pink = bool(water.get("pink_bloom"))
        clear = bool(water.get("clear_water"))
        da = water.get("da_ring_minus_center")
        if pink:
            out["hint"] = (
                f"{out.get('hint')}；周圍水液 a* 偏紅（Δa*≈{da}），"
                "教學上新鮮血染水較可能"
            )
            out["confirm"] = "pink_water_fresh_blood"
            notes.append(
                f"紅色確認：水液 a* 暈染偏粉紅 → 新鮮出血較可能（教學）（{TEACHING_TAG}）"
            )
        elif clear or not pink:
            out["label"] = "鮮紅色／暗紅色（近似・飲食色素亦可能）"
            out["hint"] = (
                f"水液未見明顯 a* 粉紅暈染（Δa*≈{da}），"
                "教學上火龍果／紅色蔬果色素亦可能"
            )
            out["confirm"] = "clear_water_diet_red"
            notes.append(
                f"紅色確認：無粉紅水暈 → 飲食色素亦可能（教學）（{TEACHING_TAG}）"
            )

    if cid == "dark_green":
        out["hint"] = f"{out.get('hint')}；深綠色蔬菜／鐵劑亦可能造成混淆"
        if "dark_greens" in conf_set or "iron" in conf_set:
            out["label"] = "墨綠色／深綠色（近似・深绿蔬菜／鐵劑混淆可能）"
            out["confirm"] = "dark_greens_confounder"
        notes.append(f"綠色確認：深綠色蔬菜／鐵劑染色混淆可能（{TEACHING_TAG}）")

    if cid == "clay_gray":
        out["hint"] = f"{out.get('hint')}；制酸劑／鋇劑亦可能造成灰白混淆"
        if "antacid" in conf_set:
            out["confirm"] = "antacid_confounder"
        notes.append(f"灰白確認：制酸劑／鋇劑染色混淆可能（{TEACHING_TAG}）")

    if cid in {"black_tarry", "bright_dark_red", "dark_green", "clay_gray", "outside_palette"}:
        notes.append(f"{DYE_CONFUSION_NOTE}（{TEACHING_TAG}）")
    elif conf_keys and cid not in {"outside_palette"}:
        notes.append(f"{DYE_CONFUSION_NOTE}（{TEACHING_TAG}）")
    return out, notes


def _downscale_circle(image: Image.Image, max_side: int = 720) -> Image.Image:
    """Phone JPEGs are huge; Lab/WB on 1600px+ was multi-second and timed out App clients."""
    work = image.convert("RGB")
    largest = max(work.size)
    if largest <= max_side:
        return work
    scale = max_side / float(largest)
    return work.resize(
        (max(1, int(round(work.size[0] * scale))), max(1, int(round(work.size[1] * scale)))),
        Image.Resampling.BILINEAR,
    )


def _preprocess_circle_image(
    image: Image.Image,
    color_temperature_k: int | float | str | None = "auto",
) -> tuple[Image.Image, dict[str, Any]]:
    from .analysis import (
        adapt_brightness_image,
        adapt_rgb_image,
        brightness_gain_to_target,
        estimate_color_temperature_k,
        estimate_relative_brightness,
    )

    rgb = _downscale_circle(image.convert("RGB"), max_side=720)
    if color_temperature_k is None or str(color_temperature_k).strip().lower() in {"", "auto"}:
        cct = estimate_color_temperature_k(rgb)
        auto = True
    else:
        try:
            cct = int(round(float(str(color_temperature_k).strip())))
        except (TypeError, ValueError):
            cct = estimate_color_temperature_k(rgb)
        auto = False
    adapted = adapt_rgb_image(rgb, cct)
    brightness = estimate_relative_brightness(adapted)
    gain = brightness_gain_to_target(brightness)
    adapted = adapt_brightness_image(adapted, gain)
    return adapted, {
        "color_temperature_k": cct,
        "color_temperature_auto": auto,
        "brightness": round(float(brightness), 4),
        "brightness_gain": round(float(gain), 4),
    }


def analyze_stool_image(
    image: Image.Image,
    color_temperature_k: int | float | str | None = "auto",
    confounders: str | None = None,
    severe_gate: bool = False,
) -> dict[str, Any]:
    work, lighting = _preprocess_circle_image(image, color_temperature_k)
    # Prefer dark stool cluster so porcelain/water does not dilute black → 黃褐色.
    L, a, b, lab_meta = _lab_from_roi(work, prefer_dark_cluster=True)
    hit = classify_stool_lab(L, a, b)
    steat = steatorrhea_score_v1(work, L, a, b)
    # Multi-cue oily override for pale/yellow-ish color classes only.
    # black / red / green stay intact. clay_gray may flip only when oil specular is clear
    # (teaching: chalky acholic vs fat-pale oily sheen).
    color_id = hit.get("id") or ""
    spec_score = float(
        ((steat.get("components") or {}).get("specular") or {}).get("specular_score") or 0.0
    )
    # Never override black / off-palette / red / green into 淡黃色／帶油光.
    # Only flip yellow-brown → pale_oily when L is pale enough AND specular oil is clear.
    overridable = color_id == "pale_oily" or (
        color_id == "normal_yellow_brown" and L >= 55 and spec_score >= 0.22
    ) or (color_id == "clay_gray" and spec_score >= 0.25 and L >= 55)
    if (
        steat["triggered"]
        and overridable
        and color_id not in {"black_tarry", "outside_palette", "bright_dark_red", "dark_green"}
        and L >= 55
    ):
        if color_id != "pale_oily":
            hit = _stool_pale_oily_class(approx=True)
            hit["via"] = "steatorrhea_score_v1"
        else:
            hit = dict(hit)
            hit["via"] = hit.get("via") or "color_and_steatorrhea_score"
        hit["steatorrhea_score"] = steat["score"]

    conf_keys = _parse_confounder_keys(confounders, STOOL_CONFOUNDER_LABELS)
    water = _surrounding_water_a_bloom(work)
    water_red = bool(water.get("pink_bloom"))
    surface = _black_surface_metrics(work) if (hit.get("id") == "black_tarry" or L < 40) else {
        "surface": "n/a",
        "glossy_score": 0.0,
        "glcm_contrast": 0.0,
        "glcm_energy": 0.0,
        "specular_score": spec_score,
        "specular_ratio": None,
        "pairs": 0,
    }
    hit, confirm_notes = _confirm_stool_class(
        hit, surface=surface, water=water, conf_keys=conf_keys
    )
    organ_scores = _organ_scores_from_keys(
        hit.get("organ_keys") or [], hit.get("health_score", 8), severe_gate=severe_gate
    )
    findings = [
        (
            f"大便色觀察：{hit['label']} → 臟腑聯想 {hit['organs']}；"
            f"{hit['hint']}；飲食／藥物混淆：{hit['confounders']}（{TEACHING_TAG}）"
        )
    ]
    if hit.get("id") == "pale_oily":
        findings.append(
            f"帶油光教學（Steatorrhea Score v1≈{steat['score']:.2f}，門檻{steat['threshold']}）："
            f"{STEATORRHEA_TEACHING}"
        )
        comps = steat.get("components") or {}
        spec = (comps.get("specular") or {}).get("specular_ratio")
        if spec is not None:
            findings.append(
                f"油光線索（教學）：表面高光比≈{float(spec):.1%}；"
                f"淡脂 Lab 匹配≈{comps.get('pale_lab_match', 0)}；"
                f"水面紋理≈{(comps.get('water_texture') or {}).get('water_texture_score', 0)}；"
                f"浮水分裂≈{(comps.get('float_split') or {}).get('float_score', 0)}"
                f"（{TEACHING_TAG}）"
            )
        findings.append(f"{STEATORRHEA_FLOAT_NOTE}（{TEACHING_TAG}）")
    findings.extend(confirm_notes)
    # No checkbox questionnaire; static dye note already appended in confirm_notes when relevant.
    if water_red and hit["id"] in {"bright_dark_red", "normal_yellow_brown", "pale_oily"}:
        findings.append(
            f"周圍水液 a* 暈染偏粉紅（Δa*≈{water.get('da_ring_minus_center')}）："
            f"教學上新鮮出血較可能；仍需排除染色（{TEACHING_TAG}）"
        )
    if hit.get("abnormal"):
        findings.append(f"{STOOL_DANGER_NOTE}（{TEACHING_TAG}）")
    findings.append(TEACHING_TAG)
    return {
        "shot_type": "stool",
        "dominant_color": _dominant_hex(work),
        "hsv": None,
        "color_label": f"大便：{hit['label']}",
        "findings": findings,
        "region_colors": {
            "face_color": None,
            "lip_color": None,
            "tongue_body_color": None,
            "tongue_coat_color": None,
        },
        "face_grid": None,
        "tongue_grid": None,
        "crop": {"method": "yellow_circle", "box": [0.0, 0.0, 1.0, 1.0], "lab": lab_meta},
        "preview": None,
        "organ_scores": organ_scores,
        "stool": {
            "class": hit,
            "lab": lab_meta,
            "water_reddish": water_red,
            "water_a_bloom": water,
            "surface": surface,
            "confounder_keys": conf_keys,
            "organ_scores": organ_scores,
            "steatorrhea": steat,
        },
        "urine": None,
        **lighting,
        "brightness_after": lighting.get("brightness"),
    }


def analyze_urine_image(
    image: Image.Image,
    color_temperature_k: int | float | str | None = "auto",
    confounders: str | None = None,
    severe_gate: bool = False,
    prior_foam_frames: list[Image.Image] | None = None,
) -> dict[str, Any]:
    work, lighting = _preprocess_circle_image(image, color_temperature_k)
    L, a, b, H, S, V, lab_meta = _urine_lab_hsv_from_roi(work)
    turbidity = _turbidity_heuristic(work)
    foam = _foam_metrics(work, prior_frames=prior_foam_frames)
    hit = classify_urine_lab(L, a, b, turbidity=turbidity, hsv=(H, S, V))
    # Optional confounders form field kept for API compat; UI no longer collects them.
    organ_scores = _organ_scores_from_keys(
        hit.get("organ_keys") or [], hit.get("health_score", 8), severe_gate=severe_gate
    )
    # Foam teaching may also soft-nudge kidney/spleen scores when fine dense
    if foam.get("persistent_foam_teaching_alert"):
        for key, val in _organ_scores_from_keys(
            ["kidney", "spleen"], 5, severe_gate=severe_gate
        ).items():
            prev = organ_scores.get(key)
            organ_scores[key] = val if prev is None else min(prev, val)

    # Short urine narrative: one status line (foam / stain folded in).
    outside = hit.get("id") in {"outside_palette", "possible_stain"} or hit.get("far_from_palette")
    status = "無法對照" if outside else ("需留意" if hit.get("abnormal") else "正常")
    extras: list[str] = []
    if outside:
        extras.append("疑染色／離色盤")
    gran = foam.get("granularity")
    if gran == "fine_dense" or foam.get("persistent_foam_teaching_alert"):
        extras.append("細密泡沫")
    elif gran == "coarse_sparse":
        extras.append("粗疏泡沫")
    elif gran == "mixed":
        extras.append("混合泡沫")
    if foam.get("decay_measured"):
        extras.append(f"泡沫衰減={foam.get('decay_half_life_hint')}")
    tip = hit.get("hint") or TEACHING_TAG
    if extras:
        tip = f"{tip}；{'、'.join(extras)}"
    findings = [f"尿尿：{status} — {hit['label']}（{tip}）"]
    findings.append(f"{DYE_CONFUSION_NOTE}（{TEACHING_TAG}）")
    findings.append(f"{URINE_PHONE_LIMIT}（{TEACHING_TAG}）")
    if foam.get("foam_ratio", 0) >= 0.05:
        findings.append(
            f"泡沫：面積比≈{foam.get('foam_ratio')}；粒度={foam.get('granularity')}；"
            f"圓度≈{foam.get('mean_roundness')}；GLCM對比≈{foam.get('glcm_contrast')}；"
            f"{URINE_FOAM_V1_LIMIT}（{TEACHING_TAG}）"
        )
    return {
        "shot_type": "urine",
        "dominant_color": _dominant_hex(work),
        "hsv": {"H": round(H, 1), "S": round(S, 3), "V": round(V, 3)},
        "color_label": f"尿尿：{hit['label']}",
        "findings": findings,
        "region_colors": {
            "face_color": None,
            "lip_color": None,
            "tongue_body_color": None,
            "tongue_coat_color": None,
        },
        "face_grid": None,
        "tongue_grid": None,
        "crop": {"method": "yellow_circle", "box": [0.0, 0.0, 1.0, 1.0], "lab": lab_meta},
        "preview": None,
        "organ_scores": organ_scores,
        "stool": None,
        "urine": {
            "class": hit,
            "lab": lab_meta,
            "hsv": {"H": round(H, 1), "S": round(S, 3), "V": round(V, 3)},
            "turbidity": turbidity,
            "foam": foam,
            "organ_scores": organ_scores,
        },
        **lighting,
        "brightness_after": lighting.get("brightness"),
    }
