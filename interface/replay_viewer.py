"""Tk replay viewer for IS-MCTS artifacts — subclass of the hotseat viewer.

Loads a simulated game from ``artifacts/ismcts/**/game_XXXX/replay.json`` and
steps through it decision by decision by re-simulating through the C engine
(:mod:`interface.replay_player`). Read-only: no move can be applied that the
log did not record.

Run with ``python -m interface.replay_viewer`` (or ``just replay-viewer``).
"""

from __future__ import annotations

import argparse
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from game_setup.market_setup import DEMONS_DECK_ID
from interface.game_viewer import (
    DECKS_DIR,
    DEFAULT_BOARD_PATH,
    DEFAULT_CARD_PATH,
    DEFAULT_LAYOUT_PATH,
    DEFAULT_SETUP_PATH,
    ROOT_DIR,
    GameViewerApp,
)
from interface.replay_loader import ReplayBundle, ReplayMeta, discover_replays, load_replay
from interface.replay_player import ReplayDesyncError, ReplayPlayer

MAX_POLICY_ROWS = 5


def _decision_display_label(decision: dict) -> str:
    """Human-facing decision summary for the replay decision panel.

    Prefers the enriched ``chosen_label`` written by the IS-MCTS runner for
    ``resolve_generic`` lines, falls back to the raw ``chosen_move``, and
    appends a compact second line from the structured ``generic`` context when
    present.  Additive-only: unknown/malformed fields degrade to the raw
    string or an empty footer, never an exception.
    """
    chosen_label = decision.get("chosen_label")
    chosen_move = decision.get("chosen_move", "")
    first = chosen_label if chosen_label else chosen_move

    generic = decision.get("generic")
    parts: list[str] = []
    if isinstance(generic, dict):
        source = generic.get("source_card_id")
        if source:
            parts.append(str(source))
        op = generic.get("op")
        if op:
            parts.append(f"op={op}")
        move_action_id = generic.get("move_action_id")
        if move_action_id:
            parts.append(f"target={move_action_id}")
    footer = " · ".join(parts) if parts else ""
    return f"{first}\n{footer}" if footer else first


