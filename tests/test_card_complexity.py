"""Tests for the card complexity scoring framework."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from game_setup.loaders import load_card_catalog
from game_setup.types import CardDefinition
from scripts.card_complexity_review import (
    REFERENCE_MAX_WEIGHTED,
    _card_id_from_test_stem,
    _count_test_functions,
    count_card_tests,
    rank_results,
    score_card,
    score_catalog,
    tier_label,
    write_artifacts,
)

BASE_DIR = Path(__file__).resolve().parents[1]
CARDS_DIR = BASE_DIR / "data" / "cards"


def _action(
    *,
    op: str = "gain_resource",
    target_scope: str = "self",
    timing: str = "immediate",
    optional: bool = False,
    kind: str = "fixed",
    value: int | None = 1,
    filters: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    action_id: str = "action_1",
) -> dict[str, Any]:
    return {
        "action_id": action_id,
        "op": op,
        "target_scope": target_scope,
        "timing": timing,
        "optional": optional,
        "quantity": {"kind": kind, "value": value},
        "filters": filters or [],
        "source_fragment": "",
        "metadata": metadata or {},
    }


def _card(
    *,
    card_id: str = "test_card",
    actions: list[dict[str, Any]] | None = None,
    execution_model: dict[str, Any] | None = None,
    rules_text: str = "Gain 1 power.",
    global_conditions: list[dict[str, str]] | None = None,
    state_contract: dict[str, Any] | None = None,
) -> CardDefinition:
    flat_actions = actions or []
    return CardDefinition.model_validate(
        {
            "card_id": card_id,
            "name": card_id.replace("_", " ").title(),
            "cost": 0,
            "aspect": "obedience",
            "rules_text": rules_text,
            "execution_model": execution_model or {"kind": "sequence", "actions": flat_actions},
            "actions": flat_actions,
            "global_conditions": global_conditions or [],
            "state_contract": state_contract or {"reads": [], "writes": []},
            "effect_key": "generic_card",
        }
    )


def _sequence_model(actions: list[dict[str, Any]]) -> dict[str, Any]:
    return {"kind": "sequence", "actions": actions}


def _modal_model(options: list[list[dict[str, Any]]]) -> dict[str, Any]:
    return {
        "kind": "modal_choice",
        "selection": "exactly_one",
        "options": [
            {"option_id": f"option_{index}", "actions": option}
            for index, option in enumerate(options, 1)
        ],
    }


def _repeat_model(options: list[list[dict[str, Any]]], repeat_count: int = 2) -> dict[str, Any]:
    return {
        "kind": "repeat_choice",
        "repeat_count": repeat_count,
        "allow_repeat": True,
        "options": [
            {"option_id": f"option_{index}", "actions": option}
            for index, option in enumerate(options, 1)
        ],
    }


def test_trivial_card_scores_in_low_band() -> None:
    result = score_card(_card(actions=[_action()]))

    assert 0.0 <= result.total < 20.0
    assert result.tier == "Low"


def test_high_tier_ops_outscore_gain_only_card() -> None:
    simple = score_card(_card(actions=[_action(op="gain_resource", kind="fixed", value=1)]))
    complex_card = score_card(
        _card(
            actions=[
                _action(op="devour_cost", kind="unspecified", value=None),
                _action(op="custom_effect", kind="fixed", value=1),
            ]
        )
    )

    assert complex_card.total > simple.total


def test_modal_outscores_sequence_and_repeat_outscores_modal() -> None:
    action = _action(op="place_spy", target_scope="board_site", kind="fixed", value=1)
    sequence = score_card(_card(actions=[action], execution_model=_sequence_model([action])))
    modal = score_card(
        _card(actions=[action, action], execution_model=_modal_model([[action], [action]]))
    )
    repeat = score_card(
        _card(actions=[action, action], execution_model=_repeat_model([[action], [action]]))
    )

    assert modal.total > sequence.total
    assert repeat.total > modal.total


def test_dynamic_quantities_outscore_fixed() -> None:
    fixed = score_card(_card(actions=[_action(kind="fixed", value=1)]))
    unspecified = score_card(_card(actions=[_action(kind="unspecified", value=None)]))
    variable = score_card(_card(actions=[_action(kind="variable_repeat", value=None)]))

    assert unspecified.total > fixed.total
    assert variable.total > unspecified.total


def test_end_of_turn_timing_adds_dynamism() -> None:
    immediate = score_card(_card(actions=[_action(op="promote_card", timing="immediate")]))
    deferred = score_card(_card(actions=[_action(op="promote_card", timing="end_of_turn")]))

    assert deferred.dimensions["D3"].raw > immediate.dimensions["D3"].raw
    assert deferred.total > immediate.total


def test_unknown_op_falls_back_to_tier_two_and_is_unmapped() -> None:
    result = score_card(_card(actions=[_action(op="some_unknown_op")]))

    assert result.dimensions["D2"].raw == 2.0
    assert "op:some_unknown_op" in result.unmapped


def test_unknown_quantity_kind_is_flagged() -> None:
    result = score_card(_card(actions=[_action(kind="mystery_quantity", value=None)]))

    assert "quantity:mystery_quantity" in result.unmapped
    assert result.dimensions["D3"].raw >= 2.0


def test_unknown_condition_type_is_flagged() -> None:
    result = score_card(
        _card(global_conditions=[{"condition_type": "strange_condition", "description": ""}])
    )

    assert "condition:strange_condition" in result.unmapped


def test_factors_are_non_empty_for_non_trivial_card() -> None:
    result = score_card(
        _card(
            actions=[
                _action(op="devour_cost", target_scope="hand", kind="unspecified", value=None),
                _action(
                    op="supplant_troop",
                    target_scope="board_site",
                    kind="fixed",
                    value=1,
                    filters=["white_troop_only"],
                    metadata={"targeting": "anywhere", "ignore_presence_requirement": True},
                ),
            ],
            rules_text="Devour a card to supplant a white troop. Then supplant another.",
        )
    )

    assert result.factors
    assert all(isinstance(factor, str) and factor for factor in result.factors)


def test_total_is_capped_at_one_hundred() -> None:
    many_actions = [
        _action(
            op="custom_effect",
            target_scope="opponent_player",
            kind="variable_repeat",
            value=None,
            optional=True,
            filters=["filter_a", "filter_b"],
            metadata={"count_from": "x"},
            action_id=f"action_{index}",
        )
        for index in range(20)
    ]
    result = score_card(_card(actions=many_actions))

    assert result.total <= 100.0


def test_tier_label_bands() -> None:
    assert tier_label(0.0) == "Low"
    assert tier_label(19.9) == "Low"
    assert tier_label(20.0) == "Moderate"
    assert tier_label(40.0) == "High"
    assert tier_label(60.0) == "Very High"
    assert tier_label(80.0) == "Extreme"


def test_reference_max_is_positive() -> None:
    assert REFERENCE_MAX_WEIGHTED > 0.0


def test_integration_scores_full_catalog() -> None:
    catalog = load_card_catalog(CARDS_DIR)
    results = score_catalog(catalog)

    assert len(results) == 125

    by_id = {result.card_id: result for result in results}

    assert by_id["soldier"].tier == "Low"
    assert by_id["aboleth"].total > by_id["soldier"].total
    assert by_id["demogorgon"].total > by_id["soldier"].total

    for result in results:
        assert 0.0 <= result.total <= 100.0


def test_ranking_is_deterministic() -> None:
    catalog = load_card_catalog(CARDS_DIR)
    results = score_catalog(catalog)

    ranked = rank_results(results)
    assert [result.card_id for result in ranked] == sorted(
        (result.card_id for result in ranked),
        key=lambda card_id: (
            -next(result.total for result in ranked if result.card_id == card_id),
            card_id,
        ),
    )
    assert ranked == sorted(ranked, key=lambda result: (-result.total, result.card_id))


def test_write_artifacts_produces_four_files(tmp_path: Path) -> None:
    catalog = load_card_catalog(CARDS_DIR)
    ranked = rank_results(score_catalog(catalog))

    paths = write_artifacts(ranked, tmp_path)

    assert len(paths) == 4
    for path in paths:
        assert path.is_file()

    md_path = tmp_path / "complexity_review.md"
    csv_path = tmp_path / "complexity_review.csv"
    json_path = tmp_path / "complexity_review.json"
    xlsx_path = tmp_path / "complexity_review.xlsx"
    assert md_path.exists()
    assert csv_path.exists()
    assert json_path.exists()
    assert xlsx_path.exists()

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        rows = list(reader)

    assert len(rows) == 126
    assert rows[0][0] == "rank"
    assert rows[0][1] == "card_id"
    assert "score" in rows[0]
    assert "tier" in rows[0]
    assert "test_count" in rows[0]


def test_card_id_from_test_stem_exact_and_variant() -> None:
    card_ids = {"conjurer", "air_elemental", "air_elemental_myrmidon", "vampire", "vampire_spawn"}

    assert _card_id_from_test_stem("test_card_conjurer", card_ids) == "conjurer"
    assert _card_id_from_test_stem("test_card_conjurer_behavior", card_ids) == "conjurer"
    assert _card_id_from_test_stem("test_card_air_elemental_myrmidon", card_ids) == "air_elemental_myrmidon"
    assert _card_id_from_test_stem("test_card_vampire_spawn", card_ids) == "vampire_spawn"
    assert _card_id_from_test_stem("test_card_scenario_market_policy", card_ids) is None
    assert _card_id_from_test_stem("test_card_unknown", card_ids) is None


def test_count_test_functions_counts_def_test_only(tmp_path: Path) -> None:
    path = tmp_path / "test_card_conjurer.py"
    path.write_text(
        "def test_a():\n    pass\n\ndef test_b():\n    pass\n\ndef _helper():\n    pass\n",
        encoding="utf-8",
    )

    assert _count_test_functions(path) == 2


def test_count_card_tests_integrates_with_catalog() -> None:
    catalog = load_card_catalog(CARDS_DIR)
    card_ids = {card.card_id for card in catalog.cards}

    counts = count_card_tests(BASE_DIR / "tests", card_ids)

    assert counts["neogi"] == 1
    assert counts["conjurer"] >= 1
    assert counts["mercenary_squad"] == 2
    assert counts["soldier"] >= 1
    for card_id in card_ids:
        assert card_id in counts
