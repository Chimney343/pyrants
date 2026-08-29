"""ctypes bindings for the engine_c DLL.

Provides a thin Python wrapper around the C engine, exposing an API
compatible with the original Python engine (engine/).

Usage:
    from engine_c.bindings.engine_bindings import CEngine
    eng = CEngine()
    state = eng.create_game(["player_1", "player_2"])
    moves = eng.legal_moves(state)
    next_state = eng.apply(state, moves[0])
"""

import ctypes
import os
from ctypes import (
    POINTER, Structure, c_bool, c_char_p, c_double, c_int, c_uint32,
    c_uint64, c_void_p, byref, cast, pointer,
)

_dll_path = os.environ.get("PYRANTS_ENGINE_DLL")

if not _dll_path:
    _dll_path = os.path.join(os.path.dirname(__file__), "..", "engine_c.dll")
    _dll_path = os.path.abspath(_dll_path)

    if not os.path.exists(_dll_path):
        _dll_path = os.path.join(os.path.dirname(__file__), "..", "engine_c", "engine_c.dll")

_lib = None
try:
    _lib = ctypes.CDLL(_dll_path)
except OSError:
    pass

# ── type aliases ──────────────────────────────────────────────────────────
Sym = c_uint32

# ── constants ─────────────────────────────────────────────────────────────
MAX_PLAYERS = 4
MAX_NODES = 128
MAX_ZONE_SIZE = 80
MAX_TROOP_SLOTS = 8
MAX_PENDING_PROMO = 16
MAX_SPY_SLOTS = 4
MAX_PENDING_ACTIONS = 32
MAX_OPTIONS = 8
MAX_FILTERS = 4
MAX_METADATA = 8
MAX_ABILITY_DISCARD = 8

PHASE_SETUP = 0
PHASE_DRAW = 1
PHASE_MAIN = 2
PHASE_END_OF_TURN = 3
PHASE_CLEANUP = 4
PHASE_GAME_OVER = 5

NODE_SITE = 0
NODE_ROUTE = 1

EXEC_SEQUENCE = 0
EXEC_MODAL = 1
EXEC_REPEAT = 2

MOVE_PLAY_CARD = 0
MOVE_END_MAIN_PHASE = 1
MOVE_RESOLVE_END_OF_TURN = 2
MOVE_RESOLVE_CLEANUP = 3
MOVE_ASSASSINATE = 4
MOVE_DEPLOY = 5
MOVE_RECRUIT = 6
MOVE_RETURN_SPY = 7
MOVE_ACTIVATE_ABILITY = 8
MOVE_DECLINE_ABILITY = 9
MOVE_PROMOTE_CARD = 10
MOVE_SKIP_PROMOTE = 11
MOVE_RESOLVE_GENERIC = 12
MOVE_INITIAL_PLACEMENT = 13


# ── C structs ─────────────────────────────────────────────────────────────
class MetaEntry(Structure):
    _fields_ = [("key", Sym), ("value", Sym)]

class CardAction(Structure):
    _fields_ = [
        ("action_id", Sym), ("op", Sym), ("target_scope", Sym),
        ("timing", Sym), ("optional", c_bool),
        ("quantity_kind", c_int), ("quantity_value", c_int),
        ("filters", Sym * MAX_FILTERS), ("filter_count", c_int),
        ("source_fragment", Sym),
        ("metadata", MetaEntry * MAX_METADATA), ("metadata_count", c_int),
    ]

class CardOption(Structure):
    _fields_ = [
        ("option_id", Sym),
        ("actions", POINTER(CardAction)), ("action_count", c_int),
    ]

class ExecutionModel(Structure):
    _fields_ = [
        ("kind", c_int),
        ("actions", POINTER(CardAction)), ("action_count", c_int),
        ("options", POINTER(CardOption)), ("option_count", c_int),
        ("selection", Sym),
        ("repeat_count", c_int), ("allow_repeat", c_bool),
    ]

class GlobalCondition(Structure):
    _fields_ = [("condition_type", Sym), ("description", Sym)]

class StateContract(Structure):
    _fields_ = [
        ("reads", POINTER(Sym)), ("read_count", c_int),
        ("writes", POINTER(Sym)), ("write_count", c_int),
    ]

