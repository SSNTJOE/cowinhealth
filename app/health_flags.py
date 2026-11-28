from __future__ import annotations

import json

from fastapi import HTTPException

CONDITION_OPTIONS = (
    "糖尿病",
    "中風",
    "痛風",
    "腎臟病",
    "肝病",
    "高血壓",
    "服用抗凝血劑",
)

# 特殊疾病 → 中醫受損臟腑 (organ keys). Unaffected organs keep quiet floor 4.
# 服用抗凝血劑 is a condition checkbox but not a TCM organ-damage disease.
DISEASE_AFFECTED_ORGANS: dict[str, frozenset[str]] = {
    "糖尿病": frozenset({"spleen", "lung", "kidney"}),
    "中風": frozenset({"liver", "heart", "kidney"}),
    "痛風": frozenset({"spleen", "kidney"}),
    "腎臟病": frozenset({"kidney", "spleen", "lung", "heart"}),
    "肝病": frozenset({"liver", "gallbladder", "spleen", "stomach"}),
    "高血壓": frozenset({"liver", "kidney", "heart"}),
}

# Aliases / English tokens → canonical CONDITION_OPTIONS label.
CONDITION_ALIASES: dict[str, str] = {
    "diabetes": "糖尿病",
    "diabetic": "糖尿病",
    "stroke": "中風",
    "cva": "中風",
    "gout": "痛風",
    "kidney disease": "腎臟病",
    "kidney": "腎臟病",
    "renal": "腎臟病",
    "liver disease": "肝病",
    "hepatitis": "肝病",
    "liver": "肝病",
    "hypertension": "高血壓",
    "high blood pressure": "高血壓",
    "htn": "高血壓",
}


def canonicalize_condition_label(label: str | None) -> str | None:
    """Map alias / English tokens onto CONDITION_OPTIONS labels."""
    text = (label or "").strip()
    if not text:
        return None
    if text in CONDITION_SET:
        return text
    lower = text.lower()
    mapped = CONDITION_ALIASES.get(lower)
    if mapped:
        return mapped
    for alias, canon in CONDITION_ALIASES.items():
        if alias in lower:
            return canon
    for canon in CONDITION_OPTIONS:
        if canon in text:
            return canon
    return None


def disease_affected_organs(
    conditions: list[str] | tuple[str, ...] | None = None,
) -> frozenset[str]:
    """Union of TCM organs damaged by checked special diseases (not anticoagulant)."""
    affected: set[str] = set()
    for raw in conditions or ():
        canon = canonicalize_condition_label(str(raw or ""))
        if not canon:
            continue
        organs = DISEASE_AFFECTED_ORGANS.get(canon)
        if organs:
            affected.update(organs)
    return frozenset(affected)


BASE_ALLERGY_OPTIONS = (
    "蝦蟹",
    "魚",
    "芒果",
    "花生",
    "堅果",
    "雞蛋",
    "牛奶",
    "優格",
    "南瓜",
    "味噌",
    "夏威夷豆",
    "大麥",
    "奶油",
    "小麥",
    "山葵",
    "杏仁果",
    "松子",
    "栗子",
    "核桃",
    "淡菜",
    "燕麥",
    "牡蠣",
    "白芝麻",
    "皮蛋",
    "芥末",
    "花生油",
    "芹菜",
    "葡萄酒",
    "蕎麥",
    "蛋",
    "蛋白",
    "蛋黃",
    "蛤蜊",
    "豆干",
    "豆漿",
    "豆腐",
    "起司",
    "醋",
    "醬油",
    "麻油",
    "黃豆",
    "黃豆芽",
    "黃酒",
    "黑豆",
)

# Raw Recipe.xls / legacy profile tokens that map onto the 蝦蟹 checkbox.
CRUSTACEAN_ALLERGY_TOKENS = frozenset(
    {"蝦蟹", "蝦", "蝦米", "蝦仁", "龍蝦", "螃蟹", "蟹"}
)

# Named fish (and related) tokens that map onto the 魚 checkbox.
# Substring "魚" in canonicalize also covers other Recipe.xls species.
FISH_ALLERGY_TOKENS = frozenset(
    {
        "魚",
        "鯉魚",
        "鯽魚",
        "鱸魚",
        "草魚",
        "鰱魚",
        "青魚",
        "帶魚",
        "黃魚",
        "鯖魚",
        "鮪魚",
        "鮭魚",
        "鱈魚",
        "鯛魚",
        "秋刀魚",
        "沙丁魚",
        "鰻魚",
        "鱔魚",
        "虱目魚",
        "石斑魚",
        "比目魚",
        "鯊魚",
        "烏魚",
        "鰹魚",
        "吳郭魚",
        "鮑魚",
        "魷魚",
        "章魚",  # no 魚 glyph; still treated as fish allergy token
    }
)

CONDITION_SET = set(CONDITION_OPTIONS)


def canonicalize_allergy_label(label: str | None) -> str | None:
    """Map legacy / raw allergen tokens onto consolidated checkbox labels."""
    text = (label or "").strip()
    if not text:
        return None
    if text in CRUSTACEAN_ALLERGY_TOKENS:
        return "蝦蟹"
    if text in FISH_ALLERGY_TOKENS or "魚" in text:
        return "魚"
    return text


