"""Tests for engine_c/bindings/label_enrich.py and view.py label plumbing."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bindings"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from label_enrich import (
    _action_focus_aspect,
    _action_has_focus_requirement,
    _describe_option,
    _describe_single_action,
    enrich_label,
)


class TestEnrichLabel:
    def test_play_card_passthrough(self):
        result = enrich_label("play_card", "Play Noble", {"card_id": "noble"})
        assert result == "Play Noble"

    def test_end_main_phase_passthrough(self):
        result = enrich_label("end_main_phase", "End main phase", {})
        assert result == "End main phase"

    def test_assassinate_passthrough(self):
        result = enrich_label(
            "assassinate",
            "Assassinate white troop at Gauntlgrym",
            {"target_node_id": "site_gauntlgrym", "target_slot_index": 0},
        )
        assert result == "Assassinate white troop at Gauntlgrym"

    def test_unknown_move_passthrough(self):
        result = enrich_label("unknown", "Move", {})
        assert result == "Move"

    def test_activate_ability_enriches_with_card_name(self):
        result = enrich_label(
            "activate_ability",
            "Activate ambush",
            {"card_id": "advance_scout", "ability_key": "ambush"},
        )
        assert "Advance Scout" in result
        assert "ability" in result
        assert "Activate" in result

    def test_activate_ability_falls_back_when_no_card_id(self):
        result = enrich_label("activate_ability", "Activate ambush", {"ability_key": "ambush"})
        assert result == "Activate ambush"

    def test_decline_ability_enriches_with_card_name(self):
        result = enrich_label(
            "decline_ability",
            "Decline ambush",
            {"card_id": "advance_scout", "ability_key": "ambush"},
        )
        assert "Advance Scout" in result
        assert "Decline" in result

    def test_decline_ability_falls_back_when_no_card_id(self):
        result = enrich_label("decline_ability", "Decline ambush", {"ability_key": "ambush"})
        assert result == "Decline ambush"

    def test_resolve_generic_with_known_card_target(self):
        result = enrich_label(
            "resolve_generic",
            "Resolve assassinate_troop",
            {"action_id": "assassinate_troop", "target_id": "advance_scout", "selection_index": 0},
        )
        assert "Advance Scout" in result
        assert "Choose for" in result

    def test_resolve_generic_with_unknown_target_falls_back_to_humanized_action(self):
        result = enrich_label(
            "resolve_generic",
            "Resolve assassinate_troop",
            {"action_id": "assassinate_troop", "target_id": "some_random_id", "selection_index": 0},
        )
        assert result == "Resolve Assassinate troop"

    def test_resolve_generic_no_target_falls_back_to_humanized_action(self):
        result = enrich_label(
            "resolve_generic",
            "Resolve assassinate_troop",
            {"action_id": "assassinate_troop", "selection_index": 0},
        )
        assert result == "Resolve Assassinate troop"

    def test_resolve_generic_uses_source_card_id(self):
        result = enrich_label(
            "resolve_generic",
            "Resolve assassinate_troop",
            {"action_id": "assassinate_troop", "target_id": "some_random_id", "selection_index": 0},
            source_card_id="advance_scout",
        )
        assert "Advance Scout" in result
        assert "Choose for" in result

    def test_resolve_generic_source_card_id_beats_action_id(self):
        result = enrich_label(
            "resolve_generic",
            "Resolve assassinate_troop",
            {"action_id": "assassinate_troop", "selection_index": 0},
            source_card_id="advance_scout",
        )
        assert "Advance Scout" in result
        assert "Choose for" in result

    def test_resolve_generic_humanizes_different_actions(self):
        result = enrich_label(
            "resolve_generic",
            "Resolve deploy_troops",
            {"action_id": "deploy_troops", "selection_index": 0},
        )
        assert result == "Resolve Deploy troops"


    def test_resolve_generic_advance_scout_still_legacy(self):
        result = enrich_label(
            "resolve_generic",
            "Resolve supplant_troop",
            {"action_id": "action_1", "selection_index": 0},
            source_card_id="advance_scout",
        )
        assert "Advance Scout" in result

    def test_resolve_generic_aboleth_option1(self):
        result = enrich_label(
            "resolve_generic",
            "Resolve option_1",
            {"action_id": "option_1", "selection_index": 0},
            source_card_id="aboleth",
            is_option_choice=True,
        )
        assert result == "Aboleth: Place spy (x2)"

    def test_resolve_generic_aboleth_option2(self):
        result = enrich_label(
            "resolve_generic",
            "Resolve option_2",
            {"action_id": "option_2", "selection_index": 0},
            source_card_id="aboleth",
            is_option_choice=True,
        )
        assert result == "Aboleth: Draw cards (from spies on board)"

    def test_resolve_generic_aboleth_action_with_target(self):
        "Relocation: place_spy with a source node in target_id labels a spy move."
        result = enrich_label(
            "resolve_generic",
            "Resolve site_gauntlgrym",
            {"action_id": "site_gauntlgrym", "target_id": "site_blingdenfire", "selection_index": 0},
            source_card_id="aboleth", card_action_id="option_1_action_1",
        )
        assert result == "Aboleth: Move your spy from Site blingdenfire to Site gauntlgrym"
    def test_resolve_generic_true_fallback(self):
        result = enrich_label(
            "resolve_generic",
            "Resolve",
            {"action_id": "", "selection_index": 0},
        )
        assert result == "Finish resolving "

    def test_resolve_generic_target_selection_uses_card_action_id(self):
        "For target selection, card_action_id comes from state, not the move."
        result = enrich_label(
            "resolve_generic",
            "Resolve site_gauntlgrym",
            {"action_id": "site_gauntlgrym", "selection_index": 0},
            source_card_id="aboleth",
            card_action_id="option_1_action_1",
            is_option_choice=False,
        )
        assert result == "Aboleth: Place spy at Site gauntlgrym"

    def test_resolve_generic_option_choice_uses_move_action_id(self):
        "For option choice, action_id comes from the move (it is the option_id)."
        result = enrich_label(
            "resolve_generic",
            "Resolve option_1",
            {"action_id": "option_1", "selection_index": 0},
            source_card_id="aboleth",
            card_action_id="",
            is_option_choice=True,
        )
        assert result == "Aboleth: Place spy (x2)"

    def test_resolve_generic_draw_cards_shows_metadata(self):
        "draw_cards actions should surface count_from metadata."
        result = enrich_label(
            "resolve_generic",
            "Resolve option_2",
            {"action_id": "option_2", "selection_index": 0},
            source_card_id="aboleth",
            is_option_choice=True,
        )
        assert "Draw cards (from spies on board)" in result

    def test_empty_data_dict(self):
        result = enrich_label("play_card", "Play Noble", {})
        assert result == "Play Noble"


    def test_draw_cards_shows_actual_spy_count(self):
        result = enrich_label(
            "resolve_generic",
            "Resolve option_2",
            {"action_id": "option_2", "selection_index": 0},
            source_card_id="aboleth",
            is_option_choice=True,
            player_spy_count=3,
        )
        assert result == "Aboleth: Draw 3 cards (from 3 spies on board)"

    def test_draw_cards_with_one_spy(self):
        result = enrich_label(
            "resolve_generic",
            "Resolve option_2",
            {"action_id": "option_2", "selection_index": 0},
            source_card_id="aboleth",
            is_option_choice=True,
            player_spy_count=1,
        )
        assert result == "Aboleth: Draw 1 card (from 1 spy on board)"

    def test_draw_cards_falls_back_when_no_spy_count(self):
        result = enrich_label(
            "resolve_generic",
            "Resolve option_2",
            {"action_id": "option_2", "selection_index": 0},
            source_card_id="aboleth",
            is_option_choice=True,
        )
        assert result == "Aboleth: Draw cards (from spies on board)"

    def test_ambassador_promote_card_with_noble_target(self):
        "Sequence execution model: promote_card with card target."
        result = enrich_label(
            "resolve_generic",
            "Resolve noble",
            {"action_id": "noble", "selection_index": 0},
            source_card_id="ambassador",
            card_action_id="action_1",
        )
        assert result == "Ambassador: Promote card Noble"

    def test_ambassador_promote_card_with_guard_target(self):
        "Sequence execution model: promote_card with another card."
        result = enrich_label(
            "resolve_generic",
            "Resolve house_guard",
            {"action_id": "house_guard", "selection_index": 0},
            source_card_id="ambassador",
            card_action_id="action_1",
        )
        assert result == "Ambassador: Promote card House Guard"

    def test_sequence_model_action_without_target(self):
        "Sequence model action that does not need a target selection (skip marker)."
        result = enrich_label(
            "resolve_generic",
            "Resolve action_1",
            {"action_id": "", "selection_index": 0},
            source_card_id="ambassador",
            card_action_id="action_1",
        )
        assert result == "Skip Promote card for Ambassador"

    def test_promote_card_with_source_enrichment(self):
        "promote_card with a known promotion source prepends the source name."
        result = enrich_label(
            "promote_card",
            "Promote Noble",
            {"card_id": "noble"},
            promotion_source_card_id="ambassador",
        )
        assert result == "Ambassador: Promote card Noble"

    def test_promote_card_with_unknown_source(self):
        "promote_card with unknown source falls back to raw label."
        result = enrich_label(
            "promote_card",
            "Promote House Guard",
            {"card_id": "house_guard"},
            promotion_source_card_id="unknown_card_id",
        )
        assert result == "Promote House Guard"

    def test_promote_card_without_source(self):
        "promote_card without a promotion source keeps the C label."
        result = enrich_label(
            "promote_card",
            "Promote Noble",
            {"card_id": "noble"},
        )
        assert result == "Promote Noble"

    def test_promote_card_with_source_and_aspect(self):
        "promote_card with source and aspect includes both in the label."
        result = enrich_label(
            "promote_card",
            "Promote Noble",
            {"card_id": "noble"},
            promotion_source_card_id="air_elemental_myrmidon",
            promotion_aspect="obedience",
        )
        assert result == "Air Elemental Myrmidon: Promote card Noble (Obedience)"

    def test_promote_card_with_aspect_no_source(self):
        "promote_card with aspect but no source appends aspect suffix."
        result = enrich_label(
            "promote_card",
            "Promote Noble",
            {"card_id": "noble"},
            promotion_aspect="obedience",
        )
        assert result == "Promote Noble (Obedience)"

    def test_promote_card_with_source_empty_aspect(self):
        "promote_card with source and empty aspect matches no-aspect behavior."
        result = enrich_label(
            "promote_card",
            "Promote Noble",
            {"card_id": "noble"},
            promotion_source_card_id="ambassador",
            promotion_aspect="",
        )
        assert result == "Ambassador: Promote card Noble"

class TestCDescribeIntegration:
    """Integration tests that call the C engine through ctypes."""

    @pytest.fixture(autouse=True)
    def _ensure_dll(self):
        from engine_bindings import _lib
        if _lib is None:
            pytest.skip("engine_c DLL not available")
        _lib.intern_init(4096)
        yield
        _lib.intern_destroy()

    def test_deploy_label_uses_friendly_node_name(self):
        import ctypes

        from engine_bindings import Move, _lib

        node_id = _lib.intern(b"site_gauntlgrym")
        m = Move()
        m.type = 5
        m.data.deploy.node_id = node_id
        m.data.deploy.slot_index = 0
        m.player_index = 0

        buf = ctypes.create_string_buffer(256)
        node_ids = (ctypes.c_char_p * 1)(b"site_gauntlgrym")
        node_labels = (ctypes.c_char_p * 1)(b"Gauntlgrym")

        _lib.engine_describe_move(None, ctypes.byref(m), node_ids, node_labels, 1, buf, 256)
        label = buf.value.decode()
        assert "Gauntlgrym" in label
        assert "Deploy" in label

    def test_deploy_label_humanizes_without_node_names(self):
        import ctypes

        from engine_bindings import Move, _lib

        node_id = _lib.intern(b"site_test")
        m = Move()
        m.type = 5
        m.data.deploy.node_id = node_id
        m.data.deploy.slot_index = 0
        m.player_index = 0

        buf = ctypes.create_string_buffer(256)
        _lib.engine_describe_move(None, ctypes.byref(m), None, None, 0, buf, 256)
        label = buf.value.decode()
        assert "Site test" in label
        assert "site_test" not in label

    def test_ettin_option1_label(self):
        """Ettin option 1: deploy 3 troops."""
        result = enrich_label(
            "resolve_generic",
            "Resolve option_1",
            {"action_id": "option_1", "selection_index": 0},
            source_card_id="ettin",
            is_option_choice=True,
        )
        assert result == "Ettin: Deploy troops (x3)"

    def test_ettin_option2_label(self):
        """Ettin option 2: assassinate 2 white troops."""
        result = enrich_label(
            "resolve_generic",
            "Resolve option_2",
            {"action_id": "option_2", "selection_index": 0},
            source_card_id="ettin",
            is_option_choice=True,
        )
        assert result == "Ettin: Assassinate white troop (x2)"

    def test_dragon_cultist_option1_label(self):
        """Dragon Cultist option 1: gain 2 power."""
        result = enrich_label(
            "resolve_generic",
            "Resolve option_1",
            {"action_id": "option_1", "selection_index": 0},
            source_card_id="dragon_cultist",
            is_option_choice=True,
        )
        assert result == "Dragon Cultist: Gain 2 power"

    def test_dragon_cultist_option2_label(self):
        """Dragon Cultist option 2: gain 2 influence."""
        result = enrich_label(
            "resolve_generic",
            "Resolve option_2",
            {"action_id": "option_2", "selection_index": 0},
            source_card_id="dragon_cultist",
            is_option_choice=True,
        )
        assert result == "Dragon Cultist: Gain 2 influence"

    def test_dragon_cultist_labels_are_distinct(self):
        """Dragon Cultist options must have different labels."""
        label1 = enrich_label(
            "resolve_generic",
            "Resolve option_1",
            {"action_id": "option_1", "selection_index": 0},
            source_card_id="dragon_cultist",
            is_option_choice=True,
        )
        label2 = enrich_label(
            "resolve_generic",
            "Resolve option_2",
            {"action_id": "option_2", "selection_index": 0},
            source_card_id="dragon_cultist",
            is_option_choice=True,
        )
        assert label1 != label2, f"Labels should be distinct: {label1!r} == {label2!r}"


class TestFocusRequirementHelpers:
    def test_has_focus_requirement_true(self):
        action = {"op": "draw_cards", "metadata": {"requires_focus": True, "focus_aspect": "malice"}}
        assert _action_has_focus_requirement(action) is True

    def test_has_focus_requirement_false(self):
        action = {"op": "draw_cards", "metadata": {"count_from": "spies_on_board"}}
        assert _action_has_focus_requirement(action) is False

    def test_has_focus_requirement_no_metadata(self):
        action = {"op": "place_spy"}
        assert _action_has_focus_requirement(action) is False

    def test_has_focus_requirement_requires_focus_false(self):
        action = {"op": "draw_cards", "metadata": {"requires_focus": False}}
        assert _action_has_focus_requirement(action) is False

    def test_focus_aspect_returns_aspect(self):
        action = {"op": "draw_cards", "metadata": {"requires_focus": True, "focus_aspect": "malice"}}
        assert _action_focus_aspect(action) == "malice"

    def test_focus_aspect_missing_key(self):
        action = {"op": "draw_cards", "metadata": {"requires_focus": True}}
        assert _action_focus_aspect(action) == ""

    def test_focus_aspect_no_metadata(self):
        action = {"op": "place_spy"}
        assert _action_focus_aspect(action) == ""

    def test_describe_single_action_appends_focus(self):
        action = {
            "op": "draw_cards",
            "quantity": {"kind": "fixed", "value": 1},
            "metadata": {"requires_focus": True, "focus_aspect": "malice"},
        }
        result = _describe_single_action(action)
        assert result == "Draw cards (malice)"

    def test_describe_single_action_no_focus(self):
        action = {"op": "place_spy", "quantity": {"kind": "unspecified", "value": None}}
        result = _describe_single_action(action)
        assert result == "Place spy"

    def test_describe_single_action_focus_without_aspect_key(self):
        action = {
            "op": "draw_cards",
            "quantity": {"kind": "fixed", "value": 1},
            "metadata": {"requires_focus": True},
        }
        result = _describe_single_action(action)
        assert result == "Draw cards (focus)"


class TestFireElementalFocusLabels:
    """Fire Elemental: modal choice with gain_resource + draw_cards (focus: malice)."""

    def test_option1_focus_met_shows_draw_with_aspect(self):
        result = enrich_label(
            "resolve_generic",
            "Resolve option_1",
            {"action_id": "option_1", "selection_index": 0},
            source_card_id="fire_elemental",
            is_option_choice=True,
            player_available_aspects=frozenset({"malice"}),
        )
        assert result == "Fire Elemental: Gain 2 power and Draw cards (malice)"

    def test_option1_focus_not_met_hides_draw(self):
        result = enrich_label(
            "resolve_generic",
            "Resolve option_1",
            {"action_id": "option_1", "selection_index": 0},
            source_card_id="fire_elemental",
            is_option_choice=True,
            player_available_aspects=frozenset({"guile"}),
        )
        assert result == "Fire Elemental: Gain 2 power"

    def test_option1_no_aspects_available(self):
        result = enrich_label(
            "resolve_generic",
            "Resolve option_1",
            {"action_id": "option_1", "selection_index": 0},
            source_card_id="fire_elemental",
            is_option_choice=True,
            player_available_aspects=frozenset(),
        )
        assert result == "Fire Elemental: Gain 2 power"

    def test_option1_no_aspects_passed_uses_legacy_label(self):
        """Without player_available_aspects, focus actions are not filtered (backward compat)."""
        result = enrich_label(
            "resolve_generic",
            "Resolve option_1",
            {"action_id": "option_1", "selection_index": 0},
            source_card_id="fire_elemental",
            is_option_choice=True,
        )
        assert "Draw cards (malice)" in result

    def test_option2_focus_met_shows_draw_with_aspect(self):
        result = enrich_label(
            "resolve_generic",
            "Resolve option_2",
            {"action_id": "option_2", "selection_index": 0},
            source_card_id="fire_elemental",
            is_option_choice=True,
            player_available_aspects=frozenset({"malice"}),
        )
        assert result == "Fire Elemental: Gain 2 influence and Draw cards (malice)"

    def test_option2_focus_not_met_hides_draw(self):
        result = enrich_label(
            "resolve_generic",
            "Resolve option_2",
            {"action_id": "option_2", "selection_index": 0},
            source_card_id="fire_elemental",
            is_option_choice=True,
            player_available_aspects=frozenset({"obedience"}),
        )
        assert result == "Fire Elemental: Gain 2 influence"

    def test_option_labels_are_distinct(self):
        label1 = enrich_label(
            "resolve_generic",
            "Resolve option_1",
            {"action_id": "option_1", "selection_index": 0},
            source_card_id="fire_elemental",
            is_option_choice=True,
            player_available_aspects=frozenset({"malice"}),
        )
        label2 = enrich_label(
            "resolve_generic",
            "Resolve option_2",
            {"action_id": "option_2", "selection_index": 0},
            source_card_id="fire_elemental",
            is_option_choice=True,
            player_available_aspects=frozenset({"malice"}),
        )
        assert label1 != label2, f"Labels should be distinct: {label1!r} == {label2!r}"


class TestAirElementalFocusLabels:
    """Air Elemental: modal choice with place_spy/return_spy+deploy+draw_cards (focus: guile)."""

    def test_option1_focus_met_shows_draw_with_aspect(self):
        result = enrich_label(
            "resolve_generic",
            "Resolve option_1",
            {"action_id": "option_1", "selection_index": 0},
            source_card_id="air_elemental",
            is_option_choice=True,
            player_available_aspects=frozenset({"guile"}),
        )
        assert result == "Air Elemental: Place spy and Draw cards (guile)"

    def test_option1_focus_not_met_hides_draw(self):
        result = enrich_label(
            "resolve_generic",
            "Resolve option_1",
            {"action_id": "option_1", "selection_index": 0},
            source_card_id="air_elemental",
            is_option_choice=True,
            player_available_aspects=frozenset({"malice"}),
        )
        assert result == "Air Elemental: Place spy"

    def test_option2_focus_met_shows_multiple_actions_with_draw(self):
        """option_2: return_spy + deploy + deploy + deploy + draw_cards (focus: guile)."""
        result = enrich_label(
            "resolve_generic",
            "Resolve option_2",
            {"action_id": "option_2", "selection_index": 0},
            source_card_id="air_elemental",
            is_option_choice=True,
            player_available_aspects=frozenset({"guile"}),
        )
        assert "Return spy" in result
        assert "Deploy troops" in result
        assert "Draw cards (guile)" in result


class TestDescribeOptionFocusFiltering:
    """Direct unit tests for _describe_option focus filtering."""

    def test_all_actions_focus_unmet_returns_unknown(self):
        option = {
            "option_id": "option_x",
            "actions": [
                {
                    "op": "draw_cards",
                    "quantity": {"kind": "fixed", "value": 1},
                    "metadata": {"requires_focus": True, "focus_aspect": "obedience"},
                },
                {
                    "op": "draw_cards",
                    "quantity": {"kind": "fixed", "value": 1},
                    "metadata": {"requires_focus": True, "focus_aspect": "destruction"},
                },
            ],
        }
        result = _describe_option(option, available_aspects=frozenset({"guile"}))
        assert result == "unknown"

    def test_mixed_focus_and_non_focus_actions(self):
        option = {
            "option_id": "option_x",
            "actions": [
                {
                    "op": "gain_resource",
                    "quantity": {"kind": "fixed", "value": 3},
                    "metadata": {"resource": "power"},
                },
                {
                    "op": "draw_cards",
                    "quantity": {"kind": "fixed", "value": 2},
                    "metadata": {"requires_focus": True, "focus_aspect": "malice"},
                },
            ],
        }
        result = _describe_option(option, available_aspects=frozenset({"malice"}))
        assert result == "Gain 3 power and Draw cards (x2) (malice)"


class TestViewHelpers:
    """Unit tests for the aspect-computation helpers in view.py."""

    @staticmethod
    def _make_card_view(card_id, aspect, secondary_aspects=()):
        from engine_c.bindings.view import CardView
        return CardView(
            card_id=card_id, name="Test", cost=1, aspect=aspect,
            deck_vp=1, inner_circle_vp=1, rules_text="", notes="",
            secondary_aspects=secondary_aspects,
        )

    def test_compute_player_card_aspects_collects_primary(self):
        from engine_c.bindings.view import _compute_player_card_aspects
        cv = self._make_card_view("fire_elemental", "malice")
        result = _compute_player_card_aspects([cv], [], [])
        assert result == {"fire_elemental": frozenset({"malice"})}

    def test_compute_player_card_aspects_collects_secondary(self):
        from engine_c.bindings.view import _compute_player_card_aspects
        cv = self._make_card_view("fire_elemental", "malice", ("elemental",))
        result = _compute_player_card_aspects([cv], [], [])
        assert result == {"fire_elemental": frozenset({"malice", "elemental"})}

    def test_compute_player_card_aspects_across_zones(self):
        from engine_c.bindings.view import _compute_player_card_aspects
        hand_cv = self._make_card_view("fire_elemental", "malice")
        ic_cv = self._make_card_view("shade_enforcer", "malice")
        played_cv = self._make_card_view("noble", "obedience")
        result = _compute_player_card_aspects([hand_cv], [played_cv], [ic_cv])
        assert result == {
            "fire_elemental": frozenset({"malice"}),
            "noble": frozenset({"obedience"}),
            "shade_enforcer": frozenset({"malice"}),
        }

    def test_available_aspects_excludes_source(self):
        from engine_c.bindings.view import _available_aspects_for_source
        player_aspects = {
            "fire_elemental": frozenset({"malice"}),
            "shade_enforcer": frozenset({"malice"}),
        }
        result = _available_aspects_for_source(player_aspects, "fire_elemental")
        assert result == frozenset({"malice"})

    def test_available_aspects_source_only_card_removes_aspect(self):
        from engine_c.bindings.view import _available_aspects_for_source
        player_aspects = {"fire_elemental": frozenset({"malice"})}
        result = _available_aspects_for_source(player_aspects, "fire_elemental")
        assert result == frozenset()

    def test_available_aspects_empty_player_aspects(self):
        from engine_c.bindings.view import _available_aspects_for_source
        result = _available_aspects_for_source({}, "fire_elemental")
        assert result == frozenset()

    def test_available_aspects_unknown_source(self):
        from engine_c.bindings.view import _available_aspects_for_source
        player_aspects = {"shade_enforcer": frozenset({"malice"})}
        result = _available_aspects_for_source(player_aspects, "fire_elemental")
        assert result == frozenset({"malice"})

    def test_available_aspects_none_player_aspects(self):
        from engine_c.bindings.view import _available_aspects_for_source
        result = _available_aspects_for_source(None, "fire_elemental")
        assert result == frozenset()


class TestNoRegressionsWithFocusParam:
    """Non-focus cards still work when player_available_aspects is passed."""

    def test_dragon_cultist_with_aspects_param(self):
        """Dragon Cultist has no focus actions; passing aspects changes nothing."""
        result = enrich_label(
            "resolve_generic",
            "Resolve option_1",
            {"action_id": "option_1", "selection_index": 0},
            source_card_id="dragon_cultist",
            is_option_choice=True,
            player_available_aspects=frozenset({"guile", "obedience"}),
        )
        assert result == "Dragon Cultist: Gain 2 power"

    def test_ettin_with_aspects_param(self):
        """Ettin has no focus actions; passing aspects changes nothing."""
        result = enrich_label(
            "resolve_generic",
            "Resolve option_1",
            {"action_id": "option_1", "selection_index": 0},
            source_card_id="ettin",
            is_option_choice=True,
            player_available_aspects=frozenset({"malice"}),
        )
        assert result == "Ettin: Deploy troops (x3)"


class TestGhostOptionLabels:
    """Ghost: modal choice place_spy / return_spy + take_from_devour_pile_to_discard."""

    def test_option_1_label(self):
        result = enrich_label(
            "resolve_generic",
            "Resolve option_1",
            {"action_id": "option_1", "selection_index": 0},
            source_card_id="ghost",
            is_option_choice=True,
        )
        assert result == "Ghost: Place spy"

    def test_option_2_label(self):
        result = enrich_label(
            "resolve_generic",
            "Resolve option_2",
            {"action_id": "option_2", "selection_index": 0},
            source_card_id="ghost",
            is_option_choice=True,
        )
        assert result == (
            "Ghost: Return spy and take the top card from the devour pile "
            "into your discard pile"
        )
