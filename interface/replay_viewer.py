"""Tk replay viewer for stepping through simulation logs."""

from __future__ import annotations

import argparse
import json
import logging
import tkinter as tk
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from pydantic_core import ValidationError as PydanticValidationError

from engine.errors import IllegalMoveError
from engine.moves import (
    HOUSE_GUARD_RECRUIT_SLOT,
    INSANE_OUTCAST_RECRUIT_SLOT,
    PRIESTESS_RECRUIT_SLOT,
)
from engine.scoring import _cards_vp, _is_total_control, _site_control_owner
from engine.state import GameState, NodeKind, board_index, build_initial_game_state
from engine.state import card_index as state_card_index
from game_session import GameSession
from game_setup.loaders import build_board_package_from_files, build_game_definition_from_dicts
from game_setup.market_setup import ABERRATIONS_DECK_ID, combine_two_deck_market_setup
from game_setup.market_setup import discover_full_deck_profiles as _discover_full_deck_profiles
from game_simulation import MOVE_ADAPTER
from game_view import CardView, GameView, build_game_view
from interface._canvas_scroll import bind_canvas_scrolling
from interface.game_renderer import GameBoardRenderer
from interface.view_fit import compute_fit_zoom

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_LAYOUT_PATH = ROOT_DIR / "data" / "layouts" / "tyrants_of_the_underdark_layout.json"
DEFAULT_BOARD_PATH = ROOT_DIR / "data" / "boards" / "tyrants_of_the_underdark.json"
DEFAULT_CARD_PATH = ROOT_DIR / "data" / "cards" / "catalog.json"
DEFAULT_SETUP_PATH = ROOT_DIR / "data" / "decks" / "base_setup.json"
DECKS_DIR = ROOT_DIR / "data" / "decks"

MARKET_CARD_WIDTH = 96
MARKET_CARD_HEIGHT = 112
PLAYER_CARD_WIDTH = 220
PLAYER_CARD_HEIGHT = 156
PLAYER_CARD_WIDTH_COMPACT = 184
PLAYER_CARD_HEIGHT_COMPACT = 124
CARD_GAP = 10
CARD_ROW_TOP_PAD = 8
CARD_ROW_SIDE_PAD = 8
CARD_NAME_MAX_CHARS = 28
CARD_META_MAX_CHARS = 48
MAP_VIEWPORT_MAX_HEIGHT = 430
MAP_VIEWPORT_MAX_WIDTH = 980
TOP_DECK_SLOT_COUNT = 9

HOUSE_GUARD_CARD_ID = "house_guard"
PRIESTESS_CARD_ID = "priestess_of_lolth"
INSANE_OUTCAST_CARD_ID = "insane_outcast"

SPECIAL_CARD_TINTS: dict[str, str] = {
    HOUSE_GUARD_CARD_ID: "#d5d0c6",
    PRIESTESS_CARD_ID: "#cfcbe0",
    INSANE_OUTCAST_CARD_ID: "#ddcdcd",
}

SPECIAL_TOP_SLOT_TO_MARKET_SLOT: dict[int, int] = {
    0: HOUSE_GUARD_RECRUIT_SLOT,
    1: PRIESTESS_RECRUIT_SLOT,
    2: INSANE_OUTCAST_RECRUIT_SLOT,
}

# ISMCTS stores the chance-outcome action id as the seed in the replay context,
# but the engine uses a Knuth-multiplicative-hash internal seed.  Replays from
# the OpenSpiel wrapper must be transformed; plain simulation replays must not.
_ISMCTS_SEED_MIXER_MULTIPLIER = 2654435761
_ISMCTS_SEED_MIXER_MASK = 0x7FFFFFFF


def _ismcts_public_to_seed(action_id: int) -> int:
    """Map an ISMCTS public chance-outcome id to the internal shuffle seed."""
    return (action_id * _ISMCTS_SEED_MIXER_MULTIPLIER) & _ISMCTS_SEED_MIXER_MASK


