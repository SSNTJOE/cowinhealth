from __future__ import annotations

from functools import lru_cache
from typing import Any

ORGAN_META = [
    ("heart", "心", "heart_score", "heart_pattern"),
    ("liver", "肝", "liver_score", "liver_pattern"),
    ("spleen", "脾", "spleen_score", "spleen_pattern"),
    ("stomach", "胃", "stomach_score", "stomach_pattern"),
    ("lung", "肺", "lung_score", "lung_pattern"),
    ("kidney", "腎", "kidney_score", "kidney_pattern"),
    ("gallbladder", "膽", "gallbladder_score", "gallbladder_pattern"),
    ("large_intestine", "大腸", "large_intestine_score", "large_intestine_pattern"),
    ("small_intestine", "小腸", "small_intestine_score", "small_intestine_pattern"),
    ("bladder", "膀胱", "bladder_score", "bladder_pattern"),
    ("uterus", "子宮", "uterus_score", "uterus_pattern"),
]

ORGAN_KEYS = [item[2] for item in ORGAN_META]
PATTERN_KEYS = [item[3] for item in ORGAN_META]
ORGAN_LABEL = {key: name for key, name, *_ in ORGAN_META}
PULSE_TO_ORGAN = {
    "left_cun_heavy": "heart",
    "left_cun_light": "small_intestine",
    "left_guan_heavy": "liver",
    "left_guan_light": "gallbladder",
    "left_chi_heavy": "kidney",
    "left_chi_light": "bladder",
    "right_cun_heavy": "lung",
    "right_cun_light": "large_intestine",
    "right_guan_heavy": "spleen",
    "right_guan_light": "stomach",
    "right_chi_heavy": "kidney",  # 命門併入腎（右手尺重按）
    "right_chi_light": "bladder",  # 三焦氣化併入膀胱
}
# PulseActivity 12×15s keys. Teaching: 左寸心、關肝、尺腎；右寸肺、關脾、尺腎／命門.
# Light (fu) maps paired fu organs; 右手關輕按=胃, 命門→腎.
PULSE_ORGAN_NOTE = (
    "left_cun_heavy=心, left_cun_light=小腸; "
    "left_guan_heavy=肝, left_guan_light=膽; "
    "left_chi_heavy=腎, left_chi_light=膀胱; "
    "right_cun_heavy=肺, right_cun_light=大腸; "
    "right_guan_heavy=脾, right_guan_light=胃; "
    "right_chi_heavy=腎(命門), right_chi_light=膀胱(三焦)"
)
COLOR_HEALTH_FORMULA = (
    "正常規格 ΔE≤3：ΔE=0→10，貼到規格邊緣→7。超過規格：剛超出→6，ΔE_ref→1（臉／舌質 20，舌苔 24）。"
    "7–10 正常，1–6 異常。臉正常 L*65 a*12 b*20；舌質 L*53 a*23 b*12；舌苔 L*70 a*4 b*8。"
    "證型取有判分來源裡分數最低者；濕熱／寒濕用 mositure。7–10 不放證型圖。"
)
HEALTH_FORMULA = (
    "臟腑分=round(mean(有判到的臉色、舌色、舌苔))。只有一項就用該分，兩項平均，三項平均。"
    "沒有判到的項目不列入。三項都沒有則記 10（正常，不放圖）。"
    + COLOR_HEALTH_FORMULA
)

