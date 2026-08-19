"""Read-only gameplay board renderer tests."""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.session import CSession
from engine_c.bindings.view import NodeOccupancyView, build_c_game_view
from game_setup.loaders import build_board_package_from_files
from game_setup.types import NodeKind
from interface.board_view import BoardNodeView
from interface.game_renderer import (
    DEFAULT_SITE_OUTLINE,
    EMPTY_ROUTE_FILL,
    PLAYER_COLORS,
    WHITE_ROUTE_FILL,
    GameBoardRenderer,
    _derive_control_owner,
    _total_control_owner,
)

BASE_DIR = Path(__file__).resolve().parents[1]
BOARD_PATH = BASE_DIR / "data" / "boards" / "tyrants_of_the_underdark.json"
LAYOUT_PATH = BASE_DIR / "data" / "layouts" / "tyrants_of_the_underdark_layout.json"
CARD_PATH = BASE_DIR / "data" / "cards"
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
    session = CSession.from_files(
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        player_ids=["p1", "p2"],
        seed=7,
    )
    view = build_c_game_view(session)
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
    session = CSession.from_files(
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        player_ids=["p1", "p2"],
        seed=7,
    )
    view = build_c_game_view(session)

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
    session = CSession.from_files(
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        player_ids=["p1", "p2"],
        seed=7,
    )
    view = build_c_game_view(session)
    canvas = _CanvasStub()

    GameBoardRenderer().redraw(canvas, package, view)

    rectangles = [(args, kwargs) for name, args, kwargs in canvas.calls if name == "rectangle"]
    texts = [(args, kwargs) for name, args, kwargs in canvas.calls if name == "text"]

    site_label_texts = [kw.get("text", "") for _, kw in texts]
    assert any("Menzoberranzan" in t for t in site_label_texts)
    assert any("Gauntlgrym" in t for t in site_label_texts)

    interior_texts = [(a, kw) for name, a, kw in canvas.calls if name == "text"]
    assert not any("Owner:" in kw.get("text", "") for _, kw in interior_texts)
    vp_texts = [(a, kw) for a, kw in interior_texts if isinstance(kw.get("text", ""), str) and kw["text"].startswith("VP:")]
    assert len(vp_texts) > 0
    for _, kwargs in vp_texts:
        font = kwargs.get("font", ())
        assert "bold" in font

    assert len(rectangles) > 0
    first_rect = rectangles[0][1]
    assert "fill" in first_rect
    assert "outline" in first_rect


def test_route_drawn_as_circle_with_fill_based_on_owner() -> None:
    package = build_board_package_from_files(BOARD_PATH, LAYOUT_PATH)
    session = CSession.from_files(
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        player_ids=["p1", "p2"],
        seed=7,
    )
    view = build_c_game_view(session)
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
    session = CSession.from_files(
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        player_ids=["p1", "p2"],
        seed=7,
    )
    view = build_c_game_view(session)
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


def test_site_vp_label_is_bold_without_owner() -> None:
    node = BoardNodeView(
        node_id="site1",
        label="Test Site",
        kind=NodeKind.SITE,
        center_x=50.0,
        center_y=50.0,
        bounds=(10.0, 10.0, 80.0, 80.0),
        troop_slot_points=((30.0, 30.0), (50.0, 30.0), (70.0, 30.0)),
        adjacent_to=(),
    )
    occupancy = NodeOccupancyView(
        node_id="site1",
        kind=NodeKind.SITE,
        adjacent_to=(),
        control_vp=3,
        total_control_vp_per_turn=0,
        troop_slots=("p1", "p1", None),
        spies=(),
        vp_tokens=0,
    )

    canvas = _CanvasStub()
    GameBoardRenderer()._draw_site(canvas, node, occupancy, is_highlighted=False, scale=1.0)

    texts = [(a, kw) for name, a, kw in canvas.calls if name == "text"]
    assert not any("Owner:" in kw.get("text", "") for _, kw in texts)

    vp_texts = [(a, kw) for a, kw in texts if isinstance(kw.get("text", ""), str) and kw["text"] == "VP: 3"]
    assert len(vp_texts) == 1
    assert "bold" in vp_texts[0][1].get("font", ())