class PaidAbility(Structure):
    _fields_ = [
        ("present", c_bool),
        ("ability_key", Sym),
        ("effect_key", Sym),
        ("effect_payload", POINTER(MetaEntry)), ("effect_payload_count", c_int),
        ("cost_power", c_int), ("cost_influence", c_int), ("cost_discard", c_int),
    ]

class CardDefinition(Structure):
    pass

CardDefinition._fields_ = [
    ("card_id", Sym), ("name", Sym), ("cost", c_int), ("aspect", Sym),
    ("secondary_aspects", POINTER(Sym)), ("secondary_aspect_count", c_int),
    ("deck_vp", c_int), ("inner_circle_vp", c_int),
    ("rules_text", Sym), ("notes", Sym),
    ("execution", ExecutionModel),
    ("actions", POINTER(CardAction)), ("action_count", c_int),
    ("global_conditions", POINTER(GlobalCondition)), ("global_condition_count", c_int),
    ("state_contract", StateContract),
    ("effect_key", Sym),
    ("effect_payload", POINTER(MetaEntry)), ("effect_payload_count", c_int),
    ("paid_ability", PaidAbility),
]

class CardCatalog(Structure):
    _fields_ = [
        ("catalog_id", Sym), ("version", Sym),
        ("cards", POINTER(CardDefinition)), ("card_count", c_int),
    ]

class NodeDefinition(Structure):
    _fields_ = [
        ("node_id", Sym), ("kind", Sym),
        ("adjacent_to", POINTER(Sym)), ("adjacent_count", c_int),
        ("troop_capacity", c_int), ("control_vp", c_int),
        ("total_control_vp_per_turn", c_int), ("influence_income", c_int),
        ("initial_troop_slots", POINTER(Sym)), ("initial_troop_slot_count", c_int),
        ("initial_vp_tokens", c_int),
    ]

class BoardDefinition(Structure):
    _fields_ = [
        ("board_id", Sym),
        ("nodes", POINTER(NodeDefinition)), ("node_count", c_int),
    ]

class DeckEntry(Structure):
    _fields_ = [("card_id", Sym), ("count", c_int)]

class DeckDefinition(Structure):
    _fields_ = [
        ("deck_id", Sym), ("name", Sym), ("kind", Sym),
        ("total_cards", c_int), ("per_player", c_bool),
        ("entries", POINTER(DeckEntry)), ("entry_count", c_int),
    ]

class SetupDefinition(Structure):
    _fields_ = [
        ("setup_id", Sym),
        ("starter_deck", DeckDefinition), ("market_deck", DeckDefinition),
        ("market_row_size", c_int),
    ]

class GameDefinition(Structure):
    _fields_ = [
        ("definition_id", Sym),
        ("board", BoardDefinition), ("catalog", CardCatalog),
        ("setup", SetupDefinition),
        ("default_player_troops", c_int), ("default_player_spies", c_int),
    ]

class NodeState(Structure):
    _fields_ = [
        ("node_id", Sym),
        ("troop_slots", Sym * MAX_TROOP_SLOTS), ("troop_slot_count", c_int),
        ("spies", Sym * MAX_SPY_SLOTS), ("spy_count", c_int),
        ("vp_tokens", c_int), ("cow_dirty", c_bool),
    ]

class PlayerState(Structure):
    _fields_ = [
        ("player_id", Sym),
        ("deck", Sym * MAX_ZONE_SIZE), ("deck_count", c_int),
        ("hand", Sym * MAX_ZONE_SIZE), ("hand_count", c_int),
        ("discard_pile", Sym * MAX_ZONE_SIZE), ("discard_pile_count", c_int),
        ("played_cards", Sym * MAX_ZONE_SIZE), ("played_cards_count", c_int),
        ("inner_circle", Sym * MAX_ZONE_SIZE), ("inner_circle_count", c_int),
        ("trophy_hall", Sym * MAX_ZONE_SIZE), ("trophy_hall_count", c_int),
        ("barracks", c_int), ("spies_available", c_int),
        ("vp_tokens", c_int), ("score", c_int),
        ("cow_dirty", c_bool),
    ]

class ResourcePool(Structure):
    _fields_ = [("power", c_int), ("influence", c_int), ("cow_dirty", c_bool)]

