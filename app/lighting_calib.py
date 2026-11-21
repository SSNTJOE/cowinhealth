"""Per-user / per-device lighting compensation that learns quietly.

Does not ask the user for a model name. Clients may send an optional device_hint
(User-Agent or Android Build fields). When missing, a shared "global" bucket is used.
"""

from __future__ import annotations

import json
import re
from typing import Any


DEFAULT_CCT_K = 4200.0
# Keep in sync with analysis.TARGET_RELATIVE_BRIGHTNESS
TARGET_BRIGHTNESS = 0.42
EMA_ALPHA = 0.18  # learn slowly so one bad shot does not dominate
BLEND_TO_BASELINE = 0.40  # how hard to pull this shot toward device baseline
MAX_CCT_BIAS_K = 800.0
MIN_GAIN_MUL = 0.75
MAX_GAIN_MUL = 1.35


def device_key_from_hint(hint: str | None) -> str:
    """Normalize a silent hint into a short stable key."""
    text = (hint or "").strip()
    if not text:
        return "global"
    lower = text.lower()
    # Android: "Android|Google|Pixel 7" style
    if lower.startswith("android|") or "android" in lower and "|" in text:
        parts = [p.strip() for p in text.split("|") if p.strip()]
        if len(parts) >= 3:
            return "android:" + re.sub(r"\s+", "-", f"{parts[1]}-{parts[2]}")[:64]
        if len(parts) >= 2:
            return "android:" + re.sub(r"\s+", "-", parts[-1])[:64]
    # Compact UA tokens
    browser = "web"
    for name in ("edg/", "chrome/", "firefox/", "safari/", "crios/", "fxios/"):
        if name in lower:
            browser = name.rstrip("/").replace("crios", "chrome").replace("fxios", "firefox")
            break
    os_name = "unknown"
    if "android" in lower:
        os_name = "android"
    elif "iphone" in lower or "ipad" in lower or "ios" in lower:
        os_name = "ios"
    elif "windows" in lower:
        os_name = "windows"
    elif "mac os" in lower or "macintosh" in lower:
        os_name = "mac"
    elif "cros" in lower:
        os_name = "chromeos"
    elif "linux" in lower:
        os_name = "linux"
    # Optional model-ish token from UA (Pixel, SM-G, iPhone)
    model = ""
    m = re.search(r"\b(pixel[^;\s)]+|sm-[a-z0-9]+|iphone\d*,\d*|ipad\d*,\d*)\b", lower)
    if m:
        model = "-" + m.group(1).replace(" ", "")
    return f"{browser}:{os_name}{model}"[:80]