def test_site_majority_control_border_is_player_color() -> None:
    node = BoardNodeView(
        node_id="site1",
        label="Test Site",
        kind=NodeKind.SITE,
        center_x=50.0,
        center_y=50.0,
        bounds=(10.0, 10.0, 80.0, 80.0),
        troop_slot_points=((30.0, 30.0), (50.0, 30.0), (70.0, 30.0)),
        adjacent_to=(),
    )
    occupancy = NodeOccupancyView(
        node_id="site1",
        kind=NodeKind.SITE,
        adjacent_to=(),
        control_vp=1,
        total_control_vp_per_turn=0,
        troop_slots=("p1", "p1", None),
        spies=(),
        vp_tokens=0,
    )

    canvas = _CanvasStub()
    GameBoardRenderer()._draw_site(canvas, node, occupancy, is_highlighted=False, scale=1.0)

    rects = [(a, kw) for name, a, kw in canvas.calls if name == "rectangle"]
    assert rects
    assert rects[0][1].get("outline") == PLAYER_COLORS["p1"]

    lines = [(a, kw) for name, a, kw in canvas.calls if name == "line"]
    assert len(lines) == 0


def test_site_no_control_border_is_default() -> None:
    node = BoardNodeView(
        node_id="site1",
        label="Test Site",
        kind=NodeKind.SITE,
        center_x=50.0,
        center_y=50.0,
        bounds=(10.0, 10.0, 80.0, 80.0),
        troop_slot_points=((30.0, 30.0), (50.0, 30.0), (70.0, 30.0)),
        adjacent_to=(),
    )
    occupancy = NodeOccupancyView(
        node_id="site1",
        kind=NodeKind.SITE,
        adjacent_to=(),
        control_vp=1,
        total_control_vp_per_turn=0,
        troop_slots=("p1", "p2", None),
        spies=(),
        vp_tokens=0,
    )

    canvas = _CanvasStub()
    GameBoardRenderer()._draw_site(canvas, node, occupancy, is_highlighted=False, scale=1.0)

    rects = [(a, kw) for name, a, kw in canvas.calls if name == "rectangle"]
    assert rects
    assert rects[0][1].get("outline") == DEFAULT_SITE_OUTLINE

    lines = [(a, kw) for name, a, kw in canvas.calls if name == "line"]
    assert len(lines) == 0


def test_lighten_color_produces_lighter_valid_hex() -> None:
    from interface.game_renderer import _lighten_color

    result = _lighten_color("#000000")
    assert len(result) == 7
    assert result[0] == "#"
    r, g, b = int(result[1:3], 16), int(result[3:5], 16), int(result[5:7], 16)
    assert r > 0
    assert g > 0
    assert b > 0

    result2 = _lighten_color("#2f72c4")
    r2, g2, b2 = int(result2[1:3], 16), int(result2[3:5], 16), int(result2[5:7], 16)
    assert r2 >= 0x2F
    assert g2 >= 0x72
    assert b2 >= 0xC4
    assert r2 <= 255
    assert g2 <= 255
    assert b2 <= 255

    result3 = _lighten_color("#ffffff")
    assert result3 == "#ffffff"


def test_site_total_control_draws_lighter_hatching_inside_bounds() -> None:
    from interface.game_renderer import _lighten_color

    node = BoardNodeView(
        node_id="site1",
        label="Test Site",
        kind=NodeKind.SITE,
        center_x=50.0,
        center_y=50.0,
        bounds=(10.0, 10.0, 80.0, 80.0),
        troop_slot_points=((30.0, 30.0), (50.0, 30.0), (70.0, 30.0)),
        adjacent_to=(),
    )
    occupancy = NodeOccupancyView(
        node_id="site1",
        kind=NodeKind.SITE,
        adjacent_to=(),
        control_vp=1,
        total_control_vp_per_turn=0,
        troop_slots=("p1", "p1", "p1"),
        spies=(),
        vp_tokens=0,
    )

    canvas = _CanvasStub()
    GameBoardRenderer()._draw_site(canvas, node, occupancy, is_highlighted=False, scale=1.0)

    expected_fill = _lighten_color(PLAYER_COLORS["p1"])
    lines = [(a, kw) for name, a, kw in canvas.calls if name == "line"]
    hatch_lines = [(a, kw) for a, kw in lines if kw.get("fill") == expected_fill]
    assert len(hatch_lines) > 0

    left, top, w, h = node.bounds
    right = left + w
    bottom = top + h
    for a, _kw in hatch_lines:
        for coord in a:
            assert isinstance(coord, (int, float))
        x1, y1, x2, y2 = a[0], a[1], a[2], a[3]
        assert left <= x1 <= right
        assert top <= y1 <= bottom
        assert left <= x2 <= right
        assert top <= y2 <= bottom

    rects = [(a, kw) for name, a, kw in canvas.calls if name == "rectangle"]
    assert rects
    assert rects[0][1].get("outline") == PLAYER_COLORS["p1"]