SYMPTOM_RULES = [
    (("心悸", "失眠", "胸悶", "心煩"), "heart", "熱證", 1.4),
    (("心慌", "氣短", "沒力", "疲倦"), "heart", "虛證", 1.2),
    (("易怒", "脅痛", "口苦", "頭痛"), "liver", "熱證", 1.3),
    (("胸脅脹", "經痛", "情緒鬱"), "liver", "實證", 1.2),
    (("咳嗽", "氣喘", "鼻塞", "容易感冒"), "lung", "虛證", 1.2),
    (("黃痰", "咽痛", "發燒"), "lung", "熱證", 1.3),
    (("腰酸", "夜尿", "耳鳴", "怕冷"), "kidney", "寒證", 1.3),
    (("口乾夜間", "盜汗"), "kidney", "虛證", 1.1),
    (("口苦", "脇脹"), "gallbladder", "熱證", 1.2),
    (("便秘", "口氣", "腹痛"), "large_intestine", "熱證", 1.2),
    (("腹瀉", "腸鳴"), "large_intestine", "寒證", 1.1),
    (("小便黃", "灼熱"), "bladder", "熱證", 1.2),
    (("夜尿", "小便清長"), "bladder", "寒證", 1.2),
    (("經少", "經淡", "子宮"), "uterus", "虛證", 1.2),
    (("經血塊", "經痛"), "uterus", "實證", 1.2),
    (("怕冷", "手腳冰", "畏寒"), "kidney", "寒證", 1.0),
    (("口乾", "口渴", "長痘", "發炎"), "heart", "熱證", 0.8),
]


def empty_evidence() -> dict[str, dict[str, float]]:
    return {
        key: {"虛證": 0.0, "實證": 0.0, "熱證": 0.0, "寒證": 0.0}
        for key, *_ in ORGAN_META
    }


def add(evidence: dict[str, dict[str, float]], organ: str, pattern: str, weight: float) -> None:
    if organ in evidence and pattern in evidence[organ]:
        evidence[organ][pattern] += weight


def apply_text(evidence: dict[str, dict[str, float]], text: str) -> list[str]:
    notes: list[str] = []
    blob = text or ""
    for keywords, organ, pattern, weight in SYMPTOM_RULES:
        if any(word in blob for word in keywords):
            add(evidence, organ, pattern, weight)
            notes.append(f"陳述「{'／'.join(keywords[:2])}」偏向{ORGAN_LABEL[organ]}{pattern}")
    return notes


# Stored tokens use 寒, matching symptoms.xls / Foods.xls (實寒、虛寒). Do not keep a 冷 token.
SPLEEN_STOMACH_PATTERNS = (
    "脾實熱",
    "脾實寒",
    "脾虛熱",
    "脾虛寒",
    "胃實熱",
    "胃實寒",
    "胃虛熱",
    "胃虛寒",
)
_PATTERN_AXES = {
    "實熱": (("實證", 1.0), ("熱證", 1.0)),
    "實寒": (("實證", 1.0), ("寒證", 1.0)),
    "虛熱": (("虛證", 1.0), ("熱證", 1.0)),
    "虛寒": (("虛證", 1.0), ("寒證", 1.0)),
}


def empty_spleen_stomach_scores() -> dict[str, int]:
    return {label: 0 for label in SPLEEN_STOMACH_PATTERNS}


def normalize_pattern_token(token: str) -> str:
    text = (token or "").strip().replace("實冷", "實寒").replace("虛冷", "虛寒")
    return text


def _organ_for_pattern(label: str) -> str:
    if label.startswith("脾"):
        return "spleen"
    if label.startswith("胃"):
        return "stomach"
    return ""


@lru_cache(maxsize=1)
def _symptom_catalog() -> tuple[tuple[str, tuple[str, ...]], ...]:
    import xlrd

    from .config import ROOT

    sheet = xlrd.open_workbook(str(ROOT / "symptoms.xls")).sheet_by_index(0)
    rows: list[tuple[str, tuple[str, ...]]] = []
    for index in range(1, sheet.nrows):
        name = str(sheet.cell_value(index, 0)).strip()
        raw = str(sheet.cell_value(index, 4)).strip()
        if not name:
            continue
        tokens = tuple(
            normalize_pattern_token(part)
            for part in raw.replace("，", ",").split(",")
            if part.strip()
        )
        rows.append((name, tokens))
    rows.sort(key=lambda item: len(item[0]), reverse=True)
    return tuple(rows)


