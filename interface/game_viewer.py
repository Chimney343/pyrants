"""Interactive Tk hotseat viewer powered by the shared session layer."""

from __future__ import annotations

import argparse
import json
import tkinter as tk
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from random import Random
from tkinter import filedialog, messagebox, ttk
from typing import Any

from engine.moves import (
    HOUSE_GUARD_RECRUIT_SLOT,
    INSANE_OUTCAST_RECRUIT_SLOT,
    PRIESTESS_RECRUIT_SLOT,
    PlayCardMove,
    ResolveGenericChoiceMove,
)
from engine.scoring import _cards_vp, _is_total_control, _site_control_owner
from engine.state import GameState, NodeKind, board_index, build_initial_game_state
from engine.state import card_index as state_card_index
from game_session import GameSession
from game_setup.board_package import BoardLayoutDefinition, BoardPackageDefinition, make_default_layout
from game_setup.loaders import build_board_package_from_files, build_game_definition_from_dicts, load_deck_rosters
from game_setup.scenarios import save_game_state
from game_view import CardView, GameView, LegalMoveView, build_game_view, filter_legal_moves
from interface._canvas_scroll import bind_canvas_scrolling
from interface.game_renderer import GameBoardRenderer
from interface.view_fit import compute_fit_zoom

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
DEFAULT_BOARD_PATH = ROOT_DIR / "data" / "boards" / "base_game.json"
DEFAULT_LAYOUT_PATH = ROOT_DIR / "data" / "layouts" / "base_game_layout.json"
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
CARD_TEXT_MAX_CHARS = 110
CARD_FLAVOR_MAX_CHARS = 85
MAP_VIEWPORT_MAX_HEIGHT = 430
MAP_VIEWPORT_MAX_WIDTH = 980
TOP_DECK_SLOT_COUNT = 9
TOP_DECK_SPECIAL_SLOTS = 3

HOUSE_GUARD_CARD_ID = "house_guard"
PRIESTESS_CARD_ID = "priestess_of_lolth"
INSANE_OUTCAST_CARD_ID = "insane_outcast"
ABERRATIONS_DECK_ID = "aberrations"

HOUSE_GUARD_STACK_TOTAL = 15
PRIESTESS_STACK_TOTAL = 15
INSANE_OUTCAST_STACK_TOTAL = 30

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


