"""Smoke tests for special-disease → TCM organ floors + score-1 consensus."""
from __future__ import annotations

from app.analysis import (
    clamp_organ_health_score,
    clamp_score_map_for_conditions,
    modalities_agree_organ_damage,
    organ_allows_severe,
    severe_health_gate,
    severe_symptom_wording,
)
from app.health_flags import (
    DISEASE_AFFECTED_ORGANS,
    canonicalize_condition_label,
    disease_affected_organs,
)


def expect(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> None:
    expect(canonicalize_condition_label("diabetes") == "糖尿病", "alias diabetes")
    expect(canonicalize_condition_label("高血壓") == "高血壓", "zh hypertension")
    expect(
        disease_affected_organs(["糖尿病"]) == DISEASE_AFFECTED_ORGANS["糖尿病"],
        "diabetes organs",
    )
    expect(
        disease_affected_organs(["diabetes"]) == frozenset({"spleen", "lung", "kidney"}),
        "diabetes alias organs",
    )
    expect(
        disease_affected_organs(["高血壓", "痛風"])
        == frozenset({"liver", "kidney", "heart", "spleen"}),
        "union organs",
    )
    expect(disease_affected_organs(["服用抗凝血劑"]) == frozenset(), "anticoagulant no organs")

    expect(organ_allows_severe("spleen", ["糖尿病"]), "diabetes opens spleen")
    expect(not organ_allows_severe("heart", ["糖尿病"]), "diabetes does not open heart")
    expect(organ_allows_severe("heart", ["中風"]), "stroke opens heart")
    expect(not organ_allows_severe("lung", ["高血壓"]), "HTN does not open lung")
    expect(
        organ_allows_severe("bladder", [], symptoms="很痛"),
        "severe wording opens any organ",
    )
    expect(severe_health_gate(["糖尿病"]), "gate from disease")
    expect(severe_symptom_wording("劇痛"), "symptom wording")

    # Unaffected organ floored at 4 even when raw score is 1.
    floored = clamp_score_map_for_conditions(
        {"heart_score": 1, "spleen_score": 1, "kidney_score": 1},
        ["糖尿病"],
    )
    expect(floored is not None, "floored map")
    assert floored is not None
    expect(floored["heart_score"] == 4, f"heart floor 4 got {floored['heart_score']}")
    expect(floored["spleen_score"] == 1, f"spleen may be 1 got {floored['spleen_score']}")
    expect(floored["kidney_score"] == 1, f"kidney may be 1 got {floored['kidney_score']}")

    # Score 1 needs face+tongue+stool+urine agreement.
    sources_agree = {
        "face": {"kidney_score": 1},
        "tongue_body": {"kidney_score": 2},
        "tongue_coat": {"kidney_score": 3},
        "stool": {"kidney_score": 1},
        "urine": {"kidney_score": 2},
    }
    expect(
        modalities_agree_organ_damage("kidney_score", sources_agree),
        "four modalities agree",
    )
    sources_missing_urine = {
        "face": {"kidney_score": 1},
        "tongue_body": {"kidney_score": 1},
        "stool": {"kidney_score": 1},
        "urine": None,
    }
    expect(
        not modalities_agree_organ_damage("kidney_score", sources_missing_urine),
        "missing urine blocks score 1",
    )
    final = clamp_score_map_for_conditions(
        {"kidney_score": 1, "heart_score": 1},
        ["糖尿病"],
        source_maps=sources_missing_urine,
        apply_one_consensus=True,
    )
    assert final is not None
    expect(final["kidney_score"] == 2, f"kidney without consensus → 2 got {final['kidney_score']}")
    expect(final["heart_score"] == 4, f"unaffected heart → 4 got {final['heart_score']}")

    final_ok = clamp_score_map_for_conditions(
        {"kidney_score": 1},
        ["糖尿病"],
        source_maps=sources_agree,
        apply_one_consensus=True,
    )
    assert final_ok is not None
    expect(final_ok["kidney_score"] == 1, "kidney with consensus stays 1")

    expect(clamp_organ_health_score(1, severe_gate=False) == 4, "quiet clamp")
    expect(clamp_organ_health_score(1, severe_gate=True, allow_one=False) == 2, "no-one clamp")
    print("OK disease-organ-floor")


if __name__ == "__main__":
    main()