class MarketState(Structure):
    _fields_ = [
        ("deck", Sym * MAX_ZONE_SIZE), ("deck_count", c_int),
        ("row", Sym * MAX_ZONE_SIZE), ("row_count", c_int),
        ("discard_pile", Sym * MAX_ZONE_SIZE), ("discard_pile_count", c_int),
        ("cow_dirty", c_bool),
    ]

class PendingAbilityState(Structure):
    _fields_ = [("card_id", Sym), ("ability_key", Sym), ("resolved", c_bool)]

class PendingPromotionState(Structure):
    _fields_ = [
        ("card_id", Sym), ("timing", Sym), ("optional", c_bool),
        ("deferred_choice", c_bool), ("source_card_id", Sym),
        ("requires_another_played_card", c_bool),
        ("required_aspect", Sym), ("required_secondary_aspect", Sym),
        ("focus_aspect", Sym),
        ("repeat_while_targets", c_bool),
        ("promotions_remaining", c_int),
    ]

class PendingGenericChoiceState(Structure):
    _fields_ = [
        ("source_card_id", Sym), ("exec_kind", c_int),
        ("option_ids", POINTER(Sym)), ("option_count", c_int),
        ("selected_option_ids", POINTER(Sym)), ("selected_count", c_int),
        ("current_option_id", Sym),
        ("current_actions", POINTER(CardAction)), ("current_action_count", c_int),
        ("next_action_index", c_int), ("awaiting_option", c_bool),
        ("remaining_repeats", c_int), ("allow_repeat", c_bool),
        ("last_selection_keys", Sym * 8), ("last_selection_values", Sym * 8),
        ("last_selection_count", c_int),
        ("counter_keys", Sym * 8), ("counter_values", c_int * 8),
        ("counter_count", c_int),
        ("limit_keys", Sym * 8), ("limit_values", c_int * 8),
        ("limit_count", c_int),
        ("resolve_depth", c_int),
    ]

class GameStateStruct(Structure):
    _fields_ = [
        ("definition", POINTER(GameDefinition)),
        ("nodes", NodeState * MAX_NODES), ("node_count", c_int),
        ("players", PlayerState * MAX_PLAYERS), ("player_count", c_int),
        ("player_ids", Sym * MAX_PLAYERS), ("player_id_count", c_int),
        ("current_player_id", Sym),
        ("phase", c_int), ("round_number", c_int),
        ("resource_pool", ResourcePool), ("market", MarketState),
        ("final_score_keys", c_int * MAX_PLAYERS), ("final_score_values", c_int * MAX_PLAYERS),
        ("final_score_count", c_int),
        ("pending_ability", POINTER(PendingAbilityState)),
        ("pending_immediate", PendingPromotionState * MAX_PENDING_PROMO),
        ("pending_immediate_count", c_int),
        ("pending_eot", PendingPromotionState * MAX_PENDING_PROMO),
        ("pending_eot_count", c_int),
        ("pending_generic", POINTER(PendingGenericChoiceState)),
        ("devour_pile", Sym * MAX_ZONE_SIZE), ("devour_pile_count", c_int),
        ("setup_complete", Sym * MAX_PLAYERS), ("setup_complete_count", c_int),
        ("shuffle_seed", c_uint64), ("shuffle_counter", c_int),
        ("arena", c_void_p),
    ]

class MoveData(ctypes.Union):
    _fields_ = [
        ("play_card", type("_pc", (Structure,), {"_fields_": [("card_id", Sym), ("hand_index", c_int)]})),
        ("assassinate", type("_as", (Structure,), {"_fields_": [("target_node_id", Sym), ("troop_owner_id", Sym), ("slot_index", c_int)]})),
        ("deploy", type("_dp", (Structure,), {"_fields_": [("node_id", Sym), ("slot_index", c_int)]})),
        ("recruit", type("_rc", (Structure,), {"_fields_": [("card_id", Sym)]})),
        ("return_spy", type("_rs", (Structure,), {"_fields_": [("node_id", Sym), ("spy_owner_id", Sym)]})),
        ("activate_ability", type("_aa", (Structure,), {"_fields_": [("card_id", Sym), ("ability_key", Sym), ("discard_hand_indices", c_int * MAX_ABILITY_DISCARD), ("discard_hand_count", c_int)]})),
        ("decline_ability", type("_da", (Structure,), {"_fields_": [("card_id", Sym), ("ability_key", Sym)]})),
        ("promote_card", type("_pc2", (Structure,), {"_fields_": [("card_id", Sym)]})),
        ("skip_promote", type("_sp", (Structure,), {"_fields_": [("source_card_id", Sym)]})),
        ("resolve_generic", type("_rg", (Structure,), {"_fields_": [("action_id", Sym), ("target_id", Sym), ("selection_index", c_int)]})),
        ("initial_placement", type("_ip", (Structure,), {"_fields_": [("node_id", Sym)]})),
    ]

