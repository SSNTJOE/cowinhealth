"""Teaching-demo stool / urine notes from a yellow-circle camera crop.

Text-only findings. No diagnosis. Images are analyzed in memory and not stored.
Optional numeric organ_scores feed compose_organ_health when present.
"""

from __future__ import annotations

from typing import Any

from PIL import Image, ImageFilter

TEACHING_TAG = "教學示範，非診斷"

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

# Teaching palette centers (L, a*, b*) for optional nearest-class / stain distance.
URINE_PALETTE = {
    "clear_colorless": (90.0, 0.0, 5.0),
    "pale_goose_yellow": (80.0, 0.0, 25.0),
    "deep_yellow": (67.0, 5.0, 50.0),
    "dark_tea": (38.0, 18.0, 30.0),
    "red_pink": (55.0, 28.0, 8.0),
    "milky_cloudy": (70.0, 0.0, 8.0),
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


def _lab_from_roi(image: Image.Image) -> tuple[float, float, float, dict[str, Any]]:
    """Median CIELAB of circle-crop pixels; soft white-ref WB; drop specular (high L / low S)."""
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
    kept_l: list[float] = []
    kept_a: list[float] = []
    kept_b: list[float] = []
    for (r, g, b), (L, a, bb), (_h, s, _v) in zip(rgb2, lab, hsv):
        # Specular / glare: very high L or very bright low-sat
        if max(r, g, b) >= 245 and min(r, g, b) >= 220:
            continue
        if L >= 92 and abs(a) < 4 and abs(bb) < 6:
            continue
        if L >= 88 and s <= 0.08:
            continue
        kept_l.append(L)
        kept_a.append(a)
        kept_b.append(bb)
    if not kept_l:
        kept_l = [p[0] for p in lab]
        kept_a = [p[1] for p in lab]
        kept_b = [p[2] for p in lab]
    med = (_median(kept_l), _median(kept_a), _median(kept_b))
    meta = {
        "pixels_used": len(kept_l),
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


def _surrounding_water_reddish(image: Image.Image) -> bool:
    work = image.convert("RGB").resize((64, 64), Image.Resampling.BILINEAR)
    w, h = work.size
    cx0, cy0, cx1, cy1 = int(w * 0.3), int(h * 0.3), int(w * 0.7), int(h * 0.7)
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
    if len(center) < 20 or len(ring) < 20:
        return False

    def mean_a(samples: list[tuple[int, int, int]]) -> float:
        patch = Image.new("RGB", (len(samples), 1))
        patch.putdata(samples)
        labs = _lab_pixels(patch, max_side=max(len(samples), 1))
        return _median([item[1] for item in labs])

    c_l = _median([max(p) for p in center])
    r_l = _median([max(p) for p in ring])
    if r_l + 8 < c_l:
        return False
    return mean_a(ring) - mean_a(center) >= 8.0


def _turbidity_heuristic(image: Image.Image) -> dict[str, Any]:
    """High local luminance variance + low edge contrast → milky/cloudy teaching cue."""
    gray = image.convert("L").resize((96, 96), Image.Resampling.BILINEAR)
    vals = [p / 255.0 for p in gray.getdata()]
    local_var = _variance(vals)
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_vals = [p / 255.0 for p in edges.getdata()]
    edge_mean = sum(edge_vals) / max(1, len(edge_vals))
    cloudy = local_var >= 0.018 and edge_mean <= 0.12
    return {
        "local_var": round(local_var, 4),
        "edge_mean": round(edge_mean, 4),
        "cloudy": cloudy,
    }


def _foam_metrics(image: Image.Image) -> dict[str, Any]:
    """Single-frame foam area + fine/coarse granularity (no multi-minute decay yet)."""
    work = image.convert("RGB").resize((128, 128), Image.Resampling.BILINEAR)
    hsv = work.convert("HSV")
    lab = work.convert("LAB")
    edges = work.convert("L").filter(ImageFilter.FIND_EDGES)
    w, h = work.size
    foam_xy: list[tuple[int, int]] = []
    hsv_data = list(hsv.getdata())
    lab_data = list(lab.getdata())
    edge_data = list(edges.getdata())
    for i, (( _hh, s, v), (Lraw, _a, _b), e) in enumerate(zip(hsv_data, lab_data, edge_data)):
        L = Lraw * 100.0 / 255.0
        sat = s / 255.0
        val = v / 255.0
        # Bright high-frequency / edge-ish on liquid surface
        if L < 72 or sat > 0.28 or val < 0.55:
            continue
        if e < 18 and L < 88:
            continue
        foam_xy.append((i % w, i // w))
    total = w * h
    ratio = len(foam_xy) / float(total) if total else 0.0
    granularity = "none"
    if foam_xy:
        # Neighbor clustering: fine foam → many small isolated peaks; coarse → larger blobs
        foam_set = set(foam_xy)
        neighbors = 0
        for x, y in foam_xy:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if (x + dx, y + dy) in foam_set:
                    neighbors += 1
        dens = neighbors / max(1, len(foam_xy))
        if dens >= 2.2 and ratio >= 0.08:
            granularity = "fine_dense"
        elif dens >= 1.2:
            granularity = "mixed"
        else:
            granularity = "coarse_sparse"
    persistent_alert = granularity == "fine_dense" and ratio >= 0.12
    return {
        "foam_ratio": round(ratio, 4),
        "granularity": granularity,
        "persistent_foam_teaching_alert": persistent_alert,
        "decay_measured": False,
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
    if 35 <= L <= 60 and 5 <= a <= 18 and 20 <= b <= 45 and b >= a + 8:
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
    # Fat-pale Lab band (steatorrhea teaching): L>60, b>+25, a≈-2..+8
    if L > 60 and b > 25 and -2 <= a <= 8:
        return _stool_pale_oily_class()
    if 45 <= L <= 72 and -2 <= a <= 12 and 8 <= b <= 28 and chroma < 32:
        return _stool_pale_oily_class()
    if L < 28 and chroma < 14:
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
    if a > 18 and a >= b:
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
    return {
        "id": "normal_yellow_brown",
        "label": "黃褐色／金黃色（近似）",
        "organs": "肝膽膽汁正常、腸道通暢（教學）",
        "organ_keys": ["liver", "gallbladder", "large_intestine", "small_intestine"],
        "hint": "相對健康糞色教學示範",
        "confounders": "一般飲食",
        "abnormal": False,
        "health_score": 8,
    }


def classify_urine_lab(
    L: float,
    a: float,
    b: float,
    turbidity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """v1 practical urine palette / Lab boxes (+ turbidity heuristic)."""
    chroma = (a * a + b * b) ** 0.5
    turb = turbidity or {}

    # Nearest palette distance for stain flag
    nearest_id = None
    nearest_de = 1e9
    for pid, center in URINE_PALETTE.items():
        de = _delta_e76((L, a, b), center)
        if de < nearest_de:
            nearest_de = de
            nearest_id = pid
    far_from_palette = nearest_de > 28.0

    if turb.get("cloudy") and chroma <= 16 and 45 <= L <= 88:
        return {
            "id": "milky_cloudy",
            "label": "乳白色／混濁",
            "hint": "泌尿道感染／膿尿或結晶（痛風／結石）教學提示",
            "abnormal": True,
            "health_score": 5,
            "organ_keys": ["bladder", "kidney"],
            "palette_delta_e": round(nearest_de, 1),
            "far_from_palette": False,
        }

    # Clear: L>85, a~0, b<10
    if L > 85 and abs(a) <= 6 and b < 10:
        return {
            "id": "clear_colorless",
            "label": "透明無色",
            "hint": "飲水過多教學；若持續清澈且多尿、飲水不多，教學上聯想腦垂體／腎或腎陽虛",
            "abnormal": True,
            "health_score": 6,
            "organ_keys": ["kidney", "bladder"],
            "palette_delta_e": round(nearest_de, 1),
            "far_from_palette": far_from_palette,
        }
    # Normal pale yellow: L65–85, a~0, b12–38 (gentle teaching box)
    if 65 <= L <= 85 and abs(a) <= 10 and 12 <= b <= 38:
        return {
            "id": "pale_goose_yellow",
            "label": "淡／鵝黃色",
            "hint": "相對健康尿色教學示範",
            "abnormal": False,
            "health_score": 9,
            "organ_keys": ["kidney", "bladder"],
            "palette_delta_e": round(nearest_de, 1),
            "far_from_palette": False,
        }
    # Deep yellow / dehydrated: L40–75, a0–12, b≥28 (before dark-tea)
    if 40 <= L <= 75 and 0 <= a <= 12 and b >= 28 and a < 14:
        return {
            "id": "deep_yellow",
            "label": "深黃色",
            "hint": "脫水／內熱／心火旺教學提示",
            "abnormal": True,
            "health_score": 6,
            "organ_keys": ["heart", "bladder", "kidney"],
            "palette_delta_e": round(nearest_de, 1),
            "far_from_palette": far_from_palette,
        }
    # Dark tea / bilirubin: L25–50, a≥6, b20–45
    if 25 <= L <= 50 and a >= 6 and 20 <= b <= 45:
        return {
            "id": "dark_tea",
            "label": "濃茶／橘褐色",
            "hint": "肝膽膽紅素教學，或劇烈運動後可樂色橫紋肌溶解／腎風險教學",
            "abnormal": True,
            "health_score": 3,
            "organ_keys": ["liver", "gallbladder", "kidney"],
            "palette_delta_e": round(nearest_de, 1),
            "far_from_palette": far_from_palette,
        }
    # Hematuria red/pink: L40–70, a>20, b<15 (a dominates)
    if 40 <= L <= 70 and a > 20 and b < 15:
        return {
            "id": "red_pink",
            "label": "紅色／粉紅色",
            "hint": "血尿教學（腎／輸尿管／膀胱／攝護腺）；劇烈腰痛教學聯想結石，無痛則腫瘤警覺教學",
            "abnormal": True,
            "health_score": 3,
            "organ_keys": ["kidney", "bladder"],
            "palette_delta_e": round(nearest_de, 1),
            "far_from_palette": far_from_palette,
        }

    # Soft fallbacks
    if L >= 78 and chroma <= 12:
        return {
            "id": "clear_colorless",
            "label": "透明無色（近似）",
            "hint": "飲水過多教學；持續清澈多尿需進一步評估（教學）",
            "abnormal": True,
            "health_score": 6,
            "organ_keys": ["kidney", "bladder"],
            "palette_delta_e": round(nearest_de, 1),
            "far_from_palette": far_from_palette,
        }
    if a >= 18 and a >= abs(b) + 5:
        return {
            "id": "red_pink",
            "label": "紅色／粉紅色（近似）",
            "hint": "血尿教學（需排除染色）；劇痛／無痛分流為教育說明",
            "abnormal": True,
            "health_score": 3,
            "organ_keys": ["kidney", "bladder"],
            "palette_delta_e": round(nearest_de, 1),
            "far_from_palette": far_from_palette,
        }
    if L < 45 and b >= 18 and a >= 8:
        return {
            "id": "dark_tea",
            "label": "濃茶／橘褐色（近似）",
            "hint": "肝膽膽紅素或運動後深色尿腎風險教學",
            "abnormal": True,
            "health_score": 3,
            "organ_keys": ["liver", "gallbladder", "kidney"],
            "palette_delta_e": round(nearest_de, 1),
            "far_from_palette": far_from_palette,
        }
    if L < 70 and b >= 30:
        return {
            "id": "deep_yellow",
            "label": "深黃色（近似）",
            "hint": "脫水／內熱／心火旺教學提示",
            "abnormal": True,
            "health_score": 6,
            "organ_keys": ["heart", "bladder", "kidney"],
            "palette_delta_e": round(nearest_de, 1),
            "far_from_palette": far_from_palette,
        }
    if 60 <= L <= 88 and 10 <= b <= 40 and abs(a) <= 12:
        return {
            "id": "pale_goose_yellow",
            "label": "淡／鵝黃色（近似）",
            "hint": "相對健康尿色教學示範",
            "abnormal": False,
            "health_score": 8,
            "organ_keys": ["kidney", "bladder"],
            "palette_delta_e": round(nearest_de, 1),
            "far_from_palette": far_from_palette,
        }
    # Milky / cloudy soft: mid-high L, very low chroma (even without turbidity flag)
    if 50 <= L <= 85 and chroma <= 14 and abs(a) <= 6 and b < 16:
        return {
            "id": "milky_cloudy",
            "label": "乳白色／混濁（近似）",
            "hint": "泌尿道感染／膿尿或結晶（痛風／結石）教學提示",
            "abnormal": True,
            "health_score": 5,
            "organ_keys": ["bladder", "kidney"],
            "palette_delta_e": round(nearest_de, 1),
            "far_from_palette": far_from_palette,
        }

    # Far from all teaching classes → stain teaching
    return {
        "id": "possible_stain",
        "label": "偏離教學色盤（可能飲食／藥物染色）",
        "hint": (
            f"色座標距最近教學色（{nearest_id or '—'}）ΔE≈{nearest_de:.0f}；"
            "教學上先排除火龍果／甜菜／Ｂ群／藥物染色再解讀"
        ),
        "abnormal": True,
        "health_score": 6,
        "organ_keys": ["kidney", "bladder"],
        "palette_delta_e": round(nearest_de, 1),
        "far_from_palette": True,
    }


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


def _parse_confounders(raw: str | None, labels: dict[str, str]) -> list[str]:
    if not raw:
        return []
    out: list[str] = []
    for token in str(raw).replace("，", ",").split(","):
        key = token.strip().lower()
        if not key:
            continue
        out.append(labels.get(key, key))
    return out


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

    rgb = image.convert("RGB")
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
    L, a, b, lab_meta = _lab_from_roi(work)
    hit = classify_stool_lab(L, a, b)
    steat = steatorrhea_score_v1(work, L, a, b)
    # Multi-cue oily override for pale/yellow-ish color classes only.
    # black / red / green stay intact. clay_gray may flip only when oil specular is clear
    # (teaching: chalky acholic vs fat-pale oily sheen).
    color_id = hit.get("id") or ""
    spec_score = float(
        ((steat.get("components") or {}).get("specular") or {}).get("specular_score") or 0.0
    )
    overridable = color_id in {"normal_yellow_brown", "pale_oily"} or (
        color_id == "clay_gray" and spec_score >= 0.25
    )
    if steat["triggered"] and overridable:
        if color_id != "pale_oily":
            hit = _stool_pale_oily_class(approx=True)
            hit["via"] = "steatorrhea_score_v1"
        else:
            hit = dict(hit)
            hit["via"] = hit.get("via") or "color_and_steatorrhea_score"
        hit["steatorrhea_score"] = steat["score"]

    user_conf = _parse_confounders(confounders, STOOL_CONFOUNDER_LABELS)
    water_red = _surrounding_water_reddish(work)
    organ_scores = _organ_scores_from_keys(
        hit.get("organ_keys") or [], hit.get("health_score", 8), severe_gate=severe_gate
    )
    findings = [
        (
            f"大便色觀察：{hit['label']} → 臟腑聯想 {hit['organs']}；"
            f"{hit['hint']}；飲食／藥物混淆：{hit['confounders']}（{TEACHING_TAG}）"
        )
    ]
    if hit.get("id") == "pale_oily" or (steat["triggered"] and overridable):
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
    if user_conf:
        findings.append(f"近２４小時自行勾選可能染色／混淆：{'、'.join(user_conf)}（{TEACHING_TAG}）")
    if water_red and hit["id"] in {"bright_dark_red", "normal_yellow_brown", "pale_oily"}:
        findings.append(
            f"周圍水液偏紅（軟提示）：教學上可對照下消化道出血與飲食色素，需排除染色（{TEACHING_TAG}）"
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
) -> dict[str, Any]:
    work, lighting = _preprocess_circle_image(image, color_temperature_k)
    L, a, b, lab_meta = _lab_from_roi(work)
    turbidity = _turbidity_heuristic(work)
    foam = _foam_metrics(work)
    hit = classify_urine_lab(L, a, b, turbidity=turbidity)
    user_conf = _parse_confounders(confounders, URINE_CONFOUNDER_LABELS)
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
    status = "需留意" if hit.get("abnormal") else "正常"
    extras: list[str] = []
    if hit.get("far_from_palette"):
        extras.append("疑染色")
    gran = foam.get("granularity")
    if gran == "fine_dense" or foam.get("persistent_foam_teaching_alert"):
        extras.append("細密泡沫")
    elif gran == "coarse_sparse":
        extras.append("粗疏泡沫")
    elif gran == "mixed":
        extras.append("混合泡沫")
    if user_conf:
        extras.append("已勾選染色")
    tip = hit.get("hint") or TEACHING_TAG
    if extras:
        tip = f"{tip}；{'、'.join(extras)}"
    findings = [f"尿尿：{status} — {hit['label']}（{tip}）"]
    return {
        "shot_type": "urine",
        "dominant_color": _dominant_hex(work),
        "hsv": None,
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
            "turbidity": turbidity,
            "foam": foam,
            "organ_scores": organ_scores,
        },
        **lighting,
        "brightness_after": lighting.get("brightness"),
    }