def _count_written_tokens(text: str) -> dict[str, int]:
    """Count tokens the user actually wrote. 脾胃X is not 脾X and not 胃X."""
    scores = empty_spleen_stomach_scores()
    blob = normalize_pattern_token(text or "")
    for label in SPLEEN_STOMACH_PATTERNS:
        start = 0
        while True:
            index = blob.find(label, start)
            if index < 0:
                break
            previous = blob[index - 1] if index else ""
            if label.startswith("胃") and previous == "脾":
                start = index + 1
                continue
            scores[label] += 1
            start = index + len(label)
    return scores


def score_spleen_stomach_symptoms(text: str) -> tuple[dict[str, int], list[str]]:
    """Tally the eight 脾/胃 patterns. A 脾 token never increments 胃, or the reverse."""
    scores = _count_written_tokens(text)
    notes: list[str] = []
    blob = text or ""
    occupied = [False] * len(blob)
    for name, tokens in _symptom_catalog():
        start = 0
        while True:
            index = blob.find(name, start)
            if index < 0:
                break
            end = index + len(name)
            if any(occupied[index:end]):
                start = index + len(name)
                continue
            for cursor in range(index, end):
                occupied[cursor] = True
            hit = [token for token in tokens if token in scores]
            for token in hit:
                scores[token] += 1
            start = end
    return scores, notes


def apply_pattern_scores_to_evidence(evidence: dict[str, dict[str, float]], scores: dict[str, int]) -> None:
    for label, count in scores.items():
        organ = _organ_for_pattern(label)
        kind = label[1:]
        if organ not in evidence or kind not in _PATTERN_AXES or count <= 0:
            continue
        for axis, weight in _PATTERN_AXES[kind]:
            add(evidence, organ, axis, weight * count)


def pattern_kinds_gained(weights: dict[str, float], baseline: dict[str, float] | None = None) -> list[str]:
    """Patterns this organ gained on its own. Does not look at the other organ."""
    before = baseline or {}
    gained: list[str] = []
    for kind, axes in _PATTERN_AXES.items():
        if all(float(weights.get(axis, 0)) - float(before.get(axis, 0)) >= 0.9 for axis, _weight in axes):
            gained.append(kind)
    return gained


