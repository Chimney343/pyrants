"""Read-only gameplay board renderer tests."""

from __future__ import annotations

from pathlib import Path

from game_session import GameSession
from game_setup.loaders import build_board_package_from_files
from game_view import build_game_view
from interface.game_renderer import GameBoardRenderer

BASE_DIR = Path(__file__).resolve().parents[1]
BOARD_PATH = BASE_DIR / "data" / "boards" / "base_game.json"
LAYOUT_PATH = BASE_DIR / "data" / "layouts" / "base_game_layout.json"
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