def _ellipsize(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return text[: max_chars - 3] + "..."


def _datetime_seed(now: datetime | None = None) -> int:
    """Build a high-entropy default seed from current local datetime."""

    timestamp = (now or datetime.now()).timestamp()
    return max(0, int(timestamp * 1_000_000))


def _resolve_seed_input(raw_seed: str | None) -> int:
    """Return explicit seed when provided, else datetime-derived default."""

    normalized = (raw_seed or "").strip()
    if not normalized:
        return _datetime_seed()
    return max(0, int(normalized))


def format_discard_pile_options(discard_pile: list[str], cards_by_id: dict[str, Any]) -> list[str]:
    """Build discard dropdown options as card-name entries with quantities."""

    if not discard_pile:
        return ["(empty)"]

    counts = Counter(discard_pile)

    def _sort_key(card_id: str) -> tuple[str, str]:
        card = cards_by_id.get(card_id)
        card_name = card.name if card is not None else "Unknown Card"
        return (card_name.casefold(), card_id.casefold())

    options: list[str] = []
    for card_id in sorted(counts, key=_sort_key):
        card = cards_by_id.get(card_id)
        card_name = card.name if card is not None else "Unknown Card"
        options.append(f"{card_name} x{counts[card_id]}")
    return options


def format_ordered_card_options(card_ids: Sequence[str], cards_by_id: Mapping[str, Any]) -> list[str]:
    """Build ordered card options with stable indices for current-player zones."""

    if not card_ids:
        return ["(empty)"]

    return [
        f"{index + 1}. {(cards_by_id.get(card_id).name if cards_by_id.get(card_id) is not None else 'Unknown Card')}"
        for index, card_id in enumerate(card_ids)
    ]


def format_card_hover_details(card: CardView) -> str:
    """Build multi-line hover details for one card."""

    rules_text = card.rules_text.strip() or "(none)"
    notes_text = card.notes.strip() or "(none)"
    return (
        f"Name: {card.name}\n"
        f"Cost: {card.cost}    Aspect: {card.aspect}\n"
        f"Deck VP: {card.deck_vp}    Inner Circle VP: {card.inner_circle_vp}\n"
        f"Rules: {rules_text}\n"
        f"Notes: {notes_text}"
    )


def format_trophy_hall_options(trophy_hall: Sequence[str]) -> list[str]:
    """Build ordered trophy hall entries for captured troop ownership markers."""

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


@dataclass(frozen=True)
class MapProfile:
    """One selectable board/layout pair for gameplay."""

    key: str
    label: str
    board_path: Path
    layout_path: Path


@dataclass(frozen=True)
class DeckProfile:
    """One selectable market half deck from roster data."""

    deck_id: str
    label: str
    total_cards: int
    entries: tuple[tuple[str, int], ...]


def discover_map_profiles(
    data_root: Path,
    *,
    default_board_path: Path,
    default_layout_path: Path,
) -> tuple[MapProfile, ...]:
    """Discover board/layout pairs from data folders."""

    board_dir = data_root / "boards"
    layout_dir = data_root / "layouts"
    profiles: list[MapProfile] = []

    for board_path in sorted(board_dir.glob("*.json")):
        candidate_layout_paths = [
            layout_dir / f"{board_path.stem}_layout.json",
            layout_dir / board_path.name,
        ]
        layout_path = next((path for path in candidate_layout_paths if path.exists()), None)
        if layout_path is None:
            continue

        key = board_path.stem
        profiles.append(
            MapProfile(
                key=key,
                label=key.replace("_", " ").title(),
                board_path=board_path,
                layout_path=layout_path,
            )
        )

    if not any(profile.board_path == default_board_path for profile in profiles):
        profiles.append(
            MapProfile(
                key=default_board_path.stem,
                label=default_board_path.stem.replace("_", " ").title(),
                board_path=default_board_path,
                layout_path=default_layout_path,
            )
        )

    return tuple(profiles)


def load_market_deck_profiles(decks_dir: Path) -> tuple[DeckProfile, ...]:
    """Load selectable 40-card market deck profiles from roster files."""

    raw_decks = load_deck_rosters(decks_dir)
    if not raw_decks:
        raise ValueError(f"No deck roster files found in {decks_dir}")

    profiles: list[DeckProfile] = []
    for raw_deck in raw_decks:
        if not isinstance(raw_deck, dict):
            continue
        kind = raw_deck.get("kind")
        total_cards = raw_deck.get("total_cards")
        if kind != "full_deck" or total_cards != 40:
            continue

        deck_id = raw_deck.get("deck_id")
        name = raw_deck.get("name")
        entries = raw_deck.get("entries")
        if not isinstance(deck_id, str) or not isinstance(name, str) or not isinstance(entries, list):
            continue

        normalized_entries: list[tuple[str, int]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            card_id = entry.get("card_id")
            count = entry.get("count")
            if not isinstance(card_id, str) or not isinstance(count, int):
                continue
            normalized_entries.append((card_id, count))

        if sum(count for _, count in normalized_entries) != 40:
            continue

        profiles.append(
            DeckProfile(
                deck_id=deck_id,
                label=f"{name} ({deck_id})",
                total_cards=40,
                entries=tuple(normalized_entries),
            )
        )

    if not profiles:
        raise ValueError("No 40-card full decks found in roster file")

    profiles.sort(key=lambda profile: profile.label.casefold())
    return tuple(profiles)


def build_setup_from_market_selection(
    base_setup_path: Path,
    *,
    deck_a: DeckProfile,
    deck_b: DeckProfile,
) -> dict[str, object]:
    """Build setup payload with starter deck and selected combined market decks."""

    base_setup = _read_json_object(base_setup_path)
    starter_deck = base_setup.get("starter_deck")
    market_row_size = base_setup.get("market_row_size")
    if not isinstance(starter_deck, dict) or not isinstance(market_row_size, int):
        raise ValueError("Base setup file must define starter_deck and market_row_size")

    combined_counts: dict[str, int] = {}
    for card_id, count in (*deck_a.entries, *deck_b.entries):
        combined_counts[card_id] = combined_counts.get(card_id, 0) + count

    market_entries = [{"card_id": card_id, "count": count} for card_id, count in combined_counts.items()]
    return {
        "setup_id": f"{deck_a.deck_id}_{deck_b.deck_id}",
        "starter_deck": starter_deck,
        "market_deck": {
            "deck_id": f"market_{deck_a.deck_id}_{deck_b.deck_id}",
            "entries": market_entries,
        },
        "market_row_size": market_row_size,
    }


def create_hotseat_session(
    *,
    board_path: Path,
    card_path: Path,
    setup_path: Path,
    deck_a: DeckProfile,
    deck_b: DeckProfile,
    player_count: int,
    seed: int,
) -> GameSession:
    """Create a game session using selected map, players, and two market decks."""

    board_data = _read_json_object(board_path)
    card_data = _read_json_object(card_path)
    setup_data = build_setup_from_market_selection(setup_path, deck_a=deck_a, deck_b=deck_b)

    definition = build_game_definition_from_dicts(board_data, card_data, setup_data)
    player_ids = [f"p{index}" for index in range(1, player_count + 1)]
    state = build_initial_game_state(
        definition,
        player_ids=player_ids,
        rng=Random(seed),
        shuffle_seed=seed,
    )
    return GameSession(state)


def _read_json_object(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


class GameViewerApp:
    """Interactive board viewer for hotseat play and state inspection."""

    def __init__(
        self,
        root: tk.Tk,
        *,
        board_path: Path,
        layout_path: Path,
        card_path: Path,
        setup_path: Path,
        decks_dir: Path,
        initial_player_count: int,
        seed: int | None,
    ) -> None:
        self.root = root
        self.root.title("Tyrants Game Viewer")

        self.card_path = card_path
        self.base_setup_path = setup_path

        self.map_profiles = discover_map_profiles(
            DATA_DIR,
            default_board_path=board_path,
            default_layout_path=layout_path,
        )
        self.deck_profiles = load_market_deck_profiles(decks_dir)
        self._map_profiles_by_label = {profile.label: profile for profile in self.map_profiles}
        self._deck_profiles_by_label = {profile.label: profile for profile in self.deck_profiles}

        self.package = build_board_package_from_files(board_path=board_path, layout_path=layout_path)
        self._node_names = {n.node_id: n.label for n in self.package.layout.nodes}
        self.session: GameSession | None = None
        self.renderer = GameBoardRenderer()

        self.zoom_level = 1.0
        self._min_zoom = 0.1
        self._max_zoom = 3.0

        default_map_label = next(
            profile.label
            for profile in self.map_profiles
            if profile.board_path == board_path and profile.layout_path == layout_path
        )
        default_deck_a_profile = next(
            (profile for profile in self.deck_profiles if profile.deck_id == "drow"),
            self.deck_profiles[0],
        )
        default_deck_b_profile = next(
            (
                profile
                for profile in self.deck_profiles
                if profile.deck_id == "dragon" and profile.deck_id != default_deck_a_profile.deck_id
            ),
            None,
        )
        if default_deck_b_profile is None:
            default_deck_b_profile = next(
                (profile for profile in self.deck_profiles if profile.deck_id != default_deck_a_profile.deck_id),
                default_deck_a_profile,
            )

        default_deck_a = default_deck_a_profile.label
        default_deck_b = default_deck_b_profile.label

        self.map_var = tk.StringVar(value=default_map_label)
        self.player_count_var = tk.IntVar(value=max(2, min(4, initial_player_count)))
        self.deck_a_var = tk.StringVar(value=default_deck_a)
        self.deck_b_var = tk.StringVar(value=default_deck_b)
        self.seed_var = tk.StringVar(value="1" if seed is None else str(seed))

        self.status_var = tk.StringVar(value="")
        self.market_meta_var = tk.StringVar(value="")
        self.resource_var = tk.StringVar(value="")
        self.vp_breakdown_var = tk.StringVar(value="")
        self.house_guard_var = tk.StringVar(value="")
        self.priestess_var = tk.StringVar(value="")
        self.discard_selection_var = tk.StringVar(value="")
        self.inner_circle_selection_var = tk.StringVar(value="")
        self.trophy_hall_selection_var = tk.StringVar(value="")
        self.devoured_selection_var = tk.StringVar(value="")
        self.inner_circle_meta_var = tk.StringVar(value="")
        self.trophy_hall_meta_var = tk.StringVar(value="")
        self.prompt_var = tk.StringVar(value="")
        self.players_var = tk.StringVar(value="")
        self._hover_popup: tk.Toplevel | None = None
        self.selection_var = tk.StringVar(value="No active filters")
        self.option_var = tk.StringVar(value="")
        self.other_discard_selection_vars: dict[str, tk.StringVar] = {}
        self.other_discard_boxes: dict[str, ttk.Combobox] = {}
        self.other_discard_labels: dict[str, ttk.Label] = {}
        self.other_discards_frame: ttk.Frame | None = None
        self._other_discards_placeholder: ttk.Label | None = None
        self._hover_market_cards: list[CardView] = []
        self._hover_hand_cards: list[CardView] = []
        self._hover_played_cards: list[CardView] = []
        self._hover_market_hitboxes: list[tuple[int, int, int, int, int]] = []

        self._selected_node_id: str | None = None
        self._selected_hand_card_id: str | None = None
        self._selected_played_card_id: str | None = None
        self._selected_market_slot: int | None = None
        self._visible_legal_moves: tuple[LegalMoveView, ...] = ()
        self._hand_card_ids: list[str] = []
        self._played_card_ids: list[str] = []
        self._market_slot_indices: list[int] = []
        self._hand_hitboxes: list[tuple[int, int, int, int, int]] = []
        self._played_hitboxes: list[tuple[int, int, int, int, int]] = []
        self._market_hitboxes: list[tuple[int, int, int, int, int]] = []
        self._map_hitboxes: list[tuple[int, int, int, int, int]] = []
        self._active_card_row: str | None = None
        self._compact_player_rows = False
        self._aberrations_in_market = False
        self._deck_a_label = ""
        self._deck_b_label = ""
        self._market_card_width = MARKET_CARD_WIDTH
        self._market_card_height = MARKET_CARD_HEIGHT
        self._player_card_width = PLAYER_CARD_WIDTH
        self._player_card_height = PLAYER_CARD_HEIGHT
        self._resize_after_id: str | None = None
        self._is_refreshing = False
        self._pending_initial_fit = True

        self._build_ui()
        self.root.bind("<Configure>", self._on_root_configure)
        self._start_new_game()

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=8)
        frame.pack(fill=tk.BOTH, expand=True)

        controls = ttk.Frame(frame)
        controls.pack(fill=tk.X)

        setup_controls = ttk.Frame(controls)
        setup_controls.pack(fill=tk.X)

        ttk.Label(setup_controls, text="Map:").pack(side=tk.LEFT)
        self.map_box = ttk.Combobox(
            setup_controls,
            state="readonly",
            width=20,
            textvariable=self.map_var,
            values=[profile.label for profile in self.map_profiles],
        )
        self.map_box.pack(side=tk.LEFT, padx=(4, 10))

        ttk.Label(setup_controls, text="Players:").pack(side=tk.LEFT)
        self.player_count_spin = ttk.Spinbox(setup_controls, from_=2, to=4, textvariable=self.player_count_var, width=4)
        self.player_count_spin.pack(side=tk.LEFT, padx=(4, 10))

        ttk.Label(setup_controls, text="Deck A:").pack(side=tk.LEFT)
        self.deck_a_box = ttk.Combobox(
            setup_controls,
            state="readonly",
            width=22,
            textvariable=self.deck_a_var,
            values=[profile.label for profile in self.deck_profiles],
        )
        self.deck_a_box.pack(side=tk.LEFT, padx=(4, 10))

        ttk.Label(setup_controls, text="Deck B:").pack(side=tk.LEFT)
        self.deck_b_box = ttk.Combobox(
            setup_controls,
            state="readonly",
            width=22,
            textvariable=self.deck_b_var,
            values=[profile.label for profile in self.deck_profiles],
        )
        self.deck_b_box.pack(side=tk.LEFT, padx=(4, 10))

        ttk.Label(setup_controls, text="Seed (optional):").pack(side=tk.LEFT)
        self.seed_entry = ttk.Entry(setup_controls, textvariable=self.seed_var, width=14)
        self.seed_entry.pack(side=tk.LEFT, padx=(4, 10))

        action_controls = ttk.Frame(controls)
        action_controls.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(action_controls, text="Start New Game", command=self._start_new_game).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(action_controls, text="Refresh", command=self._refresh_view).pack(side=tk.LEFT)
        ttk.Button(action_controls, text="Clear Filters", command=self._clear_filters).pack(side=tk.LEFT, padx=6)
        ttk.Button(action_controls, text="Apply Selected Move", command=self._apply_selected_legal_move).pack(side=tk.LEFT)
        ttk.Button(action_controls, text="Apply First Legal Move", command=self._apply_first_legal_move).pack(side=tk.LEFT, padx=6)
        ttk.Button(action_controls, text="Save Game", command=self._save_game).pack(side=tk.LEFT, padx=(12, 6))
        ttk.Button(action_controls, text="Load Game", command=self._load_game).pack(side=tk.LEFT)

        ttk.Label(action_controls, textvariable=self.status_var, font=("TkFixedFont", 9)).pack(side=tk.RIGHT, padx=6)

        content = ttk.Frame(frame)
        content.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        canvas_frame = ttk.Frame(content)
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        market_frame = ttk.LabelFrame(canvas_frame, text="Market Deck", padding=6)
        market_frame.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(market_frame, textvariable=self.market_meta_var, justify=tk.LEFT, font=("TkFixedFont", 9)).pack(anchor=tk.W)
        devoured_frame = ttk.Frame(market_frame)
        devoured_frame.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(devoured_frame, text="Devoured Cards:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        self.devoured_box = ttk.Combobox(
            devoured_frame,
            state="readonly",
            textvariable=self.devoured_selection_var,
            width=90,
        )
        self.devoured_box.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
        market_row_frame = ttk.Frame(market_frame)
        market_row_frame.pack(fill=tk.X)
        self.market_canvas = tk.Canvas(
            market_row_frame,
            height=MARKET_CARD_HEIGHT + (CARD_ROW_TOP_PAD * 2),
            bg="#f2f5f9",
            highlightthickness=1,
            highlightbackground="#9eb4d0",
            highlightcolor="#3d5f90",
            takefocus=True,
        )
        self.market_canvas.pack(fill=tk.X)
        self.market_scrollbar = ttk.Scrollbar(market_row_frame, orient=tk.HORIZONTAL, command=self.market_canvas.xview)
        self.market_scrollbar.pack(fill=tk.X, pady=(2, 0))
        self.market_canvas.configure(xscrollcommand=self.market_scrollbar.set)
        self.market_canvas.bind("<Button-1>", self._on_market_canvas_click)
        self.market_canvas.bind("<Left>", self._on_market_key_left)
        self.market_canvas.bind("<Right>", self._on_market_key_right)
        self.market_canvas.bind("<Down>", self._on_market_key_down)
        self.market_canvas.bind("<Return>", self._on_market_key_activate)
        self.market_canvas.bind("<space>", self._on_market_key_activate)
        self.market_canvas.bind("<FocusIn>", self._on_market_focus_in)
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
        self.canvas = tk.Canvas(
            map_canvas_row,
            width=min(self.package.layout.canvas.width, MAP_VIEWPORT_MAX_WIDTH),
            height=min(self.package.layout.canvas.height, MAP_VIEWPORT_MAX_HEIGHT),
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
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        bind_canvas_scrolling(self.canvas, self._zoom_in, self._zoom_out)
        self.root.bind("<plus>", lambda _: self._zoom_in())
        self.root.bind("<minus>", lambda _: self._zoom_out())
        self.root.bind("<Control-equal>", lambda _: self._zoom_in())
        self.root.bind("<Control-s>", lambda _: self._save_game())
        self.root.bind("<Control-l>", lambda _: self._load_game())

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
        self._current_player_content_id = self.current_player_canvas.create_window((0, 0), window=bottom_content, anchor=tk.NW)
        self.current_player_canvas.bind("<Configure>", self._on_current_player_canvas_configure)
        bottom_content.bind("<Configure>", self._on_current_player_content_configure)

        ttk.Label(bottom_content, textvariable=self.resource_var, font=("TkFixedFont", 10, "bold")).pack(anchor=tk.W)
        ttk.Label(bottom_content, textvariable=self.vp_breakdown_var, font=("TkFixedFont", 9)).pack(anchor=tk.W, pady=(4, 0))

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
            takefocus=True,
        )
        self.hand_canvas.pack(fill=tk.X)
        self.hand_scrollbar = ttk.Scrollbar(hand_row_frame, orient=tk.HORIZONTAL, command=self.hand_canvas.xview)
        self.hand_scrollbar.pack(fill=tk.X, pady=(2, 0))
        self.hand_canvas.configure(xscrollcommand=self.hand_scrollbar.set)
        self.hand_canvas.bind("<Button-1>", self._on_hand_canvas_click)
        self.hand_canvas.bind("<Double-Button-1>", self._on_hand_canvas_double_click)
        self.hand_canvas.bind("<Left>", self._on_hand_key_left)
        self.hand_canvas.bind("<Right>", self._on_hand_key_right)
        self.hand_canvas.bind("<Up>", self._on_hand_key_up)
        self.hand_canvas.bind("<Return>", self._on_hand_key_activate)
        self.hand_canvas.bind("<space>", self._on_hand_key_activate)
        self.hand_canvas.bind("<FocusIn>", self._on_hand_focus_in)
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
            takefocus=True,
        )
        self.played_canvas.pack(fill=tk.X)
        self.played_scrollbar = ttk.Scrollbar(played_row_frame, orient=tk.HORIZONTAL, command=self.played_canvas.xview)
        self.played_scrollbar.pack(fill=tk.X, pady=(2, 0))
        self.played_canvas.configure(xscrollcommand=self.played_scrollbar.set)
        self.played_canvas.bind("<Button-1>", self._on_played_canvas_click)
        self.played_canvas.bind("<FocusIn>", self._on_played_focus_in)
        self.played_canvas.bind("<Motion>", self._on_played_canvas_hover)
        self.played_canvas.bind("<Leave>", self._on_card_canvas_leave)

        sidebar = ttk.Frame(content, width=360)
        sidebar.pack(side=tk.RIGHT, fill=tk.Y)
        sidebar.pack_propagate(False)

        ttk.Label(sidebar, text="Prompts", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        ttk.Label(sidebar, textvariable=self.prompt_var, wraplength=340, justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 10))

        ttk.Label(sidebar, text="Players", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        ttk.Label(sidebar, textvariable=self.players_var, wraplength=340, justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 10))

        ttk.Label(sidebar, text="Other Player Discards", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        self.other_discards_frame = ttk.Frame(sidebar)
        self.other_discards_frame.pack(fill=tk.X, pady=(0, 10))
        self._other_discards_placeholder = ttk.Label(self.other_discards_frame, text="(none)", justify=tk.LEFT)
        self._other_discards_placeholder.pack(anchor=tk.W)

        ttk.Label(sidebar, text="Generic Choice Options", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        self.option_box = ttk.Combobox(sidebar, state="readonly", textvariable=self.option_var)
        self.option_box.pack(fill=tk.X, pady=(0, 8))
        self.option_box.bind("<<ComboboxSelected>>", self._on_option_selected)

        ttk.Label(sidebar, text="Selection", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        ttk.Label(sidebar, textvariable=self.selection_var, wraplength=340, justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 8))

        ttk.Label(sidebar, text="Legal Moves", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        legal_moves_frame = ttk.Frame(sidebar)
        legal_moves_frame.pack(fill=tk.BOTH, expand=True)
        self.legal_moves_listbox = tk.Listbox(legal_moves_frame, height=12, exportselection=False)
        self.legal_moves_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.legal_moves_scrollbar = ttk.Scrollbar(legal_moves_frame, orient=tk.VERTICAL, command=self.legal_moves_listbox.yview)
        self.legal_moves_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.legal_moves_listbox.configure(yscrollcommand=self.legal_moves_scrollbar.set)
        self.legal_moves_listbox.bind("<Double-Button-1>", self._on_legal_move_double_click)

    def _start_new_game(self) -> None:
        map_profile = self._map_profiles_by_label.get(self.map_var.get())
        deck_a = self._deck_profiles_by_label.get(self.deck_a_var.get())
        deck_b = self._deck_profiles_by_label.get(self.deck_b_var.get())
        if map_profile is None or deck_a is None or deck_b is None:
            messagebox.showerror("Invalid setup", "Please select a valid map and market decks.")
            return
        if deck_a.deck_id == deck_b.deck_id and len(self.deck_profiles) > 1:
            messagebox.showerror("Invalid setup", "Choose two different 40-card market decks.")
            return

        try:
            player_count = max(2, min(4, int(self.player_count_var.get())))
            seed = _resolve_seed_input(self.seed_var.get())
            self._aberrations_in_market = (
                deck_a.deck_id == ABERRATIONS_DECK_ID or deck_b.deck_id == ABERRATIONS_DECK_ID
            )
            self._deck_a_label = deck_a.label
            self._deck_b_label = deck_b.label
        except (TypeError, ValueError, tk.TclError):
            messagebox.showerror("Invalid setup", "Players must be valid integers, and seed (if set) must be a valid integer.")
            return

        try:
            self.package = build_board_package_from_files(
                board_path=map_profile.board_path,
                layout_path=map_profile.layout_path,
            )
            self._node_names = {n.node_id: n.label for n in self.package.layout.nodes}
            self.canvas.configure(
                width=min(self.package.layout.canvas.width, MAP_VIEWPORT_MAX_WIDTH),
                height=min(self.package.layout.canvas.height, MAP_VIEWPORT_MAX_HEIGHT),
            )
            self.session = create_hotseat_session(
                board_path=map_profile.board_path,
                card_path=self.card_path,
                setup_path=self.base_setup_path,
                deck_a=deck_a,
                deck_b=deck_b,
                player_count=player_count,
                seed=seed,
            )
            self._clear_filters()
            self._apply_responsive_layout()
            self._refresh_view()
            self._auto_fit_zoom()
        except Exception as error:
            messagebox.showerror("Failed to start game", str(error))

    def _save_game(self) -> None:
        if self.session is None:
            messagebox.showinfo("No Game", "Start a game before saving.")
            return

        path = filedialog.asksaveasfilename(
            title="Save Game Scenario",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=ROOT_DIR / "data" / "scenarios",
        )
        if not path:
            return

        try:
            move_count = self.session.move_count
            is_terminal = self.session.is_terminal()
            save_game_state(
                self.session.state,
                Path(path),
                scenario_id=Path(path).stem,
                description=f"Saved at round {self.session.state.round_number}, {move_count} moves",
                tags=["saved", "manual"],
                move_count=move_count,
                is_terminal=is_terminal,
            )
            messagebox.showinfo("Saved", f"Game saved to:\n{path}")
        except Exception as error:
            messagebox.showerror("Save Failed", str(error))

    def _load_game(self) -> None:
        path = filedialog.askopenfilename(
            title="Load Game Scenario",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=ROOT_DIR / "data" / "scenarios",
        )
        if not path:
            return

        try:
            self.session = GameSession.from_scenario_file(Path(path))
            self._derive_market_deck_metadata(self.session.state)
            self._rebuild_package_for_loaded_state(self.session.state)
            self._clear_filters()
            self._apply_responsive_layout()
            self._refresh_view()
            self._auto_fit_zoom()
        except Exception as error:
            messagebox.showerror("Load Failed", str(error))

    def _rebuild_package_for_loaded_state(self, state: GameState) -> None:
        """Rebuild self.package and self._node_names to match the loaded state's board."""
        board_def = state.definition.board
        board_node_ids = {n.node_id for n in board_def.nodes}
        layout_def = None

        for profile in self.map_profiles:
            try:
                layout_data = _read_json_object(profile.layout_path)
                if layout_data.get("board_id") != board_def.board_id:
                    continue
                layout_node_ids = {n["node_id"] for n in layout_data.get("nodes", ())}
                if layout_node_ids != board_node_ids:
                    continue
                layout_def = BoardLayoutDefinition.model_validate(layout_data)
                break
            except Exception:
                continue

        if layout_def is None:
            layout_def = make_default_layout(board_def)

        self.package = BoardPackageDefinition(board=board_def, layout=layout_def)
        self._node_names = {n.node_id: n.label for n in self.package.layout.nodes}
        self.canvas.configure(
            width=min(self.package.layout.canvas.width, MAP_VIEWPORT_MAX_WIDTH),
            height=min(self.package.layout.canvas.height, MAP_VIEWPORT_MAX_HEIGHT),
        )

    def _derive_market_deck_metadata(self, state: GameState) -> None:
        """Derive market deck labels and aberrations flag from loaded state."""
        market_deck_id = state.definition.setup.market_deck.deck_id

        if market_deck_id.startswith("market_"):
            remaining = market_deck_id[len("market_"):]
        else:
            remaining = market_deck_id

        profile_ids = {p.deck_id: p.label for p in self.deck_profiles}
        sorted_ids = sorted(profile_ids.keys(), key=len, reverse=True)

        deck_a_id = ""
        deck_b_id = ""
        deck_a_label = ""
        deck_b_label = ""

        for did in sorted_ids:
            if remaining.startswith(did):
                deck_a_id = did
                deck_a_label = profile_ids[did]
                remaining = remaining[len(did):]
                if remaining.startswith("_"):
                    remaining = remaining[1:]
                break

        for did in sorted_ids:
            if remaining.startswith(did):
                deck_b_id = did
                deck_b_label = profile_ids[did]
                break

        self._deck_a_label = deck_a_label or deck_a_id
        self._deck_b_label = deck_b_label or deck_b_id
        self._aberrations_in_market = (
            deck_a_id == ABERRATIONS_DECK_ID or deck_b_id == ABERRATIONS_DECK_ID
        )

    def _refresh_view(self) -> None:
        if self.session is None:
            return

        self._is_refreshing = True
        try:
            self._apply_responsive_layout()
            view = build_game_view(self.session, node_names=self._node_names)
            self.renderer.redraw(
                self.canvas, self.package, view,
                highlighted_node_id=self._selected_node_id,
                scale=self.zoom_level,
            )
            scaled_w = self.package.layout.canvas.width * self.zoom_level
            scaled_h = self.package.layout.canvas.height * self.zoom_level
            self.canvas.configure(scrollregion=(0, 0, scaled_w, scaled_h))

            state = self.session.state
            current_player = state.players[state.current_player_id]
            cards_by_id = {card.card_id: card for card in state.definition.catalog.cards}

            self.status_var.set(
                f"Round {view.round_number} | Phase {view.phase} | Current {view.current_player_id}"
            )
            self.resource_var.set(
                f"Power: {view.resource_power:>3}    Influence: {view.resource_influence:>3}"
                f"  |  Sites: {view.current_player_controlled_sites} controlled, {view.current_player_total_control_sites} total"
                f"  |  Hand: {_format_aspect_breakdown(_compute_aspect_focus(view.hand))}"
                f"  |  Played: {_format_aspect_breakdown(_compute_aspect_focus(view.current_player_played))}"
            )
            self._set_vp_breakdown(state, current_player)
            self.prompt_var.set("\n".join(view.prompts))
            deck_a_label = getattr(self, "_deck_a_label", "?")
            deck_b_label = getattr(self, "_deck_b_label", "?")
            self.market_meta_var.set(
                f"Deck A: {deck_a_label}    Deck B: {deck_b_label}    |    "
                f"Market deck: {len(view.market_row):>1} visible    Deck remaining: {view.market_deck_count:>3}    "
                f"Discard: {view.market_discard_count:>3}"
            )

            player_lines = [
                (
                    f"{summary.player_id}{' *' if summary.is_current else ''}: "
                    f"hand {summary.hand_count}, deck {summary.deck_count}, discard {summary.discard_count}, "
                    f"played {summary.played_count}, trophies {summary.trophy_hall_count}, "
                    f"barracks {summary.barracks}, spies {summary.spies_available}, vp {summary.vp_tokens}"
                )
                for summary in view.player_summaries
            ]
            self.players_var.set("\n".join(player_lines))

            self._sync_market_row(view)
            self._sync_hand_row(view)
            self._sync_played_row(view)
            self._sync_option_box(view)

            self.house_guard_var.set(
                self._starter_pile_summary(
                    current_player,
                    HOUSE_GUARD_CARD_ID,
                    cards_by_id.get(HOUSE_GUARD_CARD_ID),
                )
            )
            self.priestess_var.set(
                self._starter_pile_summary(
                    current_player,
                    PRIESTESS_CARD_ID,
                    cards_by_id.get(PRIESTESS_CARD_ID),
                )
            )

            discard_options = format_ordered_card_options(current_player.discard_pile, cards_by_id)
            self.discard_box["values"] = discard_options
            if self.discard_selection_var.get() not in discard_options:
                self.discard_selection_var.set(discard_options[0])

            devoured_options = format_ordered_card_options(state.devour_pile, cards_by_id)
            self.devoured_box["values"] = devoured_options
            if self.devoured_selection_var.get() not in devoured_options:
                self.devoured_selection_var.set(devoured_options[0])

            self._sync_other_player_discard_boxes(state, cards_by_id)

            inner_circle_options = format_ordered_card_options(
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

            trophy_hall_options = format_trophy_hall_options(view.current_player_trophy_hall)
            self.trophy_hall_box["values"] = trophy_hall_options
            if self.trophy_hall_selection_var.get() not in trophy_hall_options:
                self.trophy_hall_selection_var.set(trophy_hall_options[0])
            self.trophy_hall_meta_var.set(f"Captured Trophies: {len(view.current_player_trophy_hall):>2}")

            self._visible_legal_moves = filter_legal_moves(
                view.legal_moves,
                hand_card_id=self._selected_hand_card_id,
                played_card_id=self._selected_played_card_id,
                market_slot=self._selected_market_slot,
                node_id=self._selected_node_id,
                option_id=self.option_var.get() or None,
            )
            if not self._visible_legal_moves:
                self._visible_legal_moves = view.legal_moves

            self.legal_moves_listbox.delete(0, tk.END)
            for index, legal_move in enumerate(self._visible_legal_moves):
                self.legal_moves_listbox.insert(tk.END, f"{index + 1}. {legal_move.label}")

            if self._visible_legal_moves:
                self.legal_moves_listbox.selection_set(0)

            selections: list[str] = []
            if self._selected_node_id is not None:
                selections.append(f"node={self._selected_node_id}")
            if self._selected_hand_card_id is not None:
                hand_name = cards_by_id.get(self._selected_hand_card_id)
                selections.append(f"hand={hand_name.name if hand_name is not None else 'Unknown Card'}")
            if self._selected_played_card_id is not None:
                played_name = cards_by_id.get(self._selected_played_card_id)
                selections.append(f"played={played_name.name if played_name is not None else 'Unknown Card'}")
            if self._selected_market_slot is not None:
                selections.append(f"market_slot={self._describe_market_slot(self._selected_market_slot)}")
            if self.option_var.get():
                selections.append(f"option={self.option_var.get()}")
            self.selection_var.set("; ".join(selections) if selections else "No active filters")
            self._update_card_row_focus_styles()
        finally:
            self._is_refreshing = False

    def _sync_other_player_discard_boxes(self, state: Any, cards_by_id: dict[str, Any]) -> None:
        if self.other_discards_frame is None:
            return

        other_player_ids = [player_id for player_id in state.turn_order if player_id != state.current_player_id]
        previous_player_ids = set(self.other_discard_boxes)

        for player_id in other_player_ids:
            if player_id not in self.other_discard_boxes:
                row = ttk.Frame(self.other_discards_frame)
                row.pack(fill=tk.X, pady=(0, 4))

                label = ttk.Label(row, text=f"{player_id}:", width=6)
                label.pack(side=tk.LEFT)

                selection_var = tk.StringVar(value="(empty)")
                box = ttk.Combobox(row, state="readonly", textvariable=selection_var, width=42)
                box.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))

                self.other_discard_labels[player_id] = label
                self.other_discard_selection_vars[player_id] = selection_var
                self.other_discard_boxes[player_id] = box

            label = self.other_discard_labels[player_id]
            box = self.other_discard_boxes[player_id]
            selection_var = self.other_discard_selection_vars[player_id]

            # Keep row order aligned with turn order as the active player rotates.
            row = box.master
            row.pack_forget()
            row.pack(fill=tk.X, pady=(0, 4))

            label.configure(text=f"{player_id}:")
            options = format_discard_pile_options(state.players[player_id].discard_pile, cards_by_id)
            box["values"] = options
            if selection_var.get() not in options:
                selection_var.set(options[0])

        for player_id in previous_player_ids - set(other_player_ids):
            box = self.other_discard_boxes.pop(player_id)
            self.other_discard_selection_vars.pop(player_id, None)
            self.other_discard_labels.pop(player_id, None)
            box.master.destroy()

        if self._other_discards_placeholder is not None:
            if other_player_ids:
                self._other_discards_placeholder.pack_forget()
            else:
                self._other_discards_placeholder.pack(anchor=tk.W)

    def _sync_market_row(
        self,
        view: GameView,
    ) -> None:
        state = self.session.state if self.session is not None else None
        cards_by_id: dict[str, Any] = {}
        if state is not None:
            cards_by_id = {card.card_id: card for card in state.definition.catalog.cards}

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

        self._market_slot_indices = [slot for slot in top_slot_to_market_slot if slot is not None]
        if self._selected_market_slot not in self._market_slot_indices:
            self._selected_market_slot = None

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

        selected_top_index = -1
        if self._selected_market_slot is not None:
            for top_index, market_slot in enumerate(top_slot_to_market_slot):
                if market_slot == self._selected_market_slot:
                    selected_top_index = top_index
                    break

        top_hitboxes = self._draw_card_row(
            self.market_canvas,
            tuple(top_cards),
            selected_index=selected_top_index,
            selected_has_focus=self._active_card_row == "market",
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

    def _sync_played_row(
        self,
        view: GameView,
    ) -> None:
        self._hover_played_cards = list(view.current_player_played)
        self._played_card_ids = [card.card_id for card in view.current_player_played]
        if self._selected_played_card_id not in self._played_card_ids:
            self._selected_played_card_id = None

        selected_played_index = -1
        if self._selected_played_card_id is not None:
            selected_played_index = self._played_card_ids.index(self._selected_played_card_id)

        self._played_hitboxes = self._draw_card_row(
            self.played_canvas,
            view.current_player_played,
            selected_index=selected_played_index,
            selected_has_focus=self._active_card_row == "played",
            compact=self._compact_player_rows,
            empty_label="No cards played this phase",
        )

    def _sync_hand_row(
        self,
        view: GameView,
    ) -> None:
        self._hover_hand_cards = list(view.hand)
        self._hand_card_ids = [card.card_id for card in view.hand]
        if self._selected_hand_card_id not in self._hand_card_ids:
            self._selected_hand_card_id = None

        selected_hand_index = -1
        if self._selected_hand_card_id is not None:
            selected_hand_index = self._hand_card_ids.index(self._selected_hand_card_id)

        self._hand_hitboxes = self._draw_card_row(
            self.hand_canvas,
            view.hand,
            selected_index=selected_hand_index,
            selected_has_focus=self._active_card_row == "hand",
            compact=self._compact_player_rows,
        )

    def _draw_card_row(
        self,
        canvas: tk.Canvas,
        cards: tuple[CardView, ...],
        *,
        selected_index: int = -1,
        selected_has_focus: bool = False,
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

            is_selected = index == selected_index
            if is_selected:
                fill = "#dcecff"
            elif index in tint_colors_map:
                fill = tint_colors_map[index]
            else:
                fill = "#ffffff"

            if is_selected and selected_has_focus:
                outline = "#224f95"
                line_width = 2
            elif is_selected:
                outline = "#4d76b3"
                line_width = 2
            else:
                outline = "#9eb4d0"
                line_width = 1
            canvas.create_rectangle(x0, y0, x1, y1, fill=fill, outline=outline, width=line_width)

            if is_selected and selected_has_focus:
                canvas.create_rectangle(x0 + 3, y0 + 3, x0 + 13, y0 + 13, fill="#224f95", outline="")

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

    def _sync_option_box(self, view: GameView) -> None:
        option_ids = sorted(
            {
                legal_move.move.option_id
                for legal_move in view.legal_moves
                if isinstance(legal_move.move, ResolveGenericChoiceMove)
                and legal_move.move.option_id is not None
            }
        )
        self.option_box["values"] = [""] + option_ids
        if self.option_var.get() not in {"", *option_ids}:
            self.option_var.set("")

    def _apply_first_legal_move(self) -> None:
        if self.session is None:
            return
        view = build_game_view(self.session, node_names=self._node_names)
        if not view.legal_moves:
            return
        self.session.submit_move(view.legal_moves[0].move)
        self._clear_filters()
        self._refresh_view()

    def _apply_selected_legal_move(self) -> None:
        if self.session is None:
            return
        if not self._visible_legal_moves:
            return
        selected_indices = self.legal_moves_listbox.curselection()
        selected_index = selected_indices[0] if selected_indices else 0
        selected_index = max(0, min(selected_index, len(self._visible_legal_moves) - 1))
        self.session.submit_move(self._visible_legal_moves[selected_index].move)
        self._clear_filters()
        self._refresh_view()

    def _clear_filters(self) -> None:
        self._selected_node_id = None
        self._selected_hand_card_id = None
        self._selected_played_card_id = None
        self._selected_market_slot = None
        self.option_var.set("")

    def _on_root_configure(self, event: tk.Event[tk.Tk]) -> None:
        if event.widget is not self.root:
            return
        if self._resize_after_id is not None:
            self.root.after_cancel(self._resize_after_id)
        self._resize_after_id = self.root.after(60, self._on_resized)

    def _on_current_player_canvas_configure(self, event: tk.Event[tk.Canvas]) -> None:
        if not hasattr(self, "_current_player_content_id"):
            return
        self.current_player_canvas.itemconfigure(self._current_player_content_id, width=event.width)

    def _on_current_player_content_configure(self, _event: tk.Event[ttk.Frame]) -> None:
        self.current_player_canvas.configure(scrollregion=self.current_player_canvas.bbox("all"))

    def _on_resized(self) -> None:
        if self._pending_initial_fit:
            self._pending_initial_fit = False
            self._apply_responsive_layout()
            self._auto_fit_zoom()
            return
        self._apply_responsive_layout()
        if self.session is not None and not self._is_refreshing:
            self._refresh_view()

    def _apply_responsive_layout(self) -> None:
        self._resize_after_id = None
        if not hasattr(self, "canvas"):
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

        if self.session is None:
            return

        # Reserve enough vertical room for both current-player card rows.
        map_reserved_height = 360 + (player_row_height * 2)
        map_target_height = root_height - map_reserved_height
        map_target_width = root_width - 520
        map_height = max(1, min(self.package.layout.canvas.height, map_target_height))
        map_width = max(560, min(self.package.layout.canvas.width, map_target_width, MAP_VIEWPORT_MAX_WIDTH))
        self.canvas.configure(
            width=map_width,
            height=map_height,
            scrollregion=(0, 0, self.package.layout.canvas.width * self.zoom_level, self.package.layout.canvas.height * self.zoom_level),
        )

    def _auto_fit_zoom(self) -> None:
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
        self._refresh_view()

    def _zoom_in(self) -> None:
        self._change_zoom(self.zoom_level * 1.2)

    def _zoom_out(self) -> None:
        self._change_zoom(self.zoom_level / 1.2)

    def _zoom_reset(self) -> None:
        self._change_zoom(1.0)

    def _change_zoom(self, new_zoom: float) -> None:
        new_zoom = max(self._min_zoom, min(self._max_zoom, new_zoom))
        if abs(new_zoom - self.zoom_level) < 0.001:
            return
        self.zoom_level = new_zoom
        self._zoom_status_var.set(f"{self.zoom_level:.0%}")
        self._refresh_view()

    def _on_canvas_click(self, event: tk.Event[tk.Canvas]) -> None:
        if self._is_refreshing:
            return
        selected_node = self._node_id_at_point(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        self._selected_node_id = selected_node
        self._refresh_view()

    def _on_hand_canvas_click(self, event: tk.Event[tk.Canvas]) -> None:
        if self._is_refreshing:
            return
        self._set_active_card_row("hand")
        self.hand_canvas.focus_set()
        selected_index = self._card_index_at_point(self.hand_canvas.canvasx(event.x), self.hand_canvas.canvasy(event.y), self._hand_hitboxes)
        if selected_index is None:
            self._selected_hand_card_id = None
        elif selected_index < len(self._hand_card_ids):
            self._selected_hand_card_id = self._hand_card_ids[selected_index]
        self._refresh_view()

    def _on_hand_canvas_double_click(self, event: tk.Event[tk.Canvas]) -> None:
        if self._is_refreshing or self.session is None:
            return

        self._set_active_card_row("hand")
        self.hand_canvas.focus_set()
        selected_index = self._card_index_at_point(self.hand_canvas.canvasx(event.x), self.hand_canvas.canvasy(event.y), self._hand_hitboxes)
        if selected_index is None or selected_index >= len(self._hand_card_ids):
            return

        selected_card_id = self._hand_card_ids[selected_index]
        view = build_game_view(self.session, node_names=self._node_names)
        for legal_move in view.legal_moves:
            if isinstance(legal_move.move, PlayCardMove) and legal_move.move.card_id == selected_card_id:
                self.session.submit_move(legal_move.move)
                self._clear_filters()
                self._refresh_view()
                return

    def _on_played_canvas_click(self, event: tk.Event[tk.Canvas]) -> None:
        if self._is_refreshing:
            return
        self._set_active_card_row("played")
        self.played_canvas.focus_set()
        selected_index = self._card_index_at_point(
            self.played_canvas.canvasx(event.x),
            self.played_canvas.canvasy(event.y),
            self._played_hitboxes,
        )
        if selected_index is None:
            self._selected_played_card_id = None
        elif selected_index < len(self._played_card_ids):
            self._selected_played_card_id = self._played_card_ids[selected_index]
        self._refresh_view()

    def _on_market_canvas_click(self, event: tk.Event[tk.Canvas]) -> None:
        if self._is_refreshing:
            return
        self._set_active_card_row("market")
        self.market_canvas.focus_set()
        selected_index = self._card_index_at_point(self.market_canvas.canvasx(event.x), self.market_canvas.canvasy(event.y), self._market_hitboxes)
        self._selected_market_slot = selected_index
        self._refresh_view()

    def _on_market_canvas_hover(self, event: tk.Event[tk.Canvas]) -> None:
        if self._is_refreshing:
            return
        selected_index = self._card_index_at_point(
            self.market_canvas.canvasx(event.x),
            self.market_canvas.canvasy(event.y),
            self._hover_market_hitboxes,
        )
        self._set_hover_card("Market", self._hover_market_cards, selected_index, event.x_root, event.y_root)

    def _on_hand_canvas_hover(self, event: tk.Event[tk.Canvas]) -> None:
        if self._is_refreshing:
            return
        selected_index = self._card_index_at_point(
            self.hand_canvas.canvasx(event.x),
            self.hand_canvas.canvasy(event.y),
            self._hand_hitboxes,
        )
        self._set_hover_card("Hand", self._hover_hand_cards, selected_index, event.x_root, event.y_root)

    def _on_played_canvas_hover(self, event: tk.Event[tk.Canvas]) -> None:
        if self._is_refreshing:
            return
        selected_index = self._card_index_at_point(
            self.played_canvas.canvasx(event.x),
            self.played_canvas.canvasy(event.y),
            self._played_hitboxes,
        )
        self._set_hover_card("Played", self._hover_played_cards, selected_index, event.x_root, event.y_root)

    def _on_card_canvas_leave(self, _event: tk.Event[tk.Canvas]) -> None:
        self._hide_card_popup()

    def _set_hover_card(self, zone_name: str, cards: Sequence[CardView], index: int | None, x_root: int = 0, y_root: int = 0) -> None:
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
        detail_text = format_card_hover_details(card)
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

    def _on_market_key_left(self, _event: tk.Event[tk.Canvas]) -> str | None:
        if not self._market_slot_indices:
            return "break"
        if self._selected_market_slot is None:
            self._selected_market_slot = self._market_slot_indices[-1]
        else:
            current_index = self._market_slot_indices.index(self._selected_market_slot)
            self._selected_market_slot = self._market_slot_indices[max(0, current_index - 1)]
        self._set_active_card_row("market")
        self._refresh_view()
        return "break"

    def _on_market_key_right(self, _event: tk.Event[tk.Canvas]) -> str | None:
        if not self._market_slot_indices:
            return "break"
        if self._selected_market_slot is None:
            self._selected_market_slot = self._market_slot_indices[0]
        else:
            current_index = self._market_slot_indices.index(self._selected_market_slot)
            self._selected_market_slot = self._market_slot_indices[min(len(self._market_slot_indices) - 1, current_index + 1)]
        self._set_active_card_row("market")
        self._refresh_view()
        return "break"

    def _describe_market_slot(self, market_slot: int) -> str:
        if market_slot == HOUSE_GUARD_RECRUIT_SLOT:
            return "House Guard Stack"
        if market_slot == PRIESTESS_RECRUIT_SLOT:
            return "Priestess of Lolth Stack"
        if market_slot == INSANE_OUTCAST_RECRUIT_SLOT:
            return "Insane Outcast Stack"
        return str(market_slot + 1)

    def _on_market_key_down(self, _event: tk.Event[tk.Canvas]) -> str | None:
        self._set_active_card_row("hand")
        self.hand_canvas.focus_set()
        self._refresh_view()
        return "break"

    def _on_market_key_activate(self, _event: tk.Event[tk.Canvas]) -> str | None:
        self._apply_selected_legal_move()
        return "break"

    def _on_hand_key_left(self, _event: tk.Event[tk.Canvas]) -> str | None:
        if not self._hand_card_ids:
            return "break"
        if self._selected_hand_card_id is None:
            selected_index = len(self._hand_card_ids) - 1
        else:
            selected_index = self._hand_card_ids.index(self._selected_hand_card_id)
            selected_index = max(0, selected_index - 1)
        self._selected_hand_card_id = self._hand_card_ids[selected_index]
        self._set_active_card_row("hand")
        self._refresh_view()
        return "break"

    def _on_hand_key_right(self, _event: tk.Event[tk.Canvas]) -> str | None:
        if not self._hand_card_ids:
            return "break"
        if self._selected_hand_card_id is None:
            selected_index = 0
        else:
            selected_index = self._hand_card_ids.index(self._selected_hand_card_id)
            selected_index = min(len(self._hand_card_ids) - 1, selected_index + 1)
        self._selected_hand_card_id = self._hand_card_ids[selected_index]
        self._set_active_card_row("hand")
        self._refresh_view()
        return "break"

    def _on_hand_key_up(self, _event: tk.Event[tk.Canvas]) -> str | None:
        self._set_active_card_row("market")
        self.market_canvas.focus_set()
        self._refresh_view()
        return "break"

    def _on_hand_key_activate(self, _event: tk.Event[tk.Canvas]) -> str | None:
        self._apply_selected_legal_move()
        return "break"

    def _on_market_focus_in(self, _event: tk.Event[tk.Canvas]) -> None:
        self._set_active_card_row("market")

    def _on_hand_focus_in(self, _event: tk.Event[tk.Canvas]) -> None:
        self._set_active_card_row("hand")

    def _on_played_focus_in(self, _event: tk.Event[tk.Canvas]) -> None:
        self._set_active_card_row("played")

    def _set_active_card_row(self, row: str | None) -> None:
        self._active_card_row = row
        self._update_card_row_focus_styles()

    def _update_card_row_focus_styles(self) -> None:
        if self._active_card_row == "market":
            self.market_canvas.configure(highlightthickness=2, highlightbackground="#3d5f90")
            self.hand_canvas.configure(highlightthickness=1, highlightbackground="#9eb4d0")
            self.played_canvas.configure(highlightthickness=1, highlightbackground="#9eb4d0")
        elif self._active_card_row == "hand":
            self.market_canvas.configure(highlightthickness=1, highlightbackground="#9eb4d0")
            self.hand_canvas.configure(highlightthickness=2, highlightbackground="#3d5f90")
            self.played_canvas.configure(highlightthickness=1, highlightbackground="#9eb4d0")
        elif self._active_card_row == "played":
            self.market_canvas.configure(highlightthickness=1, highlightbackground="#9eb4d0")
            self.hand_canvas.configure(highlightthickness=1, highlightbackground="#9eb4d0")
            self.played_canvas.configure(highlightthickness=2, highlightbackground="#3d5f90")
        else:
            self.market_canvas.configure(highlightthickness=1, highlightbackground="#9eb4d0")
            self.hand_canvas.configure(highlightthickness=1, highlightbackground="#9eb4d0")
            self.played_canvas.configure(highlightthickness=1, highlightbackground="#9eb4d0")

    def _card_view_from_definition(self, card_definition: Any | None, fallback_card_id: str) -> CardView:
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

    def _set_vp_breakdown(self, state: Any, current_player: Any) -> None:
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
        deck_zone_cards = current_player.deck + current_player.hand + current_player.discard_pile
        deck_vp = _cards_vp(deck_zone_cards, card_index_lookup, "deck_vp")
        inner_circle_vp = _cards_vp(current_player.inner_circle, card_index_lookup, "inner_circle_vp")

        running_score = current_player.score
        total_vp = running_score + control_vp + total_control_vp_per_turn + trophy_vp + token_vp + deck_vp + inner_circle_vp

        self.vp_breakdown_var.set(
            f"Score: {running_score:>2} | Controlled sites: {control_vp:>2} | "
            f"Total Control VP/turn: {total_control_vp_per_turn:>2} | "

            f"Trophy: {trophy_vp:>2} | VP tokens: {token_vp:>2} | Deck VP: {deck_vp:>2} | "
            f"Inner Circle VP: {inner_circle_vp:>2} | Total: {total_vp:>2}"
        )

    def _starter_pile_summary(self, player: Any, card_id: str, card_definition: Any | None = None) -> str:
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

    def _on_option_selected(self, _event: tk.Event[ttk.Combobox]) -> None:
        if self._is_refreshing:
            return
        self._refresh_view()

    def _on_legal_move_double_click(self, _event: tk.Event[tk.Listbox]) -> None:
        self._apply_selected_legal_move()

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

    def _node_id_at_point(self, x: float, y: float) -> str | None:
        world_x = x / self.zoom_level
        world_y = y / self.zoom_level
        for node in self.package.layout.nodes:
            if node.bounds is not None:
                left = node.bounds.x
                top = node.bounds.y
                right = left + node.bounds.width
                bottom = top + node.bounds.height
                if left <= world_x <= right and top <= world_y <= bottom:
                    return node.node_id
                continue

            dx = node.center.x - world_x
            dy = node.center.y - world_y
            if (dx * dx) + (dy * dy) <= 16 * 16:
                return node.node_id

        return None


def _parse_player_ids(raw_player_ids: str) -> list[str]:
    player_ids = [player_id.strip() for player_id in raw_player_ids.split(",") if player_id.strip()]
    if not player_ids:
        raise ValueError("At least one player id is required")
    return player_ids


def main() -> None:
    """Run the interactive Tk gameplay viewer."""

    parser = argparse.ArgumentParser(description="Run the Tyrants interactive hotseat viewer")
    parser.add_argument("--players", default="p1,p2", help="Comma-separated player ids")
    parser.add_argument("--seed", type=int, default=None, help="Optional RNG seed for setup")
    parser.add_argument("--board-path", type=Path, default=DEFAULT_BOARD_PATH)
    parser.add_argument("--layout-path", type=Path, default=DEFAULT_LAYOUT_PATH)
    parser.add_argument("--card-path", type=Path, default=DEFAULT_CARD_PATH)
    parser.add_argument("--setup-path", type=Path, default=DEFAULT_SETUP_PATH)
    parser.add_argument("--decks-dir", type=Path, default=DECKS_DIR)
    args = parser.parse_args()

    root = tk.Tk()
    root.withdraw()
    try:
        GameViewerApp(
            root,
            board_path=args.board_path,
            layout_path=args.layout_path,
            card_path=args.card_path,
            setup_path=args.setup_path,
            decks_dir=args.decks_dir,
            initial_player_count=len(_parse_player_ids(args.players)),
            seed=args.seed,
        )
    except Exception as exc:
        messagebox.showerror(
            "Failed to start Game Viewer",
            str(exc),
        )
        root.destroy()
        raise
    root.deiconify()
    root.mainloop()


if __name__ == "__main__":
    main()
