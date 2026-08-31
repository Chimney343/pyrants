"""Generate an .xlsx catalog of every legal-move label template.

Each row is one label *template* (the format string used to render a legal
move's label), together with up to three concrete *filled examples* captured
from real engine runs.

Templates are discovered by driving the C engine:

* ``num_games`` random games (mixed 2/3/4-player) walk the game tree with a
  weighted random move picker, capturing every legal-move label produced
  along the way.
* every JSON scenario under ``data/scenarios/`` (crafted to reach specific
  cards and rare effects) is deserialised and its legal moves are captured.

Concrete labels are then reduced to a template by substituting the variable
parts (card names, board nodes, players, resources, aspects, zones, counts)
with ``{card}``, ``{node}``, ``{player}``, ``{resource}``, ``{aspect}``,
``{zone}`` and ``{n}`` placeholders. A small hand-curated list of templates
that are defined in the engine but unreachable in normal play (e.g. pure
fallbacks) is merged in and marked ``static-only``.

Usage:
    python -m scripts.generate_move_label_templates [--num-games 60] \
        [--max-steps 400] [--scenarios-dir data/scenarios] \
        [--output artifacts/move_label_templates.xlsx] [--no-scenarios]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path
from random import Random

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from game_setup.loaders import assemble_catalog_payload  # noqa: E402

try:
    from engine_c.bindings.ce_api import CEngine  # noqa: E402
    from engine_c.bindings.session import CSession  # noqa: E402
    from engine_c.bindings.view import build_c_game_view  # noqa: E402
except Exception:  # pragma: no cover - DLL may be absent when imported
    CEngine = None
    CSession = None
    build_c_game_view = None

DEFAULT_BOARD = ROOT_DIR / "data" / "boards" / "tyrants_of_the_underdark.json"
DEFAULT_CARDS = ROOT_DIR / "data" / "cards"
DEFAULT_SCENARIOS = ROOT_DIR / "data" / "scenarios"
DEFAULT_OUTPUT = ROOT_DIR / "artifacts" / "move_label_templates.xlsx"

# Hand-curated templates that the engine defines but that are unreachable (or
# extremely unlikely to be reached) by ordinary play. Merged in so the sheet is
# exhaustive, and marked "static-only" when no example is observed.
STATIC_TEMPLATES: list[tuple[str, str]] = [
    ("play_card", "Play {card}"),
    ("end_main_phase", "End main phase"),
    ("resolve_end_of_turn", "Proceed to end of turn"),
    ("resolve_cleanup", "Proceed to cleanup"),
    ("deploy", "Deploy a troop to {node}"),
    ("initial_placement", "Place starting troop at {node}"),
    ("assassinate", "Assassinate {player} troop at {node}"),
    ("recruit", "Recruit {card}"),
    ("return_spy", "Return {player}'s spy from {node}"),
    ("activate_ability", "Activate {card}'s ability"),
    ("decline_ability", "Decline {card}'s ability"),
    ("promote_card", "Promote {card}"),
    ("promote_card", "Promote {card} ({aspect})"),
    ("promote_card", "Promote {card} (Focus: {aspect})"),
    ("promote_card", "{card}: Promote card {card}"),
    ("promote_card", "{card}: Promote card {card} ({aspect})"),
    ("promote_card", "{card}: Promote card {card} (Focus: {aspect})"),
    ("skip_promote", "Skip promotion ({card})"),
    # Pure fallbacks in the describe/enrich paths.
    ("resolve_generic", "Skip"),
    ("resolve_generic", "Skip for {card}"),
    ("resolve_generic", "Choose for {card}"),
    ("resolve_generic", "Resolve pending choice"),
]

_RESOURCES = ("power", "influence")
_ASPECTS = ("obedience", "guile", "ambition", "conquest", "malice")
_ZONES = ("played", "hand", "discard")
_ILLEGAL_SUFFIX = " [ILLEGAL MOVE]"

# Mirror describe.c `_humanize_id` (first char uppercased, underscores to spaces).
def _humanize(node_id: str) -> str:
    out: list[str] = []
    for i, ch in enumerate(node_id):
        if ch == "_":
            out.append(" ")
        elif i == 0:
            out.append(ch.upper())
        else:
            out.append(ch)
    return "".join(out)


def _load_card_names(cards_dir: Path) -> list[str]:
    payload = assemble_catalog_payload(cards_dir)
    names: set[str] = set()
    for entry in payload.get("cards", []):
        if not isinstance(entry, dict):
            continue
        if not entry.get("card_id"):
            continue
        name = entry.get("name")
        if name:
            names.add(str(name))
    return sorted(names, key=len, reverse=True)


def _load_node_labels(board_path: Path) -> list[str]:
    data = json.loads(board_path.read_text(encoding="utf-8"))
    labels: set[str] = set()
    for node in data.get("nodes", []):
        nid = node.get("node_id")
        if nid:
            labels.add(_humanize(str(nid)))
    return sorted(labels, key=len, reverse=True)


def _make_token_re(tokens: tuple[str, ...]) -> re.Pattern[str] | None:
    if not tokens:
        return None
    escaped = sorted({re.escape(t) for t in tokens}, key=len, reverse=True)
    return re.compile(r"\b(?:" + "|".join(escaped) + r")\b", re.IGNORECASE)


class LabelTemplater:
    """Reduce a concrete legal-move label to a stable template string."""

    def __init__(self, card_names: list[str], node_labels: list[str], player_labels: list[str]) -> None:
        self._card_names = card_names
        self._node_labels = node_labels
        self._player_labels = player_labels
        self._resource_re = _make_token_re(_RESOURCES)
        self._aspect_re = _make_token_re(_ASPECTS)

    def template(self, label: str) -> str:
        text = label
        if text.endswith(_ILLEGAL_SUFFIX):
            text = text[: -len(_ILLEGAL_SUFFIX)]

        for name in self._card_names:
            text = text.replace(name, "{card}")
        for node in self._node_labels:
            text = text.replace(node, "{node}")
        for player in self._player_labels:
            text = text.replace(player, "{player}")

        if self._resource_re:
            text = self._resource_re.sub("{resource}", text)
        if self._aspect_re:
            text = self._aspect_re.sub("{aspect}", text)

        # Zones appear only in "(played)" / "(hand)" / "(discard)" and
        # "from <zone>"; avoid over-matching words like "discard" in "Force discard".
        for zone in _ZONES:
            text = text.replace("(" + zone + ")", "({zone})")
            text = text.replace("from " + zone, "from {zone}")

        text = re.sub(r"\d+", "{n}", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text


_PICK_WEIGHTS = {
    "recruit": 8.0,
    "play_card": 6.0,
    "resolve_generic": 5.0,
    "activate_ability": 5.0,
    "promote_card": 5.0,
    "decline_ability": 3.0,
    "skip_promote": 3.0,
}


def _collect_playout(session, templater: LabelTemplater, sink: dict, rng: Random, max_steps: int) -> None:
    """Walk a session forward, recording every legal-move label seen."""
    for _ in range(max_steps):
        if session.is_terminal():
            break
        view = build_c_game_view(session)
        moves = view.legal_moves
        if not moves:
            break
        for move in moves:
            label = move.label
            if label.endswith(_ILLEGAL_SUFFIX):
                label = label[: -len(_ILLEGAL_SUFFIX)]
            key = (move.move_type, templater.template(label))
            examples = sink.setdefault(key, [])
            if label not in examples:
                examples.append(label)

        weights = [_PICK_WEIGHTS.get(m.move_type, 1.0) for m in moves]
        picked = rng.choices(moves, weights=weights, k=1)[0]
        if session.submit_move(picked.move) is not None:
            continue
        # Fall back to end_main_phase, which should always be legal.
        fallback = next((m for m in moves if m.move_type == "end_main_phase"), None)
        if fallback is not None and session.submit_move(fallback.move) is not None:
            continue
        break


def _collect_random_game(engine, player_ids: list[str], seed: int, max_steps: int,
                         templater: LabelTemplater, sink: dict, rng: Random) -> None:
    session = CSession(engine, list(player_ids), seed)
    try:
        _collect_playout(session, templater, sink, rng, max_steps)
    finally:
        session.destroy()


def _collect_scenarios(engine, scenarios_dir: Path, templater: LabelTemplater,
                       sink: dict, rng: Random, max_scenarios: int, steps_per_scenario: int) -> tuple[int, int]:
    loaded = 0
    skipped = 0
    for path in sorted(scenarios_dir.rglob("*.json")):
        if max_scenarios and loaded >= max_scenarios:
            break
        try:
            session = CSession.load(str(path), engine=engine)
        except Exception:
            skipped += 1
            continue
        try:
            if session.is_terminal():
                session.destroy()
                continue
            _collect_playout(session, templater, sink, rng, steps_per_scenario)
            loaded += 1
        finally:
            session.destroy()
    return loaded, skipped


def _write_xlsx(rows: list[dict], path: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    headers = ["Move Type", "Template", "Example 1", "Example 2", "Example 3", "Distinct Labels", "Source"]

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Move Label Templates"

    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    for column_index, header in enumerate(headers, 1):
        cell = worksheet.cell(row=1, column=column_index, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for row_index, row in enumerate(rows, 2):
        worksheet.cell(row=row_index, column=1, value=row["move_type"])
        worksheet.cell(row=row_index, column=2, value=row["template"])
        examples = row["examples"]
        for i in range(3):
            worksheet.cell(row=row_index, column=3 + i, value=examples[i] if i < len(examples) else None)
        worksheet.cell(row=row_index, column=6, value=len(examples))
        worksheet.cell(row=row_index, column=7, value=row["source"])

    widths = {"Move Type": 22, "Template": 48, "Example 1": 40, "Example 2": 40, "Example 3": 40,
              "Distinct Labels": 12, "Source": 14}
    for header in headers:
        letter = worksheet.cell(row=1, column=headers.index(header) + 1).column_letter
        worksheet.column_dimensions[letter].width = widths[header]

    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions
    workbook.save(str(path))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Catalog legal-move label templates with filled examples.")
    parser.add_argument("--board-path", default=str(DEFAULT_BOARD), help="Board JSON (default: data/boards/tyrants_of_the_underdark.json)")
    parser.add_argument("--card-path", default=str(DEFAULT_CARDS), help="Card directory (default: data/cards)")
    parser.add_argument("--scenarios-dir", default=str(DEFAULT_SCENARIOS), help="Scenario directory to mine (default: data/scenarios)")
    parser.add_argument("--no-scenarios", action="store_true", help="Skip scenario mining (random games only)")
    parser.add_argument("--max-scenarios", type=int, default=0, help="Cap scenario files mined (0 = all)")
    parser.add_argument("--steps-per-scenario", type=int, default=8, help="Moves to play out from each scenario (default: 8)")
    parser.add_argument("--num-games", type=int, default=60, help="Random games to run (default: 60)")
    parser.add_argument("--max-steps", type=int, default=400, help="Max steps per random game (default: 400)")
    parser.add_argument("--seed", type=int, default=1, help="Base seed for random games (default: 1)")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output .xlsx path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    board_path = Path(args.board_path)
    cards_dir = Path(args.card_path)
    output = Path(args.output)

    card_names = _load_card_names(cards_dir)
    node_labels = _load_node_labels(board_path)
    player_labels = [f"Player {i}" for i in range(1, 9)] + [f"P{i}" for i in range(1, 9)]
    player_labels.sort(key=len, reverse=True)
    templater = LabelTemplater(card_names, node_labels, player_labels)

    if CEngine is None or CSession is None or build_c_game_view is None:
        print("C engine bindings are unavailable (engine_c.dll not built?).", file=sys.stderr)
        return 1

    engine = CEngine()
    engine.initialize(catalog_path=str(cards_dir), board_path=str(board_path))

    sink: dict[tuple[str, str], list[str]] = OrderedDict()

    player_counts = [2, 3, 4]
    per_count = max(1, args.num_games // len(player_counts))
    total_games = 0
    rng = Random(args.seed)
    for count in player_counts:
        for _i in range(per_count):
            seed = args.seed * 1_000_003 + total_games * 7919 + count * 101
            player_ids = [f"p{j + 1}" for j in range(count)]
            _collect_random_game(engine, player_ids, seed, args.max_steps, templater, sink, rng)
            total_games += 1

    loaded_scenarios = 0
    skipped_scenarios = 0
    if not args.no_scenarios:
        loaded_scenarios, skipped_scenarios = _collect_scenarios(
            engine, Path(args.scenarios_dir), templater, sink, rng, args.max_scenarios, args.steps_per_scenario
        )

    # Merge static templates, then build final rows sorted by (move_type, template).
    all_keys: set[tuple[str, str]] = set(sink.keys()) | set(STATIC_TEMPLATES)
    rows: list[dict] = []
    for key in sorted(all_keys):
        move_type, template = key
        examples = sink.get(key, [])
        source = "observed" if examples else "static-only"
        rows.append({"move_type": move_type, "template": template, "examples": examples, "source": source})

    output.parent.mkdir(parents=True, exist_ok=True)
    _write_xlsx(rows, output)

    observed_templates = sum(1 for r in rows if r["source"] == "observed")
    print(f"Games run: {total_games}")
    print(f"Scenarios mined: {loaded_scenarios} (skipped {skipped_scenarios})")
    print(f"Templates: {len(rows)} total ({observed_templates} observed, "
          f"{len(rows) - observed_templates} static-only)")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