def parse_calib_blob(raw: Any) -> dict[str, Any]:
    if not raw:
        return {"devices": {}}
    if isinstance(raw, dict):
        data = raw
    else:
        try:
            data = json.loads(str(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            return {"devices": {}}
    if not isinstance(data, dict):
        return {"devices": {}}
    devices = data.get("devices")
    if not isinstance(devices, dict):
        devices = {}
    return {"devices": devices}


def dump_calib(data: dict[str, Any]) -> str:
    return json.dumps(data or {"devices": {}}, ensure_ascii=False)


def _device_entry(calib: dict[str, Any], key: str) -> dict[str, Any]:
    devices = calib.setdefault("devices", {})
    entry = devices.get(key)
    if not isinstance(entry, dict):
        entry = {}
        devices[key] = entry
    entry.setdefault("n", 0)
    entry.setdefault("expected_cct", DEFAULT_CCT_K)
    entry.setdefault("expected_brightness", TARGET_BRIGHTNESS)
    entry.setdefault("cct_bias_k", 0.0)
    entry.setdefault("brightness_gain_mul", 1.0)
    return entry


def compensate_lighting(
    estimated_cct: float,
    estimated_brightness: float,
    brightness_gain: float,
    calib: dict[str, Any] | None,
    device_key: str | None,
) -> tuple[float, float, float, dict[str, Any]]:
    """Pull CCT/brightness toward this device's learned baseline, then apply gain mul."""
    key = device_key or "global"
    entry = _device_entry(calib or {"devices": {}}, key)
    expected_cct = float(entry.get("expected_cct") or DEFAULT_CCT_K)
    expected_bright = float(entry.get("expected_brightness") or TARGET_BRIGHTNESS)
    bias = float(entry.get("cct_bias_k") or 0.0)
    gain_mul = float(entry.get("brightness_gain_mul") or 1.0)
    gain_mul = max(MIN_GAIN_MUL, min(MAX_GAIN_MUL, gain_mul))

    # Blend measured CCT toward personal baseline (device-specific WB habit).
    blended_cct = (1.0 - BLEND_TO_BASELINE) * float(estimated_cct) + BLEND_TO_BASELINE * expected_cct
    compensated_cct = blended_cct + max(-MAX_CCT_BIAS_K, min(MAX_CCT_BIAS_K, bias))

    # Soft brightness blend before gain (underexposed phones learn higher mul).
    blended_bright = (1.0 - BLEND_TO_BASELINE * 0.5) * float(estimated_brightness) + (
        BLEND_TO_BASELINE * 0.5
    ) * expected_bright
    # Recompute gain toward target from blended brightness, then device mul.
    if blended_bright <= 1e-5:
        base_gain = float(brightness_gain)
    else:
        base_gain = float(TARGET_BRIGHTNESS) / float(blended_bright)
        base_gain = max(0.65, min(1.55, base_gain))
    compensated_gain = max(MIN_GAIN_MUL * 0.9, min(MAX_GAIN_MUL * 1.1, base_gain * gain_mul))

    meta = {
        "device_key": key,
        "estimated_cct": round(float(estimated_cct), 1),
        "compensated_cct": round(float(compensated_cct), 1),
        "estimated_brightness": round(float(estimated_brightness), 4),
        "compensated_gain": round(float(compensated_gain), 4),
        "n": int(entry.get("n") or 0),
        "cct_bias_k": round(bias, 1),
        "brightness_gain_mul": round(gain_mul, 4),
        "mode": "learned" if int(entry.get("n") or 0) > 0 else "bootstrap",
    }
    return compensated_cct, blended_bright, compensated_gain, meta


def learn_from_session(
    calib: dict[str, Any] | None,
    device_key: str | None,
    *,
    measured_cct: float,
    measured_brightness: float,
    quiet: bool,
    mean_score_delta: float | None = None,
) -> dict[str, Any]:
    """Update EMA baselines. Stronger updates on quiet (no severe-disease) sessions."""
    data = parse_calib_blob(calib)
    key = device_key or "global"
    entry = _device_entry(data, key)
    alpha = EMA_ALPHA if quiet else EMA_ALPHA * 0.35
    n = int(entry.get("n") or 0)
    # First samples learn faster.
    if n < 5:
        alpha = min(0.45, alpha + 0.12)

    prev_cct = float(entry.get("expected_cct") or measured_cct or DEFAULT_CCT_K)
    prev_bright = float(entry.get("expected_brightness") or measured_brightness or TARGET_BRIGHTNESS)
    entry["expected_cct"] = (1.0 - alpha) * prev_cct + alpha * float(measured_cct)
    entry["expected_brightness"] = (1.0 - alpha) * prev_bright + alpha * float(measured_brightness)

    # Bias: how far this camera usually sits from a neutral indoor reference.
    target_bias = float(DEFAULT_CCT_K) - float(entry["expected_cct"])
    prev_bias = float(entry.get("cct_bias_k") or 0.0)
    entry["cct_bias_k"] = max(
        -MAX_CCT_BIAS_K,
        min(MAX_CCT_BIAS_K, (1.0 - alpha) * prev_bias + alpha * target_bias * 0.35),
    )

    # Residual gain multiplier after per-shot exposure match. Quiet score drops → bump.
    prev_mul = float(entry.get("brightness_gain_mul") or 1.0)
    mul = (1.0 - alpha * 0.5) * prev_mul + (alpha * 0.5) * 1.0
    if quiet and mean_score_delta is not None:
        # Negative delta ⇒ scores fell ⇒ likely underexposure / cool cast → bump gain.
        mul += alpha * max(-0.08, min(0.08, -0.025 * float(mean_score_delta)))
    expect_b = float(entry["expected_brightness"]) or TARGET_BRIGHTNESS
    if expect_b < TARGET_BRIGHTNESS * 0.85:
        mul += alpha * 0.03
    elif expect_b > TARGET_BRIGHTNESS * 1.15:
        mul -= alpha * 0.02
    entry["brightness_gain_mul"] = max(MIN_GAIN_MUL, min(MAX_GAIN_MUL, mul))
    entry["n"] = n + 1
    entry["last_cct"] = round(float(measured_cct), 1)
    entry["last_brightness"] = round(float(measured_brightness), 4)
    data["devices"][key] = entry
    return data
