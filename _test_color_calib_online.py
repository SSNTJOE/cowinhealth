"""Unit tests for online color calibration (no MySQL / no GPU)."""

from __future__ import annotations

from app.color_calib_online import (
    apply_lighting_compensation,
    apply_threshold_adjustments,
    build_sample_from_report,
    empty_compensation,
    make_state_key,
    ml_hook_placeholder,
)


def test_state_keys():
    assert make_state_key("global", "face") == "global|face"
    assert make_state_key("device", "tongue", "android:Pixel-7").startswith("device:")
    assert "糖尿病" in make_state_key("disease", "face", "糖尿病")


def test_apply_lighting_compensation():
    online = empty_compensation()
    online["cct_bias_k"] = 100.0
    online["brightness_bias"] = 0.1
    cct, bright, gain, meta = apply_lighting_compensation(4200, 0.4, 1.0, online)
    assert abs(cct - 4300) < 1e-6
    assert gain > 1.0
    assert meta["online_cct_bias_k"] == 100.0
    assert meta["ml_hook"]["ready"] is False


def test_threshold_adjustments():
    base = {"body_heat_a_min": 41.0, "coat_yellow_b": 18.0, "shi_re_da": 6.0, "damp_db": 5.0}
    online = {"thresh_a_heat_adj": 1.5, "thresh_b_yellow_adj": -0.5, "thresh_delta_e_adj": 0.2}
    tongue = apply_threshold_adjustments(base, online, modality="tongue")
    assert tongue["body_heat_a_min"] == 42.5
    assert tongue["coat_yellow_b"] == 17.5
    face = apply_threshold_adjustments(base, online, modality="face")
    assert face["shi_re_da"] == 7.5
    assert face["damp_db"] == 4.5
    assert face["_online_applied"] is True


def test_build_sample_and_ml_hook():
    report = {
        "shot_type": "face",
        "color_temperature_k": 4500,
        "cct_raw": 4600,
        "brightness": 0.35,
        "brightness_raw": 0.33,
        "brightness_gain": 1.2,
        "color_label": "基本色",
        "hsv": {"hue": 20, "saturation": 0.3, "value": 0.7},
        "face_grid": {
            "complexion": {"lab": {"L": 64.0, "a_star": 12.5, "b_star": 19.0}, "bias": "基本色"},
            "color_health": {"blocks": [{"delta_e": 2.1}]},
        },
    }
    sample = build_sample_from_report(
        report,
        user_id="u1",
        record_id=9,
        device_key="web:windows",
        conditions=["糖尿病"],
        allergies=["花生"],
        quiet=False,
    )
    assert sample is not None
    assert sample["modality"] == "face"
    assert sample["L"] == 64.0
    assert sample["quiet"] == 0
    assert "糖尿病" in sample["conditions_json"]
    hook = ml_hook_placeholder()
    assert hook["ml_hook"]["version"] == 1
    assert hook["ml_hook"]["ready"] is False


if __name__ == "__main__":
    test_state_keys()
    test_apply_lighting_compensation()
    test_threshold_adjustments()
    test_build_sample_and_ml_hook()
    print("color_calib_online ok")
