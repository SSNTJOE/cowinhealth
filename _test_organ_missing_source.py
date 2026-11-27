"""Smoke: missing-source prompts + bladder related-organ weighting (not default 10)."""

from app.syndrome import (
    BLADDER_RELATED_WEIGHTS,
    BLADDER_URINE_WEIGHT,
    compose_organ_health,
    serialize_organ_health,
    shoot_prompt_for_organ,
)


def expect(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def _weighted(parts: list[tuple[int, int]]) -> int:
    total_w = sum(w for _s, w in parts)
    return max(1, min(10, int(round(sum(s * w for s, w in parts) / total_w))))


def main() -> None:
    expect(shoot_prompt_for_organ("bladder") == "請拍攝尿尿以便判讀", "bladder prompt")
    expect("臉" in shoot_prompt_for_organ("heart"), "heart mentions face")
    expect("大便" in shoot_prompt_for_organ("large_intestine"), "LI mentions stool")
    expect("尿尿" in shoot_prompt_for_organ("kidney"), "kidney mentions urine")
    expect(BLADDER_RELATED_WEIGHTS[0][1] == "kidney", "kidney is first related")
    expect(BLADDER_URINE_WEIGHT >= BLADDER_RELATED_WEIGHTS[0][2], "urine weight ≥ kidney")

    # Face scored heart only; no 腎/肺/脾/肝 → bladder still missing (not 10).
    scores, breakdown = compose_organ_health(
        {
            "face": {"heart_score": 8},
            "tongue_body": None,
            "tongue_coat": None,
            "stool": None,
            "urine": None,
        },
        include_uterus=False,
    )
    expect(scores.get("heart_score") == 8, f"heart real score, got {scores}")
    expect("bladder_score" not in scores, f"bladder must be omitted, got {scores}")
    expect(breakdown["bladder"]["composite"] is None, "bladder composite null")
    expect(
        breakdown["bladder"]["shoot_prompt"] == "請拍攝尿尿以便判讀",
        f"bladder shoot prompt, got {breakdown['bladder']}",
    )

    payload = serialize_organ_health(scores, breakdown, ["face"])
    prompts = payload["missing_source_prompts"]
    expect(prompts.get("bladder") == "請拍攝尿尿以便判讀", f"prompts map, got {prompts}")
    expect(prompts.get("bladder_score") == "請拍攝尿尿以便判讀", "prompts by score key")
    expect("heart" not in prompts and "heart_score" not in prompts, "heart not missing")

    # Empty session: every organ missing (no invented tens).
    empty_scores, empty_bd = compose_organ_health(
        {"face": None, "urine": None},
        include_uterus=False,
    )
    expect(empty_scores == {}, f"empty composites, got {empty_scores}")
    expect(all(info["composite"] is None for info in empty_bd.values()), "all composites null")

    # Case A — urine only: bladder from urine signal.
    urine_only, urine_bd = compose_organ_health(
        {"urine": {"bladder_score": 6, "kidney_score": 6}},
        include_uterus=False,
    )
    # kidney also present from urine map → blended with urine bladder.
    expect("bladder_score" in urine_only, f"urine-only bladder, got {urine_only}")
    expected_a = _weighted([(6, BLADDER_URINE_WEIGHT), (6, 8)])
    expect(
        urine_only["bladder_score"] == expected_a,
        f"urine+kidney blend want {expected_a}, got {urine_only['bladder_score']}",
    )
    expect(urine_bd["bladder"]["shoot_prompt"] is None, "no prompt when scored")

    # Pure urine bladder with no related organ keys on the urine map.
    pure_urine, pure_bd = compose_organ_health(
        {"urine": {"bladder_score": 4}},
        include_uterus=False,
    )
    expect(pure_urine.get("bladder_score") == 4, f"pure urine bladder=4, got {pure_urine}")
    expect(pure_bd["bladder"]["bladder_related"].get("urine", {}).get("score") == 4, "urine detail")

    # Case B — organs only (no urine): 腎=4, 肺=8 → weighted bladder.
    organs_only, organs_bd = compose_organ_health(
        {
            "face": {"kidney_score": 4, "lung_score": 8, "heart_score": 9},
            "urine": None,
        },
        include_uterus=False,
    )
    expect("bladder_score" in organs_only, f"organs-only bladder, got {organs_only}")
    expected_b = _weighted([(4, 8), (8, 4)])
    expect(
        organs_only["bladder_score"] == expected_b,
        f"organs-only want {expected_b}, got {organs_only['bladder_score']}",
    )
    expect(organs_bd["bladder"]["shoot_prompt"] is None, "no urine prompt when 腎/肺 scored")
    expect(
        "bladder" not in serialize_organ_health(organs_only, organs_bd, ["face"])[
            "missing_source_prompts"
        ],
        "organs-only not in missing prompts",
    )

    # Case C — both urine + related: urine bladder=3, kidney=9, lung=9.
    both, both_bd = compose_organ_health(
        {
            "face": {"kidney_score": 9, "lung_score": 9},
            "urine": {"bladder_score": 3},
        },
        include_uterus=False,
    )
    expected_c = _weighted([(3, BLADDER_URINE_WEIGHT), (9, 8), (9, 4)])
    expect(
        both["bladder_score"] == expected_c,
        f"both want {expected_c}, got {both['bladder_score']}",
    )
    related = both_bd["bladder"]["bladder_related"]
    expect("urine" in related and "kidney" in related and "lung" in related, f"related {related}")
    # Kidney weight (8) pulls harder than lung (4) alone.
    low_kidney, _ = compose_organ_health(
        {"face": {"kidney_score": 2, "lung_score": 10}, "urine": None},
        include_uterus=False,
    )
    high_kidney, _ = compose_organ_health(
        {"face": {"kidney_score": 10, "lung_score": 2}, "urine": None},
        include_uterus=False,
    )
    expect(
        low_kidney["bladder_score"] < high_kidney["bladder_score"],
        f"腎 weight dominates: low={low_kidney['bladder_score']} high={high_kidney['bladder_score']}",
    )
    expect(low_kidney["bladder_score"] == _weighted([(2, 8), (10, 4)]), "low kidney blend")
    expect(high_kidney["bladder_score"] == _weighted([(10, 8), (2, 4)]), "high kidney blend")

    print("ok: organ missing-source prompts + bladder related weights")


if __name__ == "__main__":
    main()
