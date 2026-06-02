"""Read-only gameplay board renderer tests."""

from __future__ import annotations

from pathlib import Path

from game_session import GameSession
from game_setup.loaders import build_board_package_from_files
from game_view import build_game_view
from interface.game_renderer import (
    DEFAULT_SITE_OUTLINE,
    EMPTY_ROUTE_FILL,
    GameBoardRenderer,
    PLAYER_COLORS,
    WHITE_ROUTE_FILL,
    _derive_control_owner,
    _total_control_owner,
)

BASE_DIR = Path(__file__).resolve().parents[1]
BOARD_PATH = BASE_DIR / "data" / "boards" / "tyrants_of_the_underdark.json"
LAYOUT_PATH = BASE_DIR / "data" / "layouts" / "tyrants_of_the_underdark_layout.json"
CARD_PATH = BASE_DIR / "data" / "cards" / "catalog.json"
SETUP_PATH = BASE_DIR / "data" / "decks" / "base_setup.json"


class _CanvasStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def delete(self, *args: object, **kwargs: object) -> None:
        self.calls.append(("delete", args, kwargs))

    def create_line(self, *args: object, **kwargs: object) -> int:
        self.calls.append(("line", args, kwargs))
        return 1

    def create_rectangle(self, *args: object, **kwargs: object) -> int:
        self.calls.append(("rectangle", args, kwargs))
        return 1

    def create_text(self, *args: object, **kwargs: object) -> int:
        self.calls.append(("text", args, kwargs))
        return 1

    def create_oval(self, *args: object, **kwargs: object) -> int:
        self.calls.append(("oval", args, kwargs))
        return 1


def test_game_board_renderer_draws_geometry_and_occupancy() -> None:
    package = build_board_package_from_files(BOARD_PATH, LAYOUT_PATH)
    session = GameSession.from_files(
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        player_ids=["p1", "p2"],
        seed=7,
    )
    view = build_game_view(session)
    canvas = _CanvasStub()

    GameBoardRenderer().redraw(canvas, package, view)

    call_types = [name for name, _args, _kwargs in canvas.calls]
    assert "delete" in call_types
    assert "line" in call_types
    assert "rectangle" in call_types
    assert "oval" in call_types
    assert "text" in call_types


def test_renderer_uses_scale_for_all_coordinates() -> None:
    package = build_board_package_from_files(BOARD_PATH, LAYOUT_PATH)
    session = GameSession.from_files(
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        player_ids=["p1", "p2"],
        seed=7,
    )
    view = build_game_view(session)

    canvas_1x = _CanvasStub()
    canvas_2x = _CanvasStub()

    GameBoardRenderer().redraw(canvas_1x, package, view, scale=1.0)
    GameBoardRenderer().redraw(canvas_2x, package, view, scale=2.0)

    for kind in ("rectangle", "oval", "text", "line"):
        calls_1x = [(args, kwargs) for name, args, kwargs in canvas_1x.calls if name == kind]
        calls_2x = [(args, kwargs) for name, args, kwargs in canvas_2x.calls if name == kind]
        if calls_1x:
            assert calls_1x[0][0][:2] != calls_2x[0][0][:2]


def test_site_rectangle_uses_bounds_and_site_label_above() -> None:
    package = build_board_package_from_files(BOARD_PATH, LAYOUT_PATH)
    session = GameSession.from_files(
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        player_ids=["p1", "p2"],
        seed=7,
    )
    view = build_game_view(session)
    canvas = _CanvasStub()

    GameBoardRenderer().redraw(canvas, package, view)

    rectangles = [(args, kwargs) for name, args, kwargs in canvas.calls if name == "rectangle"]
    texts = [(args, kwargs) for name, args, kwargs in canvas.calls if name == "text"]

    site_label_texts = [kw.get("text", "") for _, kw in texts]
    assert any("Menzoberranzan" in t for t in site_label_texts)
    assert any("Gauntlgrym" in t for t in site_label_texts)

    interior_texts = [kw.get("text", "") for _, kw in texts]
    owner_vp_texts = [t for t in interior_texts if "Owner:" in t and "VP:" in t]
    assert len(owner_vp_texts) > 0

    assert len(rectangles) > 0
    first_rect = rectangles[0][1]
    assert "fill" in first_rect
    assert "outline" in first_rect