def allergy_options() -> tuple[str, ...]:
    from .recipes import allergen_labels

    ordered: list[str] = []
    seen: set[str] = set()
    for label in (*BASE_ALLERGY_OPTIONS, *allergen_labels()):
        canon = canonicalize_allergy_label(label)
        if canon and canon not in seen:
            seen.add(canon)
            ordered.append(canon)
    return tuple(ordered)


def allergy_option_set() -> set[str]:
    return set(allergy_options())


ALLERGY_OPTIONS = BASE_ALLERGY_OPTIONS
ALLERGY_SET = set(BASE_ALLERGY_OPTIONS)

DIET_BIAS = {
    "糖尿病": "低GI控糖",
    "中風": "清淡少油血壓管理教學",
    "痛風": "低普林",
    "腎臟病": "控鉀控磷適量蛋白",
    "肝病": "少油膩戒酒精",
    "高血壓": "少鈉低鹽",
    "服用抗凝血劑": "避免過量高維生素K菠菜不過量",
}

ACUPOINT_BIAS = {
    "糖尿病": "消渴保健穴位教學",
    "中風": "復健輔助穴位輕柔教學",
    "痛風": "痛風保健穴位勿自行放血",
    "腎臟病": "腎俞輕柔按摩教學",
    "肝病": "肝區保健輕柔按摩",
    "高血壓": "血壓保健穴位勿強刺激",
    "服用抗凝血劑": "輕柔穴位避免放血破血刮痧出血",
}

ALLERGY_EXCLUDE = {
    "蝦蟹": ("蝦蟹", "蝦", "蝦米", "蝦仁", "龍蝦", "螃蟹", "蟹"),
    # "魚" substring match covers species tokens; named fish kept for exact cell tokens.
    "魚": tuple(sorted(FISH_ALLERGY_TOKENS)),
    "芒果": ("芒果",),
    "花生": ("花生", "花生油"),
    "堅果": ("堅果", "核桃", "杏仁", "杏仁果", "腰果", "夏威夷豆", "松子", "栗子", "白果"),
    "雞蛋": ("雞蛋", "蛋白", "蛋黃", "皮蛋", "鵪鶉蛋", "蛋奶"),
    "牛奶": ("牛奶", "羊奶", "奶油", "起司", "優格", "乳製品"),
}


def allergy_exclude_tokens(allergies: list[str] | None) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for allergy in allergies or []:
        canon = canonicalize_allergy_label(allergy) or (allergy or "").strip()
        words = ALLERGY_EXCLUDE.get(canon, (canon,))
        for word in words:
            if word and word not in seen:
                seen.add(word)
                tokens.append(word)
    return tokens


def labels_from_text(text: str | None, allowed: tuple[str, ...]) -> list[str]:
    blob = text or ""
    return [label for label in allowed if label in blob]


def labels_from_allergy_text(text: str | None, allowed: tuple[str, ...]) -> list[str]:
    blob = text or ""
    if not blob:
        return []
    picked: list[str] = []
    for label in allowed:
        tokens = ALLERGY_EXCLUDE.get(label, (label,))
        if label in blob or any(token and token in blob for token in tokens):
            picked.append(label)
    return picked


def parse_label_list(
    raw,
    allowed: set[str],
    allowed_order: tuple[str, ...],
    field: str,
    *,
    canonicalize=None,
) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"{field} 不是合法 JSON") from exc
    if not isinstance(raw, list):
        raise HTTPException(status_code=400, detail=f"{field} 須為陣列")
    picked: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            raise HTTPException(status_code=400, detail=f"{field} 項目不正確")
        label = item.strip()
        if canonicalize is not None:
            label = canonicalize(label) or ""
        if label not in allowed:
            raise HTTPException(status_code=400, detail=f"{field} 含未知選項")
        if label not in seen:
            seen.add(label)
            picked.append(label)
    return [label for label in allowed_order if label in seen]


def decode_stored_labels(raw, allowed: tuple[str, ...], *, canonicalize=None) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        values = raw
    else:
        try:
            values = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            if canonicalize is not None:
                return labels_from_allergy_text(str(raw), allowed)
            return labels_from_text(str(raw), allowed)
    if not isinstance(values, list):
        if canonicalize is not None:
            return labels_from_allergy_text(str(raw), allowed)
        return labels_from_text(str(raw), allowed)
    found: set[str] = set()
    for item in values:
        text = str(item).strip()
        if canonicalize is not None:
            text = canonicalize(text) or ""
        if text:
            found.add(text)
    return [label for label in allowed if label in found]


def user_conditions(user: dict | None) -> list[str]:
    user = user or {}
    labels = decode_stored_labels(user.get("conditions_json"), CONDITION_OPTIONS)
    if labels:
        return labels
    return labels_from_text(user.get("medical_history"), CONDITION_OPTIONS)


def user_allergies(user: dict | None) -> list[str]:
    user = user or {}
    options = allergy_options()
    labels = decode_stored_labels(
        user.get("allergies_json"), options, canonicalize=canonicalize_allergy_label
    )
    if labels:
        return labels
    return labels_from_allergy_text(user.get("medical_history"), options)


def history_summary(conditions: list[str], allergies: list[str]) -> str | None:
    parts: list[str] = []
    if conditions:
        parts.append("特殊疾病：" + "、".join(conditions))
    if allergies:
        parts.append("過敏：" + "、".join(allergies))
    text = "；".join(parts).strip()
    return text or None


def dumps_labels(labels: list[str]) -> str:
    return json.dumps(labels, ensure_ascii=False)