class Move(Structure):
    _fields_ = [
        ("type", c_int), ("data", MoveData), ("player_index", c_int),
    ]

class PublicView(Structure):
    _fields_ = [
        ("player_count", c_int),
        ("player_ids", Sym * MAX_PLAYERS),
        ("node_count", c_int),
        ("nodes", type("_pnv", (Structure,), {"_fields_": [
            ("node_id", Sym),
            ("troop_counts", c_int * MAX_PLAYERS),
            ("troop_owner_count", c_int),
            ("troop_owners", Sym * MAX_PLAYERS),
            ("white_troops", c_int),
            ("spy_owner_count", c_int),
            ("spy_owners", Sym * MAX_SPY_SLOTS),
            ("vp_tokens", c_int),
            ("controlled", c_bool),
            ("controller_id", Sym),
        ]}) * MAX_NODES),
        ("round_number", c_int), ("phase", c_int),
        ("current_player_id", Sym),
        ("resource_pool", ResourcePool), ("market", MarketState),
        ("pending_ability", type("_pav", (Structure,), {"_fields_": [
            ("ability_key", Sym), ("source_card_id", Sym), ("resolved", c_bool),
        ]})),
        ("has_pending_ability", c_bool),
        ("pending_immediate", type("_ppv", (Structure,), {"_fields_": [
            ("card_id", Sym), ("is_optional", c_bool), ("player_index", c_int),
        ]}) * MAX_PENDING_PROMO),
        ("pending_immediate_count", c_int),
        ("pending_generic", type("_pgv", (Structure,), {"_fields_": [
            ("source_card_id", Sym), ("player_index", c_int), ("is_pending", c_bool),
        ]})),
        ("has_pending_generic", c_bool),
    ]

class PrivateView(Structure):
    _fields_ = [
        ("public_view", PublicView), ("player", PlayerState), ("player_index", c_int),
    ]


# ── CGameView structs ──────────────────────────────────────────────────────
class CPlayerZoneView(Structure):
    _fields_ = [
        ("hand", Sym * MAX_ZONE_SIZE), ("hand_count", c_int),
        ("discard", Sym * MAX_ZONE_SIZE), ("discard_count", c_int),
        ("played", Sym * MAX_ZONE_SIZE), ("played_count", c_int),
        ("inner_circle", Sym * MAX_ZONE_SIZE), ("inner_circle_count", c_int),
        ("trophy_hall", Sym * MAX_ZONE_SIZE), ("trophy_hall_count", c_int),
        ("barracks", c_int), ("spies_available", c_int),
        ("vp_tokens", c_int), ("score", c_int), ("deck_count", c_int),
    ]

class CNodeOccupancyView(Structure):
    _fields_ = [
        ("node_id", Sym), ("kind", c_int),
        ("adjacent_to", Sym * MAX_NODES), ("adjacent_count", c_int),
        ("control_vp", c_int), ("total_control_vp_per_turn", c_int),
        ("troop_slots", Sym * MAX_TROOP_SLOTS), ("troop_slot_count", c_int),
        ("spies", Sym * MAX_SPY_SLOTS), ("spy_count", c_int),
        ("vp_tokens", c_int),
    ]

class CGameView(Structure):
    _fields_ = [
        ("round_number", c_int), ("phase", c_int),
        ("current_player_id", Sym),
        ("players", CPlayerZoneView * MAX_PLAYERS), ("player_count", c_int),
        ("player_ids", Sym * MAX_PLAYERS),
        ("market_row", Sym * MAX_ZONE_SIZE), ("market_row_count", c_int),
        ("market_deck_count", c_int), ("market_discard_count", c_int),
        ("resource_power", c_int), ("resource_influence", c_int),
        ("devour_pile", Sym * MAX_ZONE_SIZE), ("devour_pile_count", c_int),
        ("nodes", CNodeOccupancyView * MAX_NODES), ("node_count", c_int),
        ("controlled_sites", c_int), ("total_control_sites", c_int),
        ("current_player_control_vp", c_int), ("current_player_total_control_vp", c_int),
        ("house_guard_remaining", c_int), ("priestess_remaining", c_int),
        ("insane_outcast_remaining", c_int),
    ]