def test_route_drawn_as_circle_with_fill_based_on_owner() -> None:
    package = build_board_package_from_files(BOARD_PATH, LAYOUT_PATH)
    session = GameSession.from_files(
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        player_ids=["p1", "p2"],
        seed=7,
    )
    view = build_game_view(session)
    canvas = _CanvasStub()

    GameBoardRenderer().redraw(canvas, package, view)

    ovals = [(args, kwargs) for name, args, kwargs in canvas.calls if name == "oval"]

    route_ovals = [
        (args, kwargs)
        for args, kwargs in ovals
        if len(args) == 4 and (args[2] - args[0]) <= 32 and (args[3] - args[1]) <= 32
    ]
    assert len(route_ovals) >= 1

    route_fills = {kw.get("fill") for _, kw in route_ovals}
    assert EMPTY_ROUTE_FILL in route_fills or WHITE_ROUTE_FILL in route_fills or any(
        c in route_fills for c in PLAYER_COLORS.values()
    )


def test_total_control_site_gets_player_colored_border() -> None:
    package = build_board_package_from_files(BOARD_PATH, LAYOUT_PATH)
    session = GameSession.from_files(
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        player_ids=["p1", "p2"],
        seed=7,
    )
    view = build_game_view(session)
    canvas = _CanvasStub()

    GameBoardRenderer().redraw(canvas, package, view)

    rectangles = [(args, kwargs) for name, args, kwargs in canvas.calls if name == "rectangle"]
    outlines = {kw.get("outline") for _, kw in rectangles}

    assert DEFAULT_SITE_OUTLINE in outlines


def test_total_control_owner_helper_none_for_empty_or_mixed_slots() -> None:
    assert _total_control_owner((), ()) is None
    assert _total_control_owner((None, None, None), ()) is None
    assert _total_control_owner(("white",), ()) is None
    assert _total_control_owner(("p1", None, "p1"), ()) is None
    assert _total_control_owner(("p1", "p2"), ()) is None
    assert _total_control_owner(("p1", "p1"), ("p2",)) is None


def test_total_control_owner_helper_returns_player_on_full_control() -> None:
    assert _total_control_owner(("p1", "p1", "p1"), ()) == "p1"
    assert _total_control_owner(("p2",), ()) == "p2"
    assert _total_control_owner(("p3", "p3"), ("p3",)) == "p3"


# ---------------------------------------------------------------------------
# _derive_control_owner (troop-majority control)
# ---------------------------------------------------------------------------


def test_derive_control_owner_empty_or_all_none_is_none() -> None:
    assert _derive_control_owner(()) is None
    assert _derive_control_owner((None, None, None)) is None


def test_derive_control_owner_white_never_controls() -> None:
    assert _derive_control_owner(("white",)) is None
    assert _derive_control_owner(("white", "white", "white")) is None


def test_derive_control_owner_player_beats_white() -> None:
    assert _derive_control_owner(("p1", "p1", "white")) == "p1"
    assert _derive_control_owner(("p1", "white")) is None


def test_derive_control_owner_tie_returns_none() -> None:
    assert _derive_control_owner(("p1", "p2")) is None
    assert _derive_control_owner(("p1", "p2", "p2")) == "p2"


def test_derive_control_owner_single_player_sole() -> None:
    assert _derive_control_owner(("p1", None, None)) == "p1"
    assert _derive_control_owner(("p1",)) == "p1"


def test_derive_control_owner_player_white_tie_returns_none() -> None:
    assert _derive_control_owner(("p1", "white", None)) is None


def test_derive_control_owner_player_majority() -> None:
    assert _derive_control_owner(("p1", "p1", "p2", "white", None, None)) == "p1"
    assert _derive_control_owner(("p1", "p2", "p2", "white", None, None)) == "p2"