def apply_color_findings(evidence: dict[str, dict[str, float]], findings: list[str]) -> None:
    mapping = [
        ("胃火", "stomach", "熱證", 2.0),
        ("胃火", "stomach", "實證", 1.6),
        ("額頭實熱", "heart", "熱證", 2.0),
        ("額頭（第2格", "heart", "實證", 1.4),
        ("肝腎陰虛", "liver", "虛證", 1.8),
        ("肝腎陰虛", "kidney", "虛證", 1.8),
        ("肝腎陰虛", "liver", "熱證", 1.4),
        ("寒凝", "kidney", "寒證", 1.8),
        ("寒凝", "heart", "實證", 1.4),
        ("脾腎陽虛", "spleen", "虛證", 1.8),
        ("脾腎陽虛", "kidney", "虛證", 1.8),
        ("脾腎陽虛", "kidney", "寒證", 1.4),
        ("脾胃濕證", "spleen", "實證", 1.8),
        ("鼻翼", "spleen", "實證", 1.2),
        ("心火盛", "heart", "熱證", 2.2),
        ("心火盛", "heart", "實證", 1.6),
        ("心肺氣虛", "heart", "虛證", 2.0),
        ("心肺氣虛", "lung", "虛證", 1.8),
        ("淡白無血色", "heart", "寒證", 1.6),
        ("心肺區偏紅", "heart", "熱證", 1.8),
        ("點刺", "heart", "熱證", 0.8),
        ("脾胃虛寒", "stomach", "寒證", 2.0),
        ("脾胃虛寒", "stomach", "虛證", 1.8),
        ("白厚苔", "stomach", "寒證", 1.4),
        ("胃腸實熱", "stomach", "熱證", 2.0),
        ("胃腸實熱", "stomach", "實證", 1.6),
        ("胃腸實熱", "large_intestine", "熱證", 1.6),
        ("胃腸實熱", "gallbladder", "熱證", 1.2),
        ("焦黃苔", "stomach", "熱證", 1.6),
        ("焦黃苔", "large_intestine", "實證", 1.4),
        ("血瘀傾向", "liver", "實證", 1.8),
        ("心火", "heart", "熱證", 2.0),
        ("唇色偏紅", "heart", "熱證", 1.6),
        ("脾血虛", "spleen", "虛證", 2.2),
        ("蒼白", "spleen", "虛證", 1.8),
        ("肝瘀", "liver", "實證", 2.0),
        ("青紫", "liver", "實證", 1.8),
        ("萎黃", "spleen", "虛證", 1.8),
        ("苔白", "stomach", "虛證", 1.5),
        ("苔黃", "stomach", "熱證", 1.6),
        ("膽熱", "gallbladder", "熱證", 1.6),
        ("腎", "kidney", "虛證", 1.4),
        ("面色偏暗", "kidney", "虛證", 1.6),
        ("肺氣虛", "lung", "虛證", 1.6),
        ("氣色偏白", "lung", "虛證", 1.4),
        ("眼部偏紅", "liver", "熱證", 1.3),
        ("偏紅／腫脹傾向", "liver", "熱證", 1.6),
        ("臉色偏綠", "kidney", "寒證", 1.7),
        ("臉色偏紅", "heart", "熱證", 1.5),
        ("臉色偏黃", "spleen", "實證", 1.5),
        ("臉色偏白", "lung", "虛證", 1.5),
        ("氣血虛", "spleen", "虛證", 1.8),
        ("實熱證", "heart", "熱證", 1.6),
        ("胃不好", "stomach", "虛證", 1.6),
        ("濕熱", "spleen", "熱證", 1.5),
        ("血虛", "spleen", "虛證", 1.6),
        ("肺和皮實熱", "lung", "熱證", 1.7),
        ("肝膽）偏黃", "gallbladder", "熱證", 1.4),
        ("肝膽）偏紅", "liver", "熱證", 1.3),
        ("心熱象", "heart", "熱證", 1.4),
        ("咽喉／肺熱", "lung", "熱證", 1.3),
        ("咽喉／肺虛", "lung", "虛證", 1.3),
        ("小腸／大腸熱", "large_intestine", "熱證", 1.2),
        ("生殖器／腎不足", "kidney", "虛證", 1.4),
        ("舌尖紅", "heart", "熱證", 2.0),
        ("舌邊青紫", "liver", "實證", 2.2),
        ("腎／舌根）舌質偏紅", "kidney", "熱證", 1.6),
        ("腎／舌根）舌質偏白", "kidney", "寒證", 1.6),
        ("脾胃）舌質偏紅", "spleen", "熱證", 1.5),
        ("脾胃）舌質偏白", "spleen", "寒證", 1.5),
        ("心肺／舌尖）舌質偏紅", "heart", "熱證", 1.8),
        ("心肺／舌尖）舌質偏白", "lung", "寒證", 1.4),
        ("肝膽）舌質偏紅", "liver", "熱證", 1.5),
        ("肝膽）舌質偏白", "liver", "寒證", 1.4),
        ("白苔很少", "stomach", "虛證", 1.8),
        ("胃虛", "stomach", "虛證", 1.6),
        ("黑灰苔", "kidney", "寒證", 1.8),
        ("實寒證", "kidney", "寒證", 1.4),
        ("虛寒證", "kidney", "寒證", 1.4),
        ("黃苔", "stomach", "熱證", 1.5),
        ("子宮", "uterus", "實證", 1.0),
    ]
    joined = " ".join(findings)
    for needle, organ, pattern, weight in mapping:
        if needle in joined:
            add(evidence, organ, pattern, weight)


def apply_pulse(evidence: dict[str, dict[str, float]], pulse: dict[str, Any] | None) -> list[str]:
    notes: list[str] = []
    if not pulse:
        return notes
    for slot, organ in PULSE_TO_ORGAN.items():
        beats = pulse.get(slot)
        if beats is None:
            continue
        try:
            count = float(beats)
        except (TypeError, ValueError):
            continue
        if count > 23:
            add(evidence, organ, "熱證", 1.8)
            add(evidence, organ, "實證", 1.4)
            notes.append(f"{slot} 15秒 {count:.0f} 次，數脈偏熱實 → {ORGAN_LABEL[organ]}")
        elif count < 14:
            add(evidence, organ, "寒證", 1.8)
            add(evidence, organ, "虛證", 1.4)
            notes.append(f"{slot} 15秒 {count:.0f} 次，遲脈偏寒虛 → {ORGAN_LABEL[organ]}")
    return notes


OVERLAY_FILES = {
    ("實證", "熱證"): "strong-hot.png",
    ("實證", "寒證"): "strong-cold.png",
    ("虛證", "熱證"): "weak-hot.png",
    ("虛證", "寒證"): "weak-cold.png",
}


def overlay_from_weights(weights: dict[str, float]) -> tuple[str, int, str | None]:
    xu, shi, re, han = weights["虛證"], weights["實證"], weights["熱證"], weights["寒證"]
    strongest = max(xu, shi, re, han)
    if strongest < 0.9:
        return "待觀察", 5, None
    if xu >= shi:
        xu_shi = "虛證"
        xs_w = xu
    else:
        xu_shi = "實證"
        xs_w = shi
    if re >= han:
        re_han = "熱證"
        rh_w = re
    else:
        re_han = "寒證"
        rh_w = han
    if xs_w < 0.9:
        xu_shi = "實證" if re_han == "熱證" else "虛證"
    if rh_w < 0.9:
        re_han = "熱證" if xu_shi == "實證" else "寒證"
    label = f"{xu_shi}{re_han}"
    overlay = OVERLAY_FILES[(xu_shi, re_han)]
    score = max(1, min(10, int(round(5 - min(strongest, 4.0)))))
    return label, score, overlay


def finalize(
    evidence: dict[str, dict[str, float]],
) -> tuple[dict[str, int], dict[str, str], dict[str, str | None]]:
    scores: dict[str, int] = {}
    patterns: dict[str, str] = {}
    overlays: dict[str, str | None] = {}
    for key, _name, score_key, pattern_key in ORGAN_META:
        label, score, overlay = overlay_from_weights(evidence[key])
        patterns[pattern_key] = label
        scores[score_key] = score
        overlays[key] = overlay
    return scores, patterns, overlays


def pulse_is_present(pulse: dict[str, Any] | None) -> bool:
    if not pulse:
        return False
    for slot in PULSE_TO_ORGAN:
        raw = pulse.get(slot)
        if raw is None:
            continue
        try:
            float(raw)
            return True
        except (TypeError, ValueError):
            continue
    return False


def evidence_from_marks(marks: list[dict[str, Any]] | None) -> dict[str, dict[str, float]]:
    evidence = empty_evidence()
    for mark in marks or []:
        add(evidence, mark.get("organ", ""), mark.get("pattern", ""), float(mark.get("weight") or 0))
    return evidence


def organ_scores_from_color_blocks(blocks: list[dict[str, Any]] | None) -> dict[str, int]:
    """Lowest 1–10 score among blocks mapped to each organ. Organs with no block are omitted."""
    scores: dict[str, int] = {}
    for block in blocks or []:
        try:
            health = int(block.get("health_score"))
        except (TypeError, ValueError):
            continue
        health = max(1, min(10, health))
        for organ in block.get("organs") or []:
            for key, _name, score_key, _pk in ORGAN_META:
                if key == organ:
                    previous = scores.get(score_key)
                    scores[score_key] = health if previous is None else min(previous, health)
    return scores