def _ellipsize(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return text[: max_chars - 3] + "..."


def _compute_aspect_focus(cards: tuple[CardView, ...]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for card in cards:
        if card.aspect and card.aspect not in ("empty", "inactive", "unknown"):
            counter[card.aspect] += 1
    return counter


def _format_aspect_breakdown(counter: Counter[str]) -> str:
    if not counter:
        return "none"
    return ", ".join(
        f"{aspect} x{count}" if count > 1 else aspect
        for aspect, count in counter.most_common()
    )


def _format_card_hover_details(card: CardView) -> str:
    rules_text = card.rules_text.strip() or "(none)"
    notes_text = card.notes.strip() or "(none)"
    return (
        f"Name: {card.name}\n"
        f"Cost: {card.cost}    Aspect: {card.aspect}\n"
        f"Deck VP: {card.deck_vp}    Inner Circle VP: {card.inner_circle_vp}\n"
        f"Rules: {rules_text}\n"
        f"Notes: {notes_text}"
    )


def _format_ordered_card_options(card_ids: Sequence[str], cards_by_id: dict[str, object]) -> list[str]:
    if not card_ids:
        return ["(empty)"]
    return [
        f"{index + 1}. {(cards_by_id.get(card_id).name if cards_by_id.get(card_id) is not None else 'Unknown Card')}"
        for index, card_id in enumerate(card_ids)
    ]


def _format_trophy_hall_options(trophy_hall: Sequence[str]) -> list[str]:
    if not trophy_hall:
        return ["(empty)"]

    def _owner_label(owner_id: str) -> str:
        if owner_id == "white":
            return "White troop"
        return f"Player {owner_id} troop"

    return [
        f"{index + 1}. {_owner_label(owner_id)} ({owner_id})"
        for index, owner_id in enumerate(trophy_hall)
    ]


class ReplayViewerApp:
    """Replay-step browser for simulation logs."""

    def __init__(
        self,
        root: tk.Tk,
        *,
        board_path: Path,
        layout_path: Path,
        replay_payload: dict[str, object],
        card_path: Path | None = None,
        setup_path: Path | None = None,
        player_ids: list[str] | None = None,
        seed: int | None = None,
    ) -> None:
        self.root = root
        self.root.title("Tyrants Replay Viewer")

        self.renderer = GameBoardRenderer()
        self.zoom_level = 1.0
        self._min_zoom = 0.1
        self._max_zoom = 3.0
        self._compact_player_rows = False
        self._market_card_width = MARKET_CARD_WIDTH
        self._market_card_height = MARKET_CARD_HEIGHT
        self._player_card_width = PLAYER_CARD_WIDTH
        self._player_card_height = PLAYER_CARD_HEIGHT
        self._resize_after_id: str | None = None
        self._pending_initial_fit = True
        self.max_step = 0
        self.package = None
        self._is_ismcts = False

        self.status_var = tk.StringVar(value="")
        self.prompt_var = tk.StringVar(value="")
        self.players_var = tk.StringVar(value="")
        self.move_var = tk.StringVar(value="")
        self.market_meta_var = tk.StringVar(value="")
        self.resource_var = tk.StringVar(value="")
        self.vp_breakdown_var = tk.StringVar(value="")
        self.house_guard_var = tk.StringVar(value="")
        self.priestess_var = tk.StringVar(value="")
        self.discard_selection_var = tk.StringVar(value="")
        self.inner_circle_selection_var = tk.StringVar(value="")
        self.trophy_hall_selection_var = tk.StringVar(value="")
        self.inner_circle_meta_var = tk.StringVar(value="")
        self.trophy_hall_meta_var = tk.StringVar(value="")

        self._hover_popup: tk.Toplevel | None = None
        self._hover_market_cards: list[CardView] = []
        self._hover_hand_cards: list[CardView] = []
        self._hover_played_cards: list[CardView] = []
        self._hover_market_hitboxes: list[tuple[int, int, int, int, int]] = []
        self._hand_hitboxes: list[tuple[int, int, int, int, int]] = []
        self._played_hitboxes: list[tuple[int, int, int, int, int]] = []
        self._market_hitboxes: list[tuple[int, int, int, int, int]] = []

        self._build_ui()
        self.root.bind("<Configure>", self._on_root_configure)

        self._set_replay_payload(
            replay_payload,
            board_path=board_path,
            layout_path=layout_path,
            card_path=card_path,
            setup_path=setup_path,
            player_ids=player_ids,
            seed=seed,
        )
        self._render_step(0)

    def _resolve_replay_context(
        self,
        payload: dict[str, object],
        *,
        board_path: Path,
        layout_path: Path,
        card_path: Path | None,
        setup_path: Path | None,
        player_ids: list[str] | None,
        seed: int | None,
    ) -> None:
        context_payload = payload.get("replay_context")
        if isinstance(context_payload, dict):
            ctx_board = context_payload.get("board_path")
            ctx_card = context_payload.get("card_path")
            ctx_setup = context_payload.get("setup_path")
            ctx_players = context_payload.get("player_ids")
            ctx_seed = context_payload.get("seed")
            ctx_layout = context_payload.get("layout_path")

            if isinstance(ctx_board, str):
                self._board_path = Path(ctx_board)
            else:
                self._board_path = board_path

            if isinstance(ctx_card, str):
                self._card_path = Path(ctx_card)
            elif card_path is not None:
                self._card_path = card_path
            else:
                self._card_path = DEFAULT_CARD_PATH

            if isinstance(ctx_setup, str):
                self._setup_path = Path(ctx_setup)
            elif setup_path is not None:
                self._setup_path = setup_path
            else:
                self._setup_path = DEFAULT_SETUP_PATH

            if isinstance(ctx_layout, str):
                self._layout_path = Path(ctx_layout)
            else:
                self._layout_path = layout_path

            if isinstance(ctx_players, list):
                self._player_ids = tuple(str(pid) for pid in ctx_players)
            elif player_ids is not None:
                self._player_ids = tuple(player_ids)
            else:
                raise ValueError("Replay missing player_ids")

            self._seed = int(ctx_seed) if isinstance(ctx_seed, int) else seed

            # ISMCTS replays include deck_a_id / deck_b_id keys; their
            # presence (even as empty strings) signals that the seed is a
            # public chance-outcome id that must be hashed before use.
            raw_deck_a = context_payload.get("deck_a_id")
            raw_deck_b = context_payload.get("deck_b_id")
            self._is_ismcts = "deck_a_id" in context_payload or "deck_b_id" in context_payload
            # Treat empty-string deck IDs as absent (ISMCTS fallback to base setup).
            self._deck_a_id = raw_deck_a if isinstance(raw_deck_a, str) and raw_deck_a else None
            self._deck_b_id = raw_deck_b if isinstance(raw_deck_b, str) and raw_deck_b else None
        else:
            if card_path is None or setup_path is None or player_ids is None:
                raise ValueError(
                    "Replay payload missing replay_context; provide card_path, setup_path, and player_ids"
                )
            self._board_path = board_path
            self._layout_path = layout_path
            self._card_path = card_path
            self._setup_path = setup_path
            self._player_ids = tuple(player_ids)
            self._seed = seed
            self._deck_a_id = None
            self._deck_b_id = None
            self._is_ismcts = False

    def _set_replay_payload(
        self,
        payload: dict[str, object],
        *,
        board_path: Path,
        layout_path: Path,
        card_path: Path | None,
        setup_path: Path | None,
        player_ids: list[str] | None,
        seed: int | None,
    ) -> None:
        self._resolve_replay_context(
            payload,
            board_path=board_path,
            layout_path=layout_path,
            card_path=card_path,
            setup_path=setup_path,
            player_ids=player_ids,
            seed=seed,
        )

        self.package = build_board_package_from_files(
            board_path=self._board_path,
            layout_path=self._layout_path,
        )
        self._node_names = {n.node_id: n.label for n in self.package.layout.nodes}

        replay_entries = payload.get("replay_log")
        if not isinstance(replay_entries, list):
            raise ValueError("Replay payload must include replay_log as a list")
        self.replay_steps = replay_entries
        self.max_step = len(self.replay_steps)

        self._all_move_payloads: list[dict[str, object]] = []
        self._all_move_labels: list[str] = []
        self._all_move_types: list[str] = []
        for entry in self.replay_steps:
            if not isinstance(entry, dict):
                raise ValueError("Replay log entry must be an object")
            step_payload = entry.get("payload")
            if not isinstance(step_payload, dict):
                raise ValueError("Replay step payload must be an object")
            # Normalise C-engine payload structure into Python-engine flat format.
            # Models have extra="forbid", so foreign keys must be removed.

            # 1. Rename 'type' → 'move_type' (and drop the old key).
            if "move_type" not in step_payload and "type" in step_payload:
                move_type_val = step_payload["type"]
                step_payload = {k: v for k, v in step_payload.items() if k != "type"}
                step_payload["move_type"] = move_type_val

            # 2. Flatten C-engine 'data' dict into the top-level payload.
            data = step_payload.pop("data", None)
            if isinstance(data, dict):
                for k, v in data.items():
                    step_payload[k] = v

            # 3. Inject player_id from the entry level (C engine stores it there).
            if "player_id" not in step_payload:
                entry_player_id = entry.get("player_id")
                if entry_player_id is not None:
                    step_payload["player_id"] = entry_player_id

            # 4. Map C-engine move type names to Python names.
            if step_payload.get("move_type") == "resolve_generic":
                step_payload["move_type"] = "resolve_generic_choice"

            self._all_move_payloads.append(step_payload)
            self._all_move_labels.append(str(entry.get("label", "")))
            # Support C-engine entries that use 'type' at the entry level.
            entry_move_type = entry.get("move_type") or entry.get("type", "")
            self._all_move_types.append(str(entry_move_type))

        self._aberrations_in_market = self._detect_aberrations(payload)

        self.current_index = 0
        self._cached_index = -1
        self._cached_session = None

        self._hover_market_cards = []
        self._hover_hand_cards = []
        self._hover_played_cards = []
        self._hover_market_hitboxes = []
        self._hand_hitboxes = []
        self._played_hitboxes = []
        self._market_hitboxes = []

        self.slider.configure(to=self.max_step)
        self.canvas.configure(
            width=min(self.package.layout.canvas.width, MAP_VIEWPORT_MAX_WIDTH),
            height=min(self.package.layout.canvas.height, MAP_VIEWPORT_MAX_HEIGHT),
        )
        self._apply_responsive_layout()
        self._auto_fit_zoom()
        self._render_step(0)

    def _load_replay_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Load Replay File",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=ROOT_DIR / "artifacts",
        )
        if not path:
            return

        try:
            payload = _load_payload(Path(path))
        except Exception as exc:
            messagebox.showerror("Load Failed", f"Could not load replay file:\n{exc}")
            return

        try:
            self._hide_card_popup()
            self._set_replay_payload(
                payload,
                board_path=self._board_path,
                layout_path=self._layout_path,
                card_path=self._card_path,
                setup_path=self._setup_path,
                player_ids=list(self._player_ids),
                seed=self._seed,
            )
        except Exception as exc:
            messagebox.showerror("Load Failed", str(exc))

    def _detect_aberrations(self, payload: dict[str, object]) -> bool:
        context_payload = payload.get("replay_context")
        if isinstance(context_payload, dict):
            deck_a = context_payload.get("deck_a_id")
            deck_b = context_payload.get("deck_b_id")
            if isinstance(deck_a, str) and deck_a == ABERRATIONS_DECK_ID:
                return True
            if isinstance(deck_b, str) and deck_b == ABERRATIONS_DECK_ID:
                return True

        for entry in self.replay_steps:
            if not isinstance(entry, dict):
                continue
            payload_entry = entry.get("payload")
            if not isinstance(payload_entry, dict):
                continue
            market_slot = payload_entry.get("market_slot")
            if market_slot == INSANE_OUTCAST_RECRUIT_SLOT:
                return True
        return False

    def _effective_seed(self) -> int:
        """Return the seed value that the engine should use.

        ISMCTS replays store the *public* chance-outcome id as the seed,
        but the engine internally applies a Knuth-multiplicative hash.
        Plain simulation replays use the seed directly, so no transform.
        """
        raw = self._seed if self._seed is not None else 0
        if self._is_ismcts:
            return _ismcts_public_to_seed(raw)
        return raw

    def _fresh_session(self) -> GameSession:
        if self._deck_a_id is not None and self._deck_b_id is not None:
            return self._build_combined_session()
        return GameSession.from_files(
            board_path=self._board_path,
            card_path=self._card_path,
            setup_path=self._setup_path,
            player_ids=self._player_ids,
            seed=self._effective_seed(),
        )

    def _build_combined_session(self) -> GameSession:
        profiles = tuple(
            p for p in _discover_full_deck_profiles(DECKS_DIR)
            if p.deck_id in (self._deck_a_id, self._deck_b_id)
        )
        if len(profiles) != 2:
            msg = (
                f"Could not find both deck profiles: "
                f"deck_a_id={self._deck_a_id!r}, deck_b_id={self._deck_b_id!r}"
            )
            raise ValueError(msg)

        deck_a = next(p for p in profiles if p.deck_id == self._deck_a_id)
        deck_b = next(p for p in profiles if p.deck_id == self._deck_b_id)

        board_data = json.loads(self._board_path.read_text(encoding="utf-8"))
        card_data = json.loads(self._card_path.read_text(encoding="utf-8"))
        base_setup = json.loads(self._setup_path.read_text(encoding="utf-8"))

        starter_deck = base_setup.get("starter_deck")
        market_row_size = base_setup.get("market_row_size")
        if not isinstance(starter_deck, dict) or not isinstance(market_row_size, int):
            raise ValueError("Base setup file must define starter_deck and market_row_size")

        market_setup = combine_two_deck_market_setup(
            base_setup, deck_a, deck_b,
        )
        setup_data = market_setup.to_setup_data()

        definition = build_game_definition_from_dicts(board_data, card_data, setup_data)
        state = build_initial_game_state(
            definition,
            player_ids=self._player_ids,
            shuffle_seed=self._effective_seed(),
        )
        return GameSession(state)

    def _repair_hand_index(self, state: GameState, payload: dict[str, object]) -> dict[str, object]:
        """Fix a PlayCardMove payload's hand_index if it doesn't match the current state.

        ISMCTS and simulation replays capture hand_index at recording time.
        If the session was re-created with a different seed (e.g., due to the
        ISMCTS public→internal seed mapping), the hand order may differ.  This
        method looks up the correct index by card_id and returns a patched
        payload.  For non-play_card payloads, returns the original unchanged.
        """
        move_type = payload.get("move_type")
        if move_type != "play_card":
            return payload

        card_id = payload.get("card_id")
        if not isinstance(card_id, str):
            return payload

        raw_index = payload.get("hand_index")
        if not isinstance(raw_index, int):
            return payload

        # Find the current player's hand in the engine state.
        player_id = payload.get("player_id")
        if not isinstance(player_id, str):
            return payload

        player_state = state.players.get(player_id)
        if player_state is None:
            return payload

        hand = player_state.hand
        # If the recorded index already matches, no repair needed.
        if raw_index < len(hand) and hand[raw_index] == card_id:
            return payload

        # Search for the card in the hand by id.
        for idx, cid in enumerate(hand):
            if cid == card_id:
                return {**payload, "hand_index": idx}

        # Card not found in hand — set hand_index to None so the rules engine
        # falls back to a card_id lookup via hand.index().  This handles C-engine
        # replays where the hand content diverges from the recorded hand_index.
        return {**payload, "hand_index": None}

    @staticmethod
    def _repair_recruit_market_slot(state: GameState, payload: dict[str, object]) -> dict[str, object]:
        """Convert C-engine recruit's card_id into Python's market_slot index.

        The C engine records which card was recruited by its card_id; the Python
        engine expects the market slot index.  This repair looks up the card_id
        in the current market row and special-recruit slots and replaces it with
        the corresponding index.
        """
        if payload.get("move_type") != "recruit":
            return payload
        if "market_slot" in payload:
            return payload
        from engine.moves import SPECIAL_RECRUIT_SLOT_CARD_IDS

        card_id = payload.get("card_id")
        if not isinstance(card_id, str):
            return payload

        # Check special recruit slots first.
        for slot, cid in SPECIAL_RECRUIT_SLOT_CARD_IDS.items():
            if cid == card_id:
                result = {k: v for k, v in payload.items() if k != "card_id"}
                result["market_slot"] = slot
                return result

        # Look up in the market row.
        for idx, cid in enumerate(state.market.row):
            if cid == card_id:
                result = {k: v for k, v in payload.items() if k != "card_id"}
                result["market_slot"] = idx
                return result

        return payload

    @staticmethod
    def _repair_generic_choice(state: GameState, payload: dict[str, object]) -> dict[str, object]:
        """Convert C-engine resolve_generic fields into Python ResolveGenericChoiceMove format.

        The C engine stores the selection as flat fields (action_id, target_id,
        selection_index) inside 'data'.  After structural normalisation these
        become top-level keys, but Pydantic still rejects them (extra="forbid")
        and the required source_card_id is missing.  This method reads the
        pending generic choice from the game state to fill in source_card_id and
        repackages the selection data into the 'selection' dict.
        """
        if payload.get("move_type") != "resolve_generic_choice":
            return payload
        if "source_card_id" in payload:
            return payload
        if "action_id" not in payload:
            return payload

        pending = state.pending_generic_choice
        if pending is None:
            return payload

        action_id = payload.get("action_id", "")
        option_id: str | None = None
        selection: dict[str, object] = {}

        # action_id starting with "option_" maps to option_id; everything else goes into selection.
        if isinstance(action_id, str) and action_id.startswith("option_"):
            option_id = action_id
        else:
            selection["action_id"] = action_id
            if "target_id" in payload:
                selection["target_id"] = payload["target_id"]
            if "selection_index" in payload:
                selection["selection_index"] = payload["selection_index"]

        result: dict[str, object] = {
            "move_type": "resolve_generic_choice",
            "player_id": payload["player_id"],
            "source_card_id": pending.source_card_id,
        }
        if option_id is not None:
            result["option_id"] = option_id
        if selection:
            result["selection"] = selection

        return result

    def _repair_cengine_move(self, state: GameState, payload: dict[str, object]) -> dict[str, object]:
        """Run all C-engine-specific repairs on a normalised move payload."""
        payload = self._repair_hand_index(state, payload)
        payload = self._repair_recruit_market_slot(state, payload)
        payload = self._repair_generic_choice(state, payload)
        return payload

    def _session_at_index(self, index: int) -> GameSession:
        if index == 0:
            session = self._fresh_session()
            self._cached_index = 0
            self._cached_session = session
            return session

        if self._cached_session is not None and self._cached_index == index:
            return self._cached_session

        if self._cached_session is not None and 0 < index <= self.max_step and self._cached_index < index:
            session = self._cached_session
            for i in range(self._cached_index, index):
                raw_payload = self._all_move_payloads[i]
                patched = self._repair_cengine_move(session.state, raw_payload)
                try:
                    move = MOVE_ADAPTER.validate_python(patched)
                    session.submit_move(move)
                except (IllegalMoveError, ValueError, PydanticValidationError) as exc:
                    logging.warning(
                        "Skipping replay step %d (%s): %s",
                        i, patched.get("move_type", "?"), exc,
                    )
                    # Skipped move means the cache is stale — reset so future
                    # lookups rebuild from scratch instead of using diverged state.
                    self._cached_session = None
                    self._cached_index = None
                    break
            else:
                self._cached_index = index
                self._cached_session = session
            return session

        session = self._fresh_session()
        for i in range(index):
            raw_payload = self._all_move_payloads[i]
            patched = self._repair_cengine_move(session.state, raw_payload)
            try:
                move = MOVE_ADAPTER.validate_python(patched)
                session.submit_move(move)
            except (IllegalMoveError, ValueError, PydanticValidationError) as exc:
                logging.warning(
                    "Skipping replay step %d (%s): %s",
                    i, patched.get("move_type", "?"), exc,
                )
        self._cached_index = index
        self._cached_session = session
        return session

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=8)
        frame.pack(fill=tk.BOTH, expand=True)

        controls = ttk.Frame(frame)
        controls.pack(fill=tk.X)

        ttk.Button(controls, text="Load Replay", command=self._load_replay_file).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Button(controls, text="Prev", command=self._prev_step).pack(side=tk.LEFT)
        ttk.Button(controls, text="Next", command=self._next_step).pack(side=tk.LEFT, padx=6)

        self.slider = tk.Scale(
            controls,
            from_=0,
            to=self.max_step,
            orient=tk.HORIZONTAL,
            showvalue=True,
            command=self._on_slider_change,
            length=360,
        )
        self.slider.pack(side=tk.LEFT, padx=(6, 0))

        ttk.Label(controls, textvariable=self.status_var, font=("TkFixedFont", 9)).pack(side=tk.LEFT, padx=12)

        content = ttk.Frame(frame)
        content.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        canvas_frame = ttk.Frame(content)
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        market_frame = ttk.LabelFrame(canvas_frame, text="Market Deck", padding=6)
        market_frame.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(market_frame, textvariable=self.market_meta_var, justify=tk.LEFT, font=("TkFixedFont", 9)).pack(anchor=tk.W)
        market_row_frame = ttk.Frame(market_frame)
        market_row_frame.pack(fill=tk.X)
        self.market_canvas = tk.Canvas(
            market_row_frame,
            height=MARKET_CARD_HEIGHT + (CARD_ROW_TOP_PAD * 2),
            bg="#f2f5f9",
            highlightthickness=1,
            highlightbackground="#9eb4d0",
            highlightcolor="#3d5f90",
        )
        self.market_canvas.pack(fill=tk.X)
        self.market_scrollbar = ttk.Scrollbar(market_row_frame, orient=tk.HORIZONTAL, command=self.market_canvas.xview)
        self.market_scrollbar.pack(fill=tk.X, pady=(2, 0))
        self.market_canvas.configure(xscrollcommand=self.market_scrollbar.set)
        self.market_canvas.bind("<Motion>", self._on_market_canvas_hover)
        self.market_canvas.bind("<Leave>", self._on_card_canvas_leave)

        map_frame = ttk.LabelFrame(canvas_frame, text="Map", padding=4)
        map_frame.pack(fill=tk.BOTH, expand=True)
        zoom_bar = ttk.Frame(map_frame)
        zoom_bar.pack(fill=tk.X, pady=(0, 2))
        ttk.Button(zoom_bar, text="-", command=self._zoom_out, width=4).pack(side=tk.LEFT)
        ttk.Button(zoom_bar, text="+", command=self._zoom_in, width=4).pack(side=tk.LEFT, padx=(2, 0))
        ttk.Button(zoom_bar, text="Fit", command=self._auto_fit_zoom, width=4).pack(side=tk.LEFT, padx=(2, 0))
        self._zoom_status_var = tk.StringVar(value="")
        ttk.Label(zoom_bar, textvariable=self._zoom_status_var, font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(6, 0))
        map_canvas_row = ttk.Frame(map_frame)
        map_canvas_row.pack(fill=tk.BOTH, expand=True)
        pkg_canvas = self.package.layout.canvas if self.package is not None else None
        canvas_w = min(pkg_canvas.width, MAP_VIEWPORT_MAX_WIDTH) if pkg_canvas is not None else MAP_VIEWPORT_MAX_WIDTH
        canvas_h = min(pkg_canvas.height, MAP_VIEWPORT_MAX_HEIGHT) if pkg_canvas is not None else MAP_VIEWPORT_MAX_HEIGHT
        self.canvas = tk.Canvas(
            map_canvas_row,
            width=canvas_w,
            height=canvas_h,
            bg="#f7f8fa",
            highlightthickness=1,
            highlightbackground="#c4cdd8",
        )
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.map_scrollbar_y = ttk.Scrollbar(map_canvas_row, orient=tk.VERTICAL, command=self.canvas.yview)
        self.map_scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.map_scrollbar_x = ttk.Scrollbar(map_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.map_scrollbar_x.pack(fill=tk.X, pady=(2, 0))
        self.canvas.configure(xscrollcommand=self.map_scrollbar_x.set, yscrollcommand=self.map_scrollbar_y.set)
        bind_canvas_scrolling(self.canvas, self._zoom_in, self._zoom_out)
        self.root.bind("<plus>", lambda _: self._zoom_in())
        self.root.bind("<minus>", lambda _: self._zoom_out())
        self.root.bind("<Control-equal>", lambda _: self._zoom_in())
        self.root.bind("<Left>", lambda _: self._prev_step())
        self.root.bind("<Right>", lambda _: self._next_step())

        bottom_frame = ttk.LabelFrame(canvas_frame, text="Current Player", padding=0)
        bottom_frame.pack(fill=tk.X, pady=(6, 0))

        bottom_scroll_frame = ttk.Frame(bottom_frame)
        bottom_scroll_frame.pack(fill=tk.BOTH, expand=True)
        self.current_player_canvas = tk.Canvas(
            bottom_scroll_frame,
            height=300,
            bg="#f2f5f9",
            highlightthickness=0,
        )
        self.current_player_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.current_player_scrollbar = ttk.Scrollbar(
            bottom_scroll_frame,
            orient=tk.VERTICAL,
            command=self.current_player_canvas.yview,
        )
        self.current_player_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.current_player_canvas.configure(yscrollcommand=self.current_player_scrollbar.set)

        bottom_content = ttk.Frame(self.current_player_canvas, padding=6)
        self._current_player_content_id = self.current_player_canvas.create_window(
            (0, 0), window=bottom_content, anchor=tk.NW
        )
        self.current_player_canvas.bind("<Configure>", self._on_current_player_canvas_configure)
        bottom_content.bind("<Configure>", self._on_current_player_content_configure)

        ttk.Label(bottom_content, textvariable=self.resource_var, font=("TkFixedFont", 10, "bold")).pack(anchor=tk.W)
        ttk.Label(
            bottom_content, textvariable=self.vp_breakdown_var, font=("TkFixedFont", 9)
        ).pack(anchor=tk.W, pady=(4, 0))

        hg_frame = ttk.Frame(bottom_content)
        hg_frame.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(hg_frame, text="House Guard:", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        ttk.Label(hg_frame, textvariable=self.house_guard_var, font=("TkFixedFont", 9)).pack(side=tk.LEFT, padx=(8, 20))

        pr_frame = ttk.Frame(bottom_content)
        pr_frame.pack(fill=tk.X)
        ttk.Label(pr_frame, text="Priestess:", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        ttk.Label(pr_frame, textvariable=self.priestess_var, font=("TkFixedFont", 9)).pack(side=tk.LEFT, padx=(16, 0))

        discard_frame = ttk.Frame(bottom_content)
        discard_frame.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(discard_frame, text="Discard Pile:", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        self.discard_box = ttk.Combobox(
            discard_frame,
            state="readonly",
            textvariable=self.discard_selection_var,
            width=90,
        )
        self.discard_box.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))

        inner_circle_frame = ttk.Frame(bottom_content)
        inner_circle_frame.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(inner_circle_frame, text="Inner Circle:", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        self.inner_circle_box = ttk.Combobox(
            inner_circle_frame,
            state="readonly",
            textvariable=self.inner_circle_selection_var,
            width=90,
        )
        self.inner_circle_box.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
        ttk.Label(
            bottom_content,
            textvariable=self.inner_circle_meta_var,
            font=("TkFixedFont", 9),
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(2, 0))

        trophy_hall_frame = ttk.Frame(bottom_content)
        trophy_hall_frame.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(trophy_hall_frame, text="Trophy Hall:", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        self.trophy_hall_box = ttk.Combobox(
            trophy_hall_frame,
            state="readonly",
            textvariable=self.trophy_hall_selection_var,
            width=90,
        )
        self.trophy_hall_box.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
        ttk.Label(
            bottom_content,
            textvariable=self.trophy_hall_meta_var,
            font=("TkFixedFont", 9),
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(2, 0))

        ttk.Label(bottom_content, text="Cards in Hand", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, pady=(6, 0))
        hand_row_frame = ttk.Frame(bottom_content)
        hand_row_frame.pack(fill=tk.X)
        self.hand_canvas = tk.Canvas(
            hand_row_frame,
            height=PLAYER_CARD_HEIGHT + (CARD_ROW_TOP_PAD * 2),
            bg="#f2f5f9",
            highlightthickness=1,
            highlightbackground="#9eb4d0",
            highlightcolor="#3d5f90",
        )
        self.hand_canvas.pack(fill=tk.X)
        self.hand_scrollbar = ttk.Scrollbar(hand_row_frame, orient=tk.HORIZONTAL, command=self.hand_canvas.xview)
        self.hand_scrollbar.pack(fill=tk.X, pady=(2, 0))
        self.hand_canvas.configure(xscrollcommand=self.hand_scrollbar.set)
        self.hand_canvas.bind("<Motion>", self._on_hand_canvas_hover)
        self.hand_canvas.bind("<Leave>", self._on_card_canvas_leave)

        ttk.Label(bottom_content, text="Played This Phase", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, pady=(6, 0))
        played_row_frame = ttk.Frame(bottom_content)
        played_row_frame.pack(fill=tk.X)
        self.played_canvas = tk.Canvas(
            played_row_frame,
            height=PLAYER_CARD_HEIGHT + (CARD_ROW_TOP_PAD * 2),
            bg="#f2f5f9",
            highlightthickness=1,
            highlightbackground="#9eb4d0",
            highlightcolor="#3d5f90",
        )
        self.played_canvas.pack(fill=tk.X)
        self.played_scrollbar = ttk.Scrollbar(played_row_frame, orient=tk.HORIZONTAL, command=self.played_canvas.xview)
        self.played_scrollbar.pack(fill=tk.X, pady=(2, 0))
        self.played_canvas.configure(xscrollcommand=self.played_scrollbar.set)
        self.played_canvas.bind("<Motion>", self._on_played_canvas_hover)
        self.played_canvas.bind("<Leave>", self._on_card_canvas_leave)

        sidebar = ttk.Frame(content, width=360)
        sidebar.pack(side=tk.RIGHT, fill=tk.Y)
        sidebar.pack_propagate(False)

        ttk.Label(sidebar, text="Move", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        ttk.Label(
            sidebar, textvariable=self.move_var, wraplength=340, justify=tk.LEFT
        ).pack(anchor=tk.W, pady=(0, 10))

        ttk.Label(sidebar, text="Prompts", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        ttk.Label(
            sidebar, textvariable=self.prompt_var, wraplength=340, justify=tk.LEFT
        ).pack(anchor=tk.W, pady=(0, 10))

        ttk.Label(sidebar, text="Players", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        ttk.Label(
            sidebar, textvariable=self.players_var, wraplength=340, justify=tk.LEFT
        ).pack(anchor=tk.W)

    def _render_step(self, index: int) -> None:
        if self.package is None:
            return
        index = max(0, min(index, self.max_step))
        self.current_index = index
        self.slider.set(index)

        session = self._session_at_index(index)
        view = build_game_view(session, node_names=self._node_names)

        self.renderer.redraw(self.canvas, self.package, view, scale=self.zoom_level)
        scaled_w = self.package.layout.canvas.width * self.zoom_level
        scaled_h = self.package.layout.canvas.height * self.zoom_level
        self.canvas.configure(scrollregion=(0, 0, scaled_w, scaled_h))

        state = session.state
        current_player = state.players[state.current_player_id]
        cards_by_id = {card.card_id: card for card in state.definition.catalog.cards}

        self.status_var.set(
            f"Step {index}/{self.max_step} | Round {view.round_number} | "
            f"Phase {view.phase} | Current {view.current_player_id}"
        )

        self.resource_var.set(
            f"Power: {view.resource_power:>3}    Influence: {view.resource_influence:>3}"
            f"  |  Sites: {view.current_player_controlled_sites} controlled, {view.current_player_total_control_sites} total"
            f"  |  Hand: {_format_aspect_breakdown(_compute_aspect_focus(view.hand))}"
            f"  |  Played: {_format_aspect_breakdown(_compute_aspect_focus(view.current_player_played))}"
        )

        self._set_vp_breakdown(state, current_player)
        self.prompt_var.set("\n".join(view.prompts))

        deck_ctx = self._resolve_deck_context()
        self.market_meta_var.set(
            f"Deck A: {deck_ctx}    |    "
            f"Market deck: {len(view.market_row):>1} visible    Deck remaining: {view.market_deck_count:>3}    "
            f"Discard: {view.market_discard_count:>3}"
        )

        self.house_guard_var.set(
            self._starter_pile_summary(
                current_player,
                HOUSE_GUARD_CARD_ID,
            )
        )
        self.priestess_var.set(
            self._starter_pile_summary(
                current_player,
                PRIESTESS_CARD_ID,
            )
        )

        discard_options = _format_ordered_card_options(current_player.discard_pile, cards_by_id)
        self.discard_box["values"] = discard_options
        if self.discard_selection_var.get() not in discard_options:
            self.discard_selection_var.set(discard_options[0])

        inner_circle_options = _format_ordered_card_options(
            [card.card_id for card in view.current_player_inner_circle],
            cards_by_id,
        )
        self.inner_circle_box["values"] = inner_circle_options
        if self.inner_circle_selection_var.get() not in inner_circle_options:
            self.inner_circle_selection_var.set(inner_circle_options[0])
        inner_circle_vp_total = sum(card.inner_circle_vp for card in view.current_player_inner_circle)
        self.inner_circle_meta_var.set(
            f"End-game Inner Circle VP: {inner_circle_vp_total:>2}    "
            f"Cards: {len(view.current_player_inner_circle):>2}"
        )

        trophy_hall_options = _format_trophy_hall_options(view.current_player_trophy_hall)
        self.trophy_hall_box["values"] = trophy_hall_options
        if self.trophy_hall_selection_var.get() not in trophy_hall_options:
            self.trophy_hall_selection_var.set(trophy_hall_options[0])
        self.trophy_hall_meta_var.set(f"Captured Trophies: {len(view.current_player_trophy_hall):>2}")

        player_lines = [
            (
                f"{summary.player_id}{' *' if summary.is_current else ''}: "
                f"score {summary.score}, hand {summary.hand_count}, deck {summary.deck_count}, "
                f"discard {summary.discard_count}, played {summary.played_count}, "
                f"barracks {summary.barracks}, spies {summary.spies_available}, vp {summary.vp_tokens}"
            )
            for summary in view.player_summaries
        ]
        self.players_var.set("\n".join(player_lines))

        if index == 0:
            self.move_var.set("Initial state")
        else:
            label = self._all_move_labels[index - 1]
            move_type = self._all_move_types[index - 1]
            self.move_var.set(f"{label}\n({move_type})")

        self._apply_responsive_layout()
        self._sync_market_row(view)
        self._sync_hand_row(view)
        self._sync_played_row(view)

    def _resolve_deck_context(self) -> str:
        if self._aberrations_in_market:
            return "Aberrations"
        return "Standard"

    def _set_vp_breakdown(self, state: GameState, current_player: object) -> None:
        node_index = board_index(state.definition.board)
        card_index_lookup = state_card_index(state.definition.catalog)
        player_id = state.current_player_id

        control_vp = 0
        total_control_vp_per_turn = 0
        for node_id, node_def in node_index.items():
            if node_def.kind != NodeKind.SITE:
                continue
            if _site_control_owner(state, node_id) == player_id:
                control_vp += node_def.control_vp
            if _is_total_control(state, node_id, player_id):
                total_control_vp_per_turn += node_def.total_control_vp_per_turn

        trophy_vp = len(current_player.trophy_hall)
        token_vp = current_player.vp_tokens
        deck_zone_cards = current_player.deck + current_player.hand + current_player.discard_pile + current_player.played_cards
        deck_vp = _cards_vp(deck_zone_cards, card_index_lookup, "deck_vp")
        inner_circle_vp = _cards_vp(current_player.inner_circle, card_index_lookup, "inner_circle_vp")

        running_score = current_player.score
        total_vp = running_score + control_vp + total_control_vp_per_turn + trophy_vp + token_vp + deck_vp + inner_circle_vp

        self.vp_breakdown_var.set(
            f"Controlled sites VP: {control_vp:>2} | "
            f"Total Control VP/turn: {total_control_vp_per_turn:>2} | "
            f"Trophy: {trophy_vp:>2} | VP tokens: {token_vp:>2} | Deck VP: {deck_vp:>2} | "
            f"Inner Circle VP: {inner_circle_vp:>2} | Total: {total_vp:>2}"
        )

    def _starter_pile_summary(self, player: object, card_id: str) -> str:
        deck_count = player.deck.count(card_id)
        hand_count = player.hand.count(card_id)
        played_count = player.played_cards.count(card_id)
        discard_count = player.discard_pile.count(card_id)
        inner_circle_count = player.inner_circle.count(card_id)
        owned_total = deck_count + hand_count + played_count + discard_count + inner_circle_count
        return (
            f"deck {deck_count:>2} | hand {hand_count:>2} | played {played_count:>2}\n"
            f"discard {discard_count:>2} | inner {inner_circle_count:>2} | total {owned_total:>2}"
        )

    def _sync_market_row(self, view: GameView) -> None:
        session = self._session_at_index(self.current_index)
        cards_by_id = {card.card_id: card for card in session.state.definition.catalog.cards}

        house_guard_card = self._card_view_from_definition(cards_by_id.get(HOUSE_GUARD_CARD_ID), HOUSE_GUARD_CARD_ID)
        priestess_card = self._card_view_from_definition(cards_by_id.get(PRIESTESS_CARD_ID), PRIESTESS_CARD_ID)
        outcast_card = self._card_view_from_definition(cards_by_id.get(INSANE_OUTCAST_CARD_ID), INSANE_OUTCAST_CARD_ID)

        market_cards = list(view.market_row[:6])
        while len(market_cards) < 6:
            empty_index = len(market_cards) + 1
            market_cards.append(
                CardView(
                    card_id=f"market_empty_{empty_index}",
                    name=f"Market Slot {empty_index}",
                    cost=0,
                    aspect="empty",
                    deck_vp=0,
                    inner_circle_vp=0,
                    rules_text="Waiting for market refill",
                    notes="",
                )
            )

        top_cards = [house_guard_card, priestess_card, outcast_card, *market_cards]
        self._hover_market_cards = top_cards

        top_slot_to_market_slot: list[int | None] = [
            SPECIAL_TOP_SLOT_TO_MARKET_SLOT[0],
            SPECIAL_TOP_SLOT_TO_MARKET_SLOT[1],
            SPECIAL_TOP_SLOT_TO_MARKET_SLOT[2] if self._aberrations_in_market else None,
            *list(range(len(view.market_row))),
        ]
        while len(top_slot_to_market_slot) < TOP_DECK_SLOT_COUNT:
            top_slot_to_market_slot.append(None)

        if not self._aberrations_in_market:
            top_cards[2] = CardView(
                card_id="insane_outcast_disabled",
                name="Insane Outcasts",
                cost=0,
                aspect="inactive",
                deck_vp=0,
                inner_circle_vp=0,
                rules_text="Disabled (requires Aberrations in market deck)",
                notes="",
            )

        top_hitboxes = self._draw_card_row(
            self.market_canvas,
            tuple(top_cards),
            tint_colors={
                0: SPECIAL_CARD_TINTS[HOUSE_GUARD_CARD_ID],
                1: SPECIAL_CARD_TINTS[PRIESTESS_CARD_ID],
                2: SPECIAL_CARD_TINTS[INSANE_OUTCAST_CARD_ID],
            },
            compact=True,
        )
        self._hover_market_hitboxes = top_hitboxes

        self._market_hitboxes = []
        for x0, y0, x1, y1, top_index in top_hitboxes:
            if top_index >= len(top_slot_to_market_slot):
                continue
            market_slot = top_slot_to_market_slot[top_index]
            if market_slot is not None:
                self._market_hitboxes.append((x0, y0, x1, y1, market_slot))

    def _sync_hand_row(self, view: GameView) -> None:
        self._hover_hand_cards = list(view.hand)
        self._hand_hitboxes = self._draw_card_row(
            self.hand_canvas,
            view.hand,
            compact=self._compact_player_rows,
        )

    def _sync_played_row(self, view: GameView) -> None:
        self._hover_played_cards = list(view.current_player_played)
        self._played_hitboxes = self._draw_card_row(
            self.played_canvas,
            view.current_player_played,
            compact=self._compact_player_rows,
            empty_label="No cards played this phase",
        )

    def _draw_card_row(
        self,
        canvas: tk.Canvas,
        cards: tuple[CardView, ...],
        *,
        tint_colors: dict[int, str] | None = None,
        compact: bool = False,
        empty_label: str = "No cards",
    ) -> list[tuple[int, int, int, int, int]]:
        canvas.delete("all")
        canvas.update_idletasks()

        card_width = self._market_card_width if compact else self._player_card_width
        card_height = self._market_card_height if compact else self._player_card_height

        card_count = len(cards)
        content_width = CARD_ROW_SIDE_PAD * 2 + (card_width * card_count) + (CARD_GAP * max(0, card_count - 1))
        content_height = CARD_ROW_TOP_PAD * 2 + card_height

        if not cards:
            canvas.create_text(
                CARD_ROW_SIDE_PAD,
                CARD_ROW_TOP_PAD + (card_height // 2),
                anchor=tk.W,
                text=empty_label,
                fill="#445066",
                font=("Segoe UI", 10),
            )
            canvas.configure(scrollregion=(0, 0, max(canvas.winfo_width(), CARD_ROW_SIDE_PAD * 2), content_height))
            return []

        tint_colors_map = tint_colors if tint_colors is not None else {}

        hitboxes: list[tuple[int, int, int, int, int]] = []
        for index, card in enumerate(cards):
            x0 = CARD_ROW_SIDE_PAD + index * (card_width + CARD_GAP)
            y0 = CARD_ROW_TOP_PAD
            x1 = x0 + card_width
            y1 = y0 + card_height

            fill = tint_colors_map.get(index, "#ffffff")

            outline = "#9eb4d0"
            line_width = 1
            canvas.create_rectangle(x0, y0, x1, y1, fill=fill, outline=outline, width=line_width)

            text_budget = max(10, (card_width - 14) // 5)

            if compact:
                name_chars = min(CARD_NAME_MAX_CHARS, text_budget + 4)
                meta_chars = min(CARD_META_MAX_CHARS, text_budget + 8)
                name_y = y0 + 13
                meta_y = y0 + 28
                rules_y = y0 + 42
                rules_width = card_width - 14
            else:
                name_chars = min(CARD_NAME_MAX_CHARS, text_budget + 12)
                meta_chars = min(CARD_META_MAX_CHARS, text_budget + 16)
                name_y = y0 + 18
                meta_y = y0 + 38
                rules_y = y0 + 56
                rules_width = card_width - 20

            canvas.create_text(
                x0 + 8,
                name_y,
                anchor=tk.W,
                text=_ellipsize(card.name, name_chars),
                fill="#152238",
                font=("Segoe UI", 9, "bold"),
            )

            if card.secondary_aspects:
                secondary = " / ".join((card.aspect, *card.secondary_aspects))
                aspect_display = f"{secondary}  |  "
            else:
                aspect_display = f"{card.aspect}  |  " if card.aspect else ""

            canvas.create_text(
                x0 + 8,
                meta_y,
                anchor=tk.W,
                text=_ellipsize(
                    f"{aspect_display}Cost {card.cost}  |  VP {card.deck_vp}/{card.inner_circle_vp}",
                    meta_chars,
                ),
                fill="#2c3f5f",
                font=("Segoe UI", 8),
            )

            rules_text = card.rules_text.strip() or "(no rules text)"
            canvas.create_text(
                x0 + 8,
                rules_y,
                anchor=tk.NW,
                text=rules_text,
                fill="#394f71",
                font=("Segoe UI", 8),
                width=rules_width,
                justify=tk.LEFT,
            )
            hitboxes.append((x0, y0, x1, y1, index))

        canvas.configure(scrollregion=(0, 0, max(content_width, canvas.winfo_width()), content_height))
        return hitboxes

    def _card_view_from_definition(self, card_definition: object | None, fallback_card_id: str) -> CardView:
        if card_definition is None:
            return CardView(
                card_id=fallback_card_id,
                name="Unknown Card",
                cost=0,
                aspect="unknown",
                deck_vp=0,
                inner_circle_vp=0,
                rules_text="",
                notes="",
            )
        return CardView(
            card_id=card_definition.card_id,
            name=card_definition.name,
            cost=card_definition.cost,
            aspect=card_definition.aspect,
            deck_vp=card_definition.deck_vp,
            inner_circle_vp=card_definition.inner_circle_vp,
            rules_text=card_definition.rules_text,
            notes=card_definition.notes,
            secondary_aspects=tuple(getattr(card_definition, "secondary_aspects", ())),
        )

    def _card_index_at_point(
        self,
        x: float,
        y: float,
        hitboxes: list[tuple[int, int, int, int, int]],
    ) -> int | None:
        for x0, y0, x1, y1, index in hitboxes:
            if x0 <= x <= x1 and y0 <= y <= y1:
                return index
        return None

    def _on_market_canvas_hover(self, event: tk.Event[tk.Canvas]) -> None:
        selected_index = self._card_index_at_point(
            self.market_canvas.canvasx(event.x),
            self.market_canvas.canvasy(event.y),
            self._hover_market_hitboxes,
        )
        self._set_hover_card("Market", self._hover_market_cards, selected_index, event.x_root, event.y_root)

    def _on_hand_canvas_hover(self, event: tk.Event[tk.Canvas]) -> None:
        selected_index = self._card_index_at_point(
            self.hand_canvas.canvasx(event.x),
            self.hand_canvas.canvasy(event.y),
            self._hand_hitboxes,
        )
        self._set_hover_card("Hand", self._hover_hand_cards, selected_index, event.x_root, event.y_root)

    def _on_played_canvas_hover(self, event: tk.Event[tk.Canvas]) -> None:
        selected_index = self._card_index_at_point(
            self.played_canvas.canvasx(event.x),
            self.played_canvas.canvasy(event.y),
            self._played_hitboxes,
        )
        self._set_hover_card("Played", self._hover_played_cards, selected_index, event.x_root, event.y_root)

    def _on_card_canvas_leave(self, _event: tk.Event[tk.Canvas]) -> None:
        self._hide_card_popup()

    def _set_hover_card(
        self, zone_name: str, cards: Sequence[CardView], index: int | None, x_root: int = 0, y_root: int = 0
    ) -> None:
        if index is None or index < 0 or index >= len(cards):
            self._hide_card_popup()
            return
        card = cards[index]
        self._show_card_popup(card, x_root, y_root, zone_name)

    def _show_card_popup(self, card: CardView, x_root: int, y_root: int, zone_name: str) -> None:
        self._hide_card_popup()
        popup = tk.Toplevel(self.root)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        frame = ttk.Frame(popup, padding=8)
        frame.pack(fill=tk.BOTH, expand=True)
        title_label = ttk.Label(frame, text=f"{zone_name}: {card.name}", font=("Segoe UI", 9, "bold"))
        title_label.pack(anchor=tk.W)
        detail_text = _format_card_hover_details(card)
        detail_label = ttk.Label(frame, text=detail_text, font=("Segoe UI", 8), wraplength=280, justify=tk.LEFT)
        detail_label.pack(anchor=tk.W, pady=(4, 0))
        popup.update_idletasks()
        popup_x = x_root + 16
        popup_y = y_root + 8
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        pw = popup.winfo_width()
        ph = popup.winfo_height()
        if popup_x + pw > screen_w:
            popup_x = x_root - pw - 16
        if popup_y + ph > screen_h:
            popup_y = y_root - ph - 8
        popup.geometry(f"+{popup_x}+{popup_y}")
        self._hover_popup = popup

    def _hide_card_popup(self) -> None:
        if self._hover_popup is not None:
            self._hover_popup.destroy()
            self._hover_popup = None

    def _prev_step(self) -> None:
        self._render_step(self.current_index - 1)

    def _next_step(self) -> None:
        self._render_step(self.current_index + 1)

    def _on_slider_change(self, value: str) -> None:
        self._render_step(int(float(value)))

    def _auto_fit_zoom(self) -> None:
        if self.package is None:
            return
        bboxes: list[tuple[float, float, float, float]] = []
        for node in self.package.layout.nodes:
            if node.bounds is not None:
                b = node.bounds
                bboxes.append((b.x, b.y, b.x + b.width, b.y + b.height))
            else:
                bboxes.append((node.center.x - 14, node.center.y - 14, node.center.x + 14, node.center.y + 14))

        view_w = self.canvas.winfo_width()
        view_h = self.canvas.winfo_height()
        if view_w < 10:
            view_w = int(self.canvas.cget("width"))
        if view_h < 10:
            view_h = int(self.canvas.cget("height"))

        result = compute_fit_zoom(bboxes, view_w, view_h, min_zoom=self._min_zoom, max_zoom=self._max_zoom)
        if result is None:
            return

        self.zoom_level = result.zoom
        scaled_w = self.package.layout.canvas.width * self.zoom_level
        scaled_h = self.package.layout.canvas.height * self.zoom_level
        self.canvas.configure(scrollregion=(0, 0, scaled_w, scaled_h))

        scroll_x = (result.center_x * self.zoom_level) - (view_w / 2)
        scroll_y = (result.center_y * self.zoom_level) - (view_h / 2)
        self.canvas.xview_moveto(min(1.0, max(0.0, scroll_x / scaled_w)))
        self.canvas.yview_moveto(min(1.0, max(0.0, scroll_y / scaled_h)))

        self._zoom_status_var.set(f"{self.zoom_level:.0%}")
        self._render_step(self.current_index)

    def _zoom_in(self) -> None:
        self._change_zoom(self.zoom_level * 1.2)

    def _zoom_out(self) -> None:
        self._change_zoom(self.zoom_level / 1.2)

    def _change_zoom(self, new_zoom: float) -> None:
        new_zoom = max(self._min_zoom, min(self._max_zoom, new_zoom))
        if abs(new_zoom - self.zoom_level) < 0.001:
            return
        self.zoom_level = new_zoom
        self._zoom_status_var.set(f"{self.zoom_level:.0%}")
        self._render_step(self.current_index)

    def _on_root_configure(self, event: tk.Event[tk.Tk]) -> None:
        if event.widget is not self.root:
            return
        if self._resize_after_id is not None:
            self.root.after_cancel(self._resize_after_id)
        self._resize_after_id = self.root.after(60, self._on_resized)

    def _on_current_player_canvas_configure(self, event: tk.Event[tk.Canvas]) -> None:
        self.current_player_canvas.itemconfigure(self._current_player_content_id, width=event.width)

    def _on_current_player_content_configure(self, _event: tk.Event[ttk.Frame]) -> None:
        self.current_player_canvas.configure(scrollregion=self.current_player_canvas.bbox("all"))

    def _on_resized(self) -> None:
        self._resize_after_id = None
        if self._pending_initial_fit:
            self._pending_initial_fit = False
            self._apply_responsive_layout()
            self._auto_fit_zoom()
            return
        self._apply_responsive_layout()
        self._render_step(self.current_index)

    def _apply_responsive_layout(self) -> None:
        if self.package is None:
            return
        root_width = max(self.root.winfo_width(), 1)
        root_height = max(self.root.winfo_height(), 1)

        if root_height < 760 or root_width < 1200:
            self._compact_player_rows = True
            self._player_card_width = 132
            self._player_card_height = 72
        elif root_height < 860 or root_width < 1350:
            self._compact_player_rows = True
            self._player_card_width = 148
            self._player_card_height = 92
        elif root_height < 980 or root_width < 1520:
            self._compact_player_rows = True
            self._player_card_width = PLAYER_CARD_WIDTH_COMPACT
            self._player_card_height = PLAYER_CARD_HEIGHT_COMPACT
        else:
            self._compact_player_rows = False
            self._player_card_width = PLAYER_CARD_WIDTH
            self._player_card_height = PLAYER_CARD_HEIGHT

        market_canvas_width = max(self.market_canvas.winfo_width(), root_width - 520)
        total_gap = CARD_GAP * (TOP_DECK_SLOT_COUNT - 1)
        total_padding = CARD_ROW_SIDE_PAD * 2
        max_slot_width = 200
        min_slot_width = 72
        fitted_slot_width = (market_canvas_width - total_gap - total_padding) // TOP_DECK_SLOT_COUNT
        self._market_card_width = max(min_slot_width, min(max_slot_width, fitted_slot_width))
        if root_height < 760:
            self._market_card_height = 82
        elif root_height < 860:
            self._market_card_height = 94
        else:
            self._market_card_height = MARKET_CARD_HEIGHT

        player_row_height = self._player_card_height + (CARD_ROW_TOP_PAD * 2)
        self.played_canvas.configure(height=player_row_height)
        self.hand_canvas.configure(height=player_row_height)
        if hasattr(self, "current_player_canvas"):
            current_panel_height = min(380, max(180, (root_height // 3) + 20))
            self.current_player_canvas.configure(height=current_panel_height)

        market_row_height = self._market_card_height + (CARD_ROW_TOP_PAD * 2)
        self.market_canvas.configure(height=market_row_height)

        map_reserved_height = 360 + (player_row_height * 2)
        map_target_height = root_height - map_reserved_height
        map_target_width = root_width - 520
        map_height = max(1, min(self.package.layout.canvas.height, map_target_height))
        map_width = max(560, min(self.package.layout.canvas.width, map_target_width, MAP_VIEWPORT_MAX_WIDTH))
        self.canvas.configure(
            width=map_width,
            height=map_height,
            scrollregion=(
                0, 0,
                self.package.layout.canvas.width * self.zoom_level,
                self.package.layout.canvas.height * self.zoom_level,
            ),
        )


def _parse_player_ids(raw_player_ids: str | None) -> list[str] | None:
    if raw_player_ids is None:
        return None
    player_ids = [player_id.strip() for player_id in raw_player_ids.split(",") if player_id.strip()]
    return player_ids or None


def _load_payload(path: Path) -> dict[str, object]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("Replay file must contain a JSON object")
    return loaded


def main() -> None:
    """Run the replay viewer for a simulation log file."""

    parser = argparse.ArgumentParser(description="Run the Tyrants replay viewer")
    parser.add_argument("--replay-log-path", type=Path, required=True)
    parser.add_argument("--layout-path", type=Path, default=DEFAULT_LAYOUT_PATH)
    parser.add_argument("--board-path", type=Path, default=DEFAULT_BOARD_PATH)
    parser.add_argument("--card-path", type=Path)
    parser.add_argument("--setup-path", type=Path)
    parser.add_argument("--players")
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()

    payload = _load_payload(args.replay_log_path)

    root = tk.Tk()
    ReplayViewerApp(
        root,
        board_path=args.board_path,
        layout_path=args.layout_path,
        replay_payload=payload,
        card_path=args.card_path,
        setup_path=args.setup_path,
        player_ids=_parse_player_ids(args.players),
        seed=args.seed,
    )
    root.mainloop()


if __name__ == "__main__":
    main()
