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

    def test_resolve_generic_with_unknown_target_falls_back(self):
        result = enrich_label(
            "resolve_generic",
            "Resolve assassinate_troop",
            {"action_id": "assassinate_troop", "target_id": "some_random_id", "selection_index": 0},
        )
        assert result == "Resolve pending choice"

    def test_resolve_generic_no_target_falls_back(self):
        result = enrich_label(
            "resolve_generic",
            "Resolve assassinate_troop",
            {"action_id": "assassinate_troop", "selection_index": 0},
        )
        assert result == "Resolve pending choice"

    def test_empty_data_dict(self):
        result = enrich_label("play_card", "Play Noble", {})
        assert result == "Play Noble"


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