class ReplayViewerApp(GameViewerApp):
    """Replay-only viewer; transports, timeline, autoplay, decision inspector."""

    def __init__(
        self,
        root: tk.Tk,
        *,
        artifacts_root: Path,
        board_path: Path,
        layout_path: Path,
        card_path: Path,
        setup_path: Path,
        decks_dir: Path,
        game_dir: Path | None = None,
    ) -> None:
        self._artifacts_root = Path(artifacts_root)
        self._playing = False
        self._play_after_id: str | None = None
        self._timeline_updating = False
        self._player: ReplayPlayer | None = None
        self._bundle: ReplayBundle | None = None
        self._replay_metas: list[ReplayMeta] = []

        self.speed_var = tk.DoubleVar(master=root, value=0.50)
        self.warning_var = tk.StringVar(master=root, value="")
        self.move_status_var = tk.StringVar(master=root, value="")
        self.step_var = tk.IntVar(master=root, value=0)

        super().__init__(
            root,
            board_path=board_path,
            layout_path=layout_path,
            card_path=card_path,
            setup_path=setup_path,
            decks_dir=decks_dir,
            initial_player_count=2,
            seed=None,
            autostart=False,
        )

        self.root.title("IS-MCTS Replay Viewer")
        self.legal_moves_listbox.bind(
            "<Double-Button-1>", lambda _event: self._readonly_toast("read-only replay")
        )

        self._populate_replay_box()
        self._build_decision_panel()
        self._bind_replay_keys()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        if game_dir is not None:
            self._load_replay_dir(Path(game_dir))

    # ── control bar (replaces the hotseat setup/action rows) ─────────────────

    def _build_control_bar(self, controls: ttk.Frame) -> None:
        pick_row = ttk.Frame(controls)
        pick_row.pack(fill=tk.X)

        ttk.Label(pick_row, text="Replay:").pack(side=tk.LEFT)
        self.replay_box = ttk.Combobox(
            pick_row,
            state="readonly",
            width=72,
            height=256,
            textvariable=tk.StringVar(master=self.root, value="(no replays found)"),
        )
        self.replay_box.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 8))
        self.replay_box.bind("<<ComboboxSelected>>", self._on_replay_selected)
        ttk.Button(pick_row, text="Browse…", command=self._browse).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(pick_row, text="Reload", command=self._reload).pack(side=tk.LEFT)

        transport_row = ttk.Frame(controls)
        transport_row.pack(fill=tk.X, pady=(6, 0))

        self._reset_button = ttk.Button(transport_row, text="|<", command=lambda: self._seek(0), width=3)
        self._reset_button.pack(side=tk.LEFT)
        ttk.Button(transport_row, text="<", command=self._step_back, width=3).pack(side=tk.LEFT, padx=(2, 0))
        self.play_button = ttk.Button(transport_row, text="▶", command=self._toggle_play, width=3)
        self.play_button.pack(side=tk.LEFT, padx=(2, 0))
        ttk.Button(transport_row, text=">", command=self._step_forward, width=3).pack(side=tk.LEFT, padx=(2, 0))
        self._end_button = ttk.Button(
            transport_row,
            text=">|",
            command=lambda: self._seek(self.player.total_steps if self._player else 0),
            width=3,
        )
        self._end_button.pack(side=tk.LEFT, padx=(2, 6))

        ttk.Label(transport_row, text="Speed:").pack(side=tk.LEFT, padx=(8, 0))
        self.speed_spin = ttk.Spinbox(
            transport_row,
            from_=0.05,
            to=5.0,
            increment=0.05,
            textvariable=self.speed_var,
            width=5,
        )
        self.speed_spin.pack(side=tk.LEFT, padx=(4, 4))
        ttk.Label(transport_row, text="s/step").pack(side=tk.LEFT)

        self.timeline = ttk.Scale(
            transport_row,
            from_=0,
            to=1,
            variable=self.step_var,
            orient=tk.HORIZONTAL,
            command=self._on_timeline_change,
        )
        self.timeline.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(12, 8))
        self.step_label_var = tk.StringVar(master=self.root, value="Step 0 / 0")
        ttk.Label(transport_row, textvariable=self.step_label_var, width=16, anchor=tk.E).pack(side=tk.LEFT)

        status_row = ttk.Frame(controls)
        status_row.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(status_row, textvariable=self.move_status_var, font=("TkFixedFont", 9)).pack(side=tk.LEFT)
        ttk.Label(status_row, textvariable=self.warning_var, foreground="#8a6d00", font=("TkFixedFont", 9)).pack(side=tk.RIGHT, padx=6)

    # ── decision inspector (sidebar, above Legal Moves) ──────────────────────

    def _build_decision_panel(self) -> None:
        sidebar = self.legal_moves_listbox.master.master
        legal_moves_frame = self.legal_moves_listbox.master

        decision_frame = ttk.LabelFrame(sidebar, text="Decision", padding=4)
        decision_frame.pack(fill=tk.X, pady=(0, 8), before=legal_moves_frame)

        ttk.Label(decision_frame, textvariable=self.move_status_var, font=("TkFixedFont", 8), wraplength=330, justify=tk.LEFT).pack(anchor=tk.W)
        self._decision_meta_var = tk.StringVar(master=self.root, value="(no decision telemetry)")
        ttk.Label(decision_frame, textvariable=self._decision_meta_var, font=("TkFixedFont", 8), wraplength=330, justify=tk.LEFT).pack(anchor=tk.W, pady=(2, 0))

        self._policy_listbox = tk.Listbox(decision_frame, height=MAX_POLICY_ROWS, exportselection=False)
        self._policy_listbox.pack(fill=tk.X, pady=(4, 0))

    # ── replay loading ───────────────────────────────────────────────────────

    def _populate_replay_box(self) -> None:
        try:
            metas = discover_replays(self._artifacts_root)
        except OSError:
            metas = []
        self._replay_metas = metas
        labels = [meta.label for meta in metas]
        self.replay_box.configure(values=labels or ["(no replays found)"])
        if labels:
            self.replay_box.current(0)

    def _on_replay_selected(self, _event: tk.Event[ttk.Combobox]) -> None:
        index = self.replay_box.current()
        if 0 <= index < len(self._replay_metas):
            self._load_replay_dir(self._replay_metas[index].game_dir)

    def _browse(self) -> None:
        path = filedialog.askopenfilename(
            title="Open Replay",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=self._artifacts_root,
        )
        if not path:
            return
        self._load_replay_dir(Path(path).parent)

    def _reload(self) -> None:
        if self._bundle is None:
            return
        self._load_replay_dir(self._bundle.meta.game_dir)

    def _load_replay_dir(self, game_dir: Path) -> None:
        try:
            bundle = load_replay(game_dir)
        except Exception as exc:
            messagebox.showerror("Failed to load replay", str(exc))
            return
        self._apply_bundle(bundle)

    def _apply_bundle(self, bundle: ReplayBundle) -> None:
        self._cancel_timer()
        self._set_playing(False)
        if self._player is not None:
            self._player.close()

        self._bundle = bundle
        self._player = ReplayPlayer(bundle)
        self._game_over_shown = False
        self._clear_filters()

        from engine_c.bindings.view import build_c_game_view

        self.session = self._player.session
        view = build_c_game_view(self.session, node_names=self._node_names)
        self._rebuild_package_for_loaded_state_c(view)
        self._demons_in_market = (
            bundle.meta.deck_a_id == DEMONS_DECK_ID or bundle.meta.deck_b_id == DEMONS_DECK_ID
        )
        self._deck_a_label = bundle.meta.deck_a_id
        self._deck_b_label = bundle.meta.deck_b_id

        self._apply_responsive_layout()
        self.replay_box.set(bundle.meta.label)
        self._refresh_after_step()
        self._auto_fit_zoom()

    # ── transport ────────────────────────────────────────────────────────────

    def _step_forward(self) -> None:
        if self._player is None:
            return
        self._set_playing(False)
        try:
            if not self._player.step_forward():
                return
        except ReplayDesyncError as exc:
            self._handle_desync(exc)
            return
        self._refresh_after_step()

    def _step_back(self) -> None:
        if self._player is None:
            return
        self._set_playing(False)
        self._seek(self._player.index - 1)

    def _seek(self, target: int) -> None:
        if self._player is None:
            return
        self._cancel_timer()
        self._set_playing(False)
        self._suppress_score_dialog = True
        try:
            self._player.seek(target)
        except ReplayDesyncError as exc:
            self._suppress_score_dialog = False
            self._handle_desync(exc)
            return
        self._suppress_score_dialog = False
        self._refresh_after_step()

    def _toggle_play(self) -> None:
        if self._player is None:
            return
        if self._playing:
            self._set_playing(False)
        elif not self._player.is_terminal:
            self._set_playing(True)

    def _set_playing(self, playing: bool) -> None:
        if playing == self._playing:
            return
        self._playing = playing
        self.play_button.configure(text="⏸" if playing else "▶")
        if playing:
            self._play_after_id = self.root.after(
                int(float(self.speed_var.get()) * 1000), self._tick
            )

    def _cancel_timer(self) -> None:
        if self._play_after_id is not None:
            self.root.after_cancel(self._play_after_id)
            self._play_after_id = None

    def _tick(self) -> None:
        self._play_after_id = None
        if not self._playing or self._player is None:
            return
        try:
            if not self._player.step_forward():
                self._set_playing(False)
                return
        except ReplayDesyncError as exc:
            self._handle_desync(exc)
            return
        self._refresh_after_step()
        self._play_after_id = self.root.after(
            int(float(self.speed_var.get()) * 1000), self._tick
        )

    # ── refresh ──────────────────────────────────────────────────────────────

    def _refresh_after_step(self) -> None:
        self.session = self._player.session
        self._refresh_view()
        self._highlight_recorded_move()
        self._update_decision_panel()
        self._update_transport()
        self._update_step_status()
        self._update_warning()

    def _highlight_recorded_move(self) -> None:
        entry = self._player.next_entry()
        if entry is None:
            return
        payload = entry["payload"]
        for index, legal_move in enumerate(self._visible_legal_moves):
            if legal_move.move.to_payload() == payload:
                self.legal_moves_listbox.selection_clear(0, tk.END)
                self.legal_moves_listbox.selection_set(index)
                self.legal_moves_listbox.see(index)
                return

    def _update_decision_panel(self) -> None:
        if not self._player:
            return
        decision = self._player.decision_at(self._player.index)
        if decision is None and self._player.index == self._player.total_steps:
            decision = self._player.decision_at(self._player.index - 1)

        if not self._bundle.decisions or decision is None:
            self._decision_meta_var.set("(no decision telemetry)")
            self._policy_listbox.delete(0, tk.END)
            return

        sims = decision.get("sims_requested", "-")
        wall = decision.get("wall_time_ms", "-")
        self._decision_meta_var.set(
            f"{_decision_display_label(decision)}\nsims {sims} · {wall} ms"
        )

        legal = decision.get("legal_moves", []) or []
        policy = decision.get("policy", {}) or {}
        counts = decision.get("visit_counts", {}) or {}
        chosen_id = str(decision.get("chosen_action_id", ""))

        def _prob(item) -> float:
            try:
                return float(item[1])
            except (TypeError, ValueError):
                return 0.0

        ranked = sorted(policy.items(), key=_prob, reverse=True)[:MAX_POLICY_ROWS]

        self._policy_listbox.delete(0, tk.END)
        for action_id, prob in ranked:
            index = int(action_id) if str(action_id).isdigit() else None
            label = legal[index] if index is not None and 0 <= index < len(legal) else str(action_id)
            visits = counts.get(str(action_id), 0)
            prefix = "▶ " if str(action_id) == chosen_id else ""
            self._policy_listbox.insert(tk.END, f"{prefix}p={prob:.2f} (v={visits})  {label}")

    def _update_transport(self) -> None:
        self.step_label_var.set(f"Step {self._player.index} / {self._player.total_steps}")
        self._timeline_updating = True
        try:
            self.timeline.configure(to=max(1, self._player.total_steps))
            self.step_var.set(self._player.index)
        finally:
            self._timeline_updating = False

    def _update_step_status(self) -> None:
        entry = self._player.next_entry()
        if entry is not None:
            self.move_status_var.set(
                f"Round {entry['round_number']} · {entry['phase']} · {entry['player_id']} · {entry['label']}"
            )
        else:
            state = self._player.session.state
            self.move_status_var.set(
                f"Round {state.round_number} · {state.phase} · {state.current_player_id} · terminal"
            )

    def _update_warning(self) -> None:
        parts: list[str] = []
        if self._bundle is None:
            self.warning_var.set("")
            return
        if self._bundle.setup_sha_matches is False:
            parts.append("setup hash differs")
        if self._bundle.substituted_paths:
            parts.append("path fallback: " + ", ".join(self._bundle.substituted_paths))
        self.warning_var.set("⚠ " + " · ".join(parts) if parts else "")

    # ── timeline / keyboard / desync / close ─────────────────────────────────

    def _on_timeline_change(self, value: str) -> None:
        if self._timeline_updating:
            return
        self._seek(int(round(float(value))))

    def _bind_replay_keys(self) -> None:
        self.root.bind("<space>", self._on_space_key)
        self.root.bind("<Control-Left>", self._on_step_back_key)
        self.root.bind("<Control-Right>", self._on_step_forward_key)
        self.root.bind("<Home>", self._on_home_key)
        self.root.bind("<End>", self._on_end_key)

    def _on_space_key(self, _event: tk.Event[tk.Misc]) -> str:
        self._toggle_play()
        return "break"

    def _on_step_back_key(self, _event: tk.Event[tk.Misc]) -> str:
        self._step_back()
        return "break"

    def _on_step_forward_key(self, _event: tk.Event[tk.Misc]) -> str:
        self._step_forward()
        return "break"

    def _on_home_key(self, _event: tk.Event[tk.Misc]) -> str:
        self._seek(0)
        return "break"

    def _on_end_key(self, _event: tk.Event[tk.Misc]) -> str:
        self._seek(self._player.total_steps if self._player else 0)
        return "break"

    def _handle_desync(self, exc: ReplayDesyncError) -> None:
        self._refresh_after_step()
        sample = ",\n".join(repr(p) for p in exc.legal[:3]) if exc.legal else "(no legal moves)"
        messagebox.showerror(
            "Replay desync",
            f"Step {exc.step_index} recorded {exc.expected!r} but no legal move matches.\n\n"
            f"Sample legal payloads:\n{sample}",
        )

    def _on_close(self) -> None:
        self._cancel_timer()
        if self._player is not None:
            self._player.close()
        self.root.destroy()

    # ── read-only enforcement ────────────────────────────────────────────────

    def _apply_selected_legal_move(self) -> None:
        self._readonly_toast("read-only replay")

    def _apply_first_legal_move(self) -> None:
        self._readonly_toast("read-only replay")

    def _on_legal_move_double_click(self, _event: tk.Event[tk.Listbox]) -> None:
        self._readonly_toast("read-only replay")

    def _load_game(self) -> None:
        self._readonly_toast("read-only replay")

    def _readonly_toast(self, text: str) -> None:
        self.move_status_var.set(f"{text} — no move can be applied that the log did not record")


