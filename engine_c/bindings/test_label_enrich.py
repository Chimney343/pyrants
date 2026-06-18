"""Tests for engine_c/bindings/label_enrich.py and view.py label plumbing."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bindings"))

import pytest
from label_enrich import enrich_label


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
            "Remove white troop at Gauntlgrym",
            {"target_node_id": "site_gauntlgrym", "target_slot_index": 0},
        )
        assert result == "Remove white troop at Gauntlgrym"

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
        assert "choice" in result

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
        assert "choice" in result

    def test_resolve_generic_source_card_id_beats_action_id(self):
        result = enrich_label(
            "resolve_generic",
            "Resolve assassinate_troop",
            {"action_id": "assassinate_troop", "selection_index": 0},
            source_card_id="advance_scout",
        )
        assert "Advance Scout" in result
        assert "choice" in result

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
        result = enrich_label(
            "resolve_generic",
            "Resolve option_1_action_1",
            {"action_id": "option_1_action_1", "target_id": "site_gauntlgrym", "selection_index": 0},
            source_card_id="aboleth", card_action_id="option_1_action_1",
        )
        assert result == "Aboleth: Place spy at Site gauntlgrym"
    def test_resolve_generic_true_fallback(self):
        result = enrich_label(
            "resolve_generic",
            "Resolve",
            {"action_id": "", "selection_index": 0},
        )
        assert result == "Resolve pending choice"

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
        "Sequence model action that does not need a target selection."
        result = enrich_label(
            "resolve_generic",
            "Resolve action_1",
            {"action_id": "", "selection_index": 0},
            source_card_id="ambassador",
            card_action_id="action_1",
        )
        assert result == "Ambassador: Promote card"

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
