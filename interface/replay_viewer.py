"""Tk replay viewer for stepping through simulation logs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from game_simulation import replay_views_from_payload
from game_view import GameView
from game_setup.loaders import build_board_package_from_files
from interface.game_renderer import GameBoardRenderer

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_LAYOUT_PATH = ROOT_DIR / "data" / "layouts" / "tyrants_of_the_underdark_layout.json"
DEFAULT_BOARD_PATH = ROOT_DIR / "data" / "boards" / "tyrants_of_the_underdark.json"
DEFAULT_CARD_PATH = ROOT_DIR / "data" / "cards" / "catalog.json"
DEFAULT_SETUP_PATH = ROOT_DIR / "data" / "decks" / "base_setup.json"


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

        self.package = build_board_package_from_files(board_path=board_path, layout_path=layout_path)
        self.views = replay_views_from_payload(
            replay_payload,
            board_path=board_path if card_path is not None else None,
            card_path=card_path,
            setup_path=setup_path,
            player_ids=player_ids,
            seed=seed,
        )
        self.replay_steps = replay_payload.get("replay_log", [])
        if not isinstance(self.replay_steps, list):
            raise ValueError("Replay payload must include replay_log")

        self.renderer = GameBoardRenderer()
        self.current_index = 0

        self.status_var = tk.StringVar(value="")
        self.prompt_var = tk.StringVar(value="")
        self.players_var = tk.StringVar(value="")
        self.move_var = tk.StringVar(value="")

        self._build_ui()
        self._render_step(0)

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=8)
        frame.pack(fill=tk.BOTH, expand=True)

        controls = ttk.Frame(frame)
        controls.pack(fill=tk.X)
        ttk.Button(controls, text="Prev", command=self._prev_step).pack(side=tk.LEFT)
        ttk.Button(controls, text="Next", command=self._next_step).pack(side=tk.LEFT, padx=6)

        self.slider = tk.Scale(
            controls,
            from_=0,
            to=max(0, len(self.views) - 1),
            orient=tk.HORIZONTAL,
            showvalue=True,
            command=self._on_slider_change,
            length=360,
        )
        self.slider.pack(side=tk.LEFT, padx=(6, 0))

        ttk.Label(controls, textvariable=self.status_var).pack(side=tk.LEFT, padx=12)

        content = ttk.Frame(frame)
        content.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        self.canvas = tk.Canvas(
            content,
            width=self.package.layout.canvas.width,
            height=self.package.layout.canvas.height,
            bg="#f7f8fa",
            highlightthickness=0,
        )
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        sidebar = ttk.Frame(content, width=360)
        sidebar.pack(side=tk.RIGHT, fill=tk.Y)
        sidebar.pack_propagate(False)

        ttk.Label(sidebar, text="Move", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        ttk.Label(sidebar, textvariable=self.move_var, wraplength=340, justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 10))

        ttk.Label(sidebar, text="Prompts", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        ttk.Label(sidebar, textvariable=self.prompt_var, wraplength=340, justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 10))

        ttk.Label(sidebar, text="Players", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        ttk.Label(sidebar, textvariable=self.players_var, wraplength=340, justify=tk.LEFT).pack(anchor=tk.W)

    def _render_step(self, index: int) -> None:
        index = max(0, min(index, len(self.views) - 1))
        self.current_index = index
        self.slider.set(index)

        view = self.views[index]
        self.renderer.redraw(self.canvas, self.package, view)

        self.status_var.set(
            f"Step {index}/{len(self.views) - 1} | Round {view.round_number} | "
            f"Phase {view.phase} | Current {view.current_player_id}"
        )
        self.prompt_var.set("\n".join(view.prompts))

        if index == 0:
            self.move_var.set("Initial state")
        else:
            step_entry = self.replay_steps[index - 1]
            if isinstance(step_entry, dict):
                label = str(step_entry.get("label", ""))
                move_type = str(step_entry.get("move_type", ""))
                self.move_var.set(f"{label}\n({move_type})")
            else:
                self.move_var.set("Unknown replay step")

        player_lines = [
            (
                f"{summary.player_id}{' *' if summary.is_current else ''}: "
                f"hand {summary.hand_count}, deck {summary.deck_count}, discard {summary.discard_count}, "
                f"played {summary.played_count}, barracks {summary.barracks}, spies {summary.spies_available}, vp {summary.vp_tokens}"
            )
            for summary in view.player_summaries
        ]
        self.players_var.set("\n".join(player_lines))

    def _prev_step(self) -> None:
        self._render_step(self.current_index - 1)

    def _next_step(self) -> None:
        self._render_step(self.current_index + 1)

    def _on_slider_change(self, value: str) -> None:
        self._render_step(int(float(value)))


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
