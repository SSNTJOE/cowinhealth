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

BASE_ALLERGY_OPTIONS = (
    "蝦蟹",
    "芒果",
    "花生",
    "堅果",
    "雞蛋",
    "牛奶",
)

CONDITION_SET = set(CONDITION_OPTIONS)


def allergy_options() -> tuple[str, ...]:
    return BASE_ALLERGY_OPTIONS


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
        words = ALLERGY_EXCLUDE.get(allergy, (allergy,))
        for word in words:
            if word and word not in seen:
                seen.add(word)
                tokens.append(word)
    return tokens


def labels_from_text(text: str | None, allowed: tuple[str, ...]) -> list[str]:
    blob = text or ""
    return [label for label in allowed if label in blob]


def parse_label_list(raw, allowed: set[str], allowed_order: tuple[str, ...], field: str) -> list[str]:
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
        if label not in allowed:
            raise HTTPException(status_code=400, detail=f"{field} 含未知選項")
        if label not in seen:
            seen.add(label)
            picked.append(label)
    return [label for label in allowed_order if label in seen]


def decode_stored_labels(raw, allowed: tuple[str, ...]) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        values = raw
    else:
        try:
            values = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return labels_from_text(str(raw), allowed)
    if not isinstance(values, list):
        return labels_from_text(str(raw), allowed)
    found = {str(item) for item in values}
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
    labels = decode_stored_labels(user.get("allergies_json"), options)
    if labels:
        return labels
    return labels_from_text(user.get("medical_history"), options)


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