# ── function signatures ───────────────────────────────────────────────────
def _setup():
    _lib.intern_init.argtypes = [c_int]
    _lib.intern_init.restype = None
    _lib.intern_destroy.argtypes = []
    _lib.intern_destroy.restype = None
    _lib.intern.argtypes = [c_char_p]
    _lib.intern.restype = Sym
    _lib.intern_str.argtypes = [Sym]
    _lib.intern_str.restype = c_char_p

    _lib.engine_load_definition_json.argtypes = [c_char_p, c_char_p, c_char_p, c_void_p]
    _lib.engine_load_definition_json.restype = POINTER(GameDefinition)
    _lib.engine_apply_setup_json.argtypes = [POINTER(GameDefinition), c_char_p, c_void_p]
    _lib.engine_apply_setup_json.restype = c_int
    _lib.engine_create_game_definition.argtypes = [
        POINTER(GameDefinition), POINTER(c_char_p), c_int, c_uint64]
    _lib.engine_create_game_definition.restype = POINTER(GameStateStruct)
    _lib.engine_clone.argtypes = [POINTER(GameStateStruct)]
    _lib.engine_clone.restype = POINTER(GameStateStruct)
    _lib.engine_destroy.argtypes = [POINTER(GameStateStruct)]
    _lib.engine_destroy.restype = None

    _lib.engine_legal_moves.argtypes = [POINTER(GameStateStruct), POINTER(Move), c_int]
    _lib.engine_legal_moves.restype = c_int
    _lib.engine_apply.argtypes = [POINTER(GameStateStruct), POINTER(Move)]
    _lib.engine_apply.restype = POINTER(GameStateStruct)
    _lib.engine_is_terminal.argtypes = [POINTER(GameStateStruct)]
    _lib.engine_is_terminal.restype = c_int
    _lib.engine_winner.argtypes = [POINTER(GameStateStruct), POINTER(c_int)]
    _lib.engine_winner.restype = Sym

    _lib.engine_public_view.argtypes = [POINTER(GameStateStruct), POINTER(PublicView)]
    _lib.engine_public_view.restype = None
    _lib.engine_private_view.argtypes = [POINTER(GameStateStruct), Sym, POINTER(PrivateView)]
    _lib.engine_private_view.restype = None

    _lib.register_default_effects.argtypes = []
    _lib.register_default_effects.restype = None

    _lib.arena_create.argtypes = [ctypes.c_size_t]
    _lib.arena_create.restype = c_void_p
    _lib.arena_destroy.argtypes = [c_void_p]
    _lib.arena_destroy.restype = None

    _lib.compute_final_scores.argtypes = [POINTER(GameStateStruct), POINTER(c_int)]
    _lib.compute_final_scores.restype = None

    _lib.set_game_over.argtypes = [POINTER(GameStateStruct)]
    _lib.set_game_over.restype = None
    _lib.advance_phase.argtypes = [POINTER(GameStateStruct)]
    _lib.advance_phase.restype = c_int

    _lib.engine_determinize.argtypes = [POINTER(GameStateStruct), Sym, c_uint64]
    _lib.engine_determinize.restype = POINTER(GameStateStruct)

    _lib.engine_build_view.argtypes = [POINTER(GameStateStruct), POINTER(CGameView)]
    _lib.engine_build_view.restype = None

    _lib.engine_describe_move.argtypes = [
        POINTER(GameStateStruct), POINTER(Move),
        POINTER(c_char_p), POINTER(c_char_p), c_int,
        c_char_p, c_int,
    ]
    _lib.engine_describe_move.restype = c_int

    _lib.engine_serialize_state.argtypes = [
        POINTER(GameStateStruct), c_char_p, c_char_p, c_char_p,
        c_int, c_int, c_char_p, c_int,
    ]
    _lib.engine_serialize_state.restype = c_int

    _lib.engine_deserialize_state.argtypes = [
        c_char_p, c_char_p, c_void_p, POINTER(c_int),
    ]
    _lib.engine_deserialize_state.restype = POINTER(GameStateStruct)


if _lib is not None:
    _setup()