def main() -> None:
    """Run the interactive replay viewer (mirrors game_viewer.main setup)."""
    parser = argparse.ArgumentParser(description="View IS-MCTS replay artifacts")
    parser.add_argument("--artifacts-root", type=Path, default=ROOT_DIR / "artifacts" / "ismcts")
    parser.add_argument("--game-dir", type=Path, default=None, help="Load this replay immediately")
    parser.add_argument("--board-path", type=Path, default=DEFAULT_BOARD_PATH)
    parser.add_argument("--layout-path", type=Path, default=DEFAULT_LAYOUT_PATH)
    parser.add_argument("--card-path", type=Path, default=DEFAULT_CARD_PATH)
    parser.add_argument("--setup-path", type=Path, default=DEFAULT_SETUP_PATH)
    parser.add_argument("--decks-dir", type=Path, default=DECKS_DIR)
    args = parser.parse_args()

    root = tk.Tk()
    root.withdraw()

    tmp = tk.Toplevel(root)
    tmp.geometry("1x1+0+0")
    tmp.update_idletasks()
    primary_w = tmp.winfo_screenwidth()
    tmp.destroy()

    tmp2 = tk.Toplevel(root)
    tmp2.geometry(f"1x1+{primary_w + 100}+0")
    tmp2.update_idletasks()
    second_w = tmp2.winfo_screenwidth()
    second_h = tmp2.winfo_screenheight()
    tmp2.destroy()

    if second_w != primary_w and second_w < primary_w:
        root.geometry(f"{second_w}x{second_h}+{primary_w}+0")
    else:
        root.state("zoomed")

    try:
        ReplayViewerApp(
            root,
            artifacts_root=args.artifacts_root,
            board_path=args.board_path,
            layout_path=args.layout_path,
            card_path=args.card_path,
            setup_path=args.setup_path,
            decks_dir=args.decks_dir,
            game_dir=args.game_dir,
        )
    except Exception as exc:
        messagebox.showerror("Failed to start Replay Viewer", str(exc))
        root.destroy()
        raise
    root.deiconify()
    root.mainloop()


if __name__ == "__main__":
    main()