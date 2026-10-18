from __future__ import annotations

from typing import Any

ORGAN_META = [
    ("heart", "心", "heart_score", "heart_pattern"),
    ("liver", "肝", "liver_score", "liver_pattern"),
    ("spleen", "脾", "spleen_score", "spleen_pattern"),
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
    "right_guan_light": "spleen",  # 胃併入脾系統
    "right_chi_heavy": "heart",  # 心包併入心
    "right_chi_light": "bladder",  # 三焦氣化併入膀胱
}

SYMPTOM_RULES = [
    (("心悸", "失眠", "胸悶", "心煩"), "heart", "熱證", 1.4),
    (("心慌", "氣短", "沒力", "疲倦"), "heart", "虛證", 1.2),
    (("易怒", "脅痛", "口苦", "頭痛"), "liver", "熱證", 1.3),
    (("胸脅脹", "經痛", "情緒鬱"), "liver", "實證", 1.2),
    (("腹脹", "消化不好", "便溏", "胃口差"), "spleen", "虛證", 1.3),
    (("口甜", "身體重", "濕疹"), "spleen", "實證", 1.1),
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


def apply_color_findings(evidence: dict[str, dict[str, float]], findings: list[str]) -> None:
    mapping = [
        ("心火", "heart", "熱證", 2.0),
        ("唇色偏紅", "heart", "熱證", 1.6),
        ("脾血虛", "spleen", "虛證", 2.2),
        ("蒼白", "spleen", "虛證", 1.8),
        ("肝瘀", "liver", "實證", 2.0),
        ("青紫", "liver", "實證", 1.8),
        ("萎黃", "spleen", "虛證", 1.8),
        ("苔白", "spleen", "虛證", 1.5),
        ("苔黃", "spleen", "熱證", 1.6),
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
        ("胃不好", "spleen", "虛證", 1.6),
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
        ("白苔很少", "spleen", "虛證", 1.8),
        ("胃虛", "spleen", "虛證", 1.6),
        ("黑灰苔", "kidney", "寒證", 1.8),
        ("實寒證", "kidney", "寒證", 1.4),
        ("虛寒證", "kidney", "寒證", 1.4),
        ("黃苔", "spleen", "熱證", 1.5),
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
        return "未定", 5, None
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


def overlay_from_pattern_label(label: str | None) -> str | None:
    mapping = {
        "實證熱證": "strong-hot.png",
        "實證寒證": "strong-cold.png",
        "虛證熱證": "weak-hot.png",
        "虛證寒證": "weak-cold.png",
        "濕氣較重": "mositure.png",
    }
    return mapping.get(label or "")