CLASS_TO_API_PATTERN = {
    "正常": "健康",
    "接近基本色": "健康",
    "接近正常": "健康",
    "實熱": "實證熱證",
    "實熱色": "實證熱證",
    "虛熱": "虛證熱證",
    "虛熱色": "虛證熱證",
    "實寒": "實證寒證",
    "實寒色": "實證寒證",
    "虛寒": "虛證寒證",
    "虛寒色": "虛證寒證",
    "濕熱": "濕熱證",
    "濕熱證": "濕熱證",
    "寒濕": "寒濕證",
    "寒濕證": "寒濕證",
    "濕症": "濕氣較重",
    "濕氣": "濕氣較重",
}


def organ_patterns_from_color_blocks(blocks: list[dict[str, Any]] | None) -> dict[str, str]:
    """Pattern of the worst (lowest health) block per organ; 健康 if none."""
    chosen: dict[str, tuple[int, str]] = {}
    for block in blocks or []:
        try:
            health = int(block.get("health_score"))
        except (TypeError, ValueError):
            continue
        raw = block.get("api_pattern") or block.get("class_label") or block.get("bias") or ""
        label = CLASS_TO_API_PATTERN.get(str(raw), str(raw) or "健康")
        for organ in block.get("organs") or []:
            previous = chosen.get(organ)
            if previous is None or health < previous[0]:
                chosen[organ] = (health, label)
    return {organ: label for organ, (_health, label) in chosen.items()}


def compose_organ_health(
    source_scores: dict[str, dict[str, int] | None],
) -> tuple[dict[str, int], dict[str, Any]]:
    """Mean of face, tongue body, and tongue coat scores that actually exist for the organ."""
    composites: dict[str, int] = {}
    breakdown: dict[str, Any] = {}
    for key, name, score_key, _pattern_key in ORGAN_META:
        parts: dict[str, int | None] = {}
        values: list[int] = []
        for source, scores in source_scores.items():
            if not scores or score_key not in scores:
                parts[source] = None
                continue
            value = int(scores[score_key])
            parts[source] = value
            values.append(value)
        if values:
            composite = max(1, min(10, int(round(sum(values) / len(values)))))
        else:
            composite = 10
        composites[score_key] = composite
        breakdown[key] = {
            "organ": name,
            "composite": composite,
            "n_sources": len(values),
            "sources": parts,
        }
    return composites, breakdown


def serialize_organ_health(
    scores: dict[str, int],
    breakdown: dict[str, Any],
    source_keys: list[str],
) -> dict[str, Any]:
    return {
        "formula": HEALTH_FORMULA,
        "color_formula": COLOR_HEALTH_FORMULA,
        "pulse_organ_map": dict(PULSE_TO_ORGAN),
        "pulse_organ_note": PULSE_ORGAN_NOTE,
        "source_keys": source_keys,
        "scores": scores,
        "organs": breakdown,
        "disclaimer": "教學示範，非中醫診斷",
    }


def overlay_from_pattern_label(label: str | None) -> str | None:
    mapping = {
        "實證熱證": "strong-hot.png",
        "實熱": "strong-hot.png",
        "實證寒證": "strong-cold.png",
        "實寒": "strong-cold.png",
        "虛證熱證": "weak-hot.png",
        "虛熱": "weak-hot.png",
        "虛證寒證": "weak-cold.png",
        "虛寒": "weak-cold.png",
        "濕氣較重": "mositure.png",
        "濕熱證": "mositure.png",
        "寒濕證": "mositure.png",
        "濕熱": "mositure.png",
        "寒濕": "mositure.png",
        "濕症": "mositure.png",
    }
    return mapping.get(label or "")
