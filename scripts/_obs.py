"""Observability helpers for ``scripts/run_ismcts.py``.

Provides structured-logging wiring and an in-memory metrics collector
that is dumped as ``metrics.json`` at the end of the run.  Kept in a
separate file so it can be tested without pulling in the full IS-MCTS
pipeline and its side-effect imports.
"""

from __future__ import annotations

import logging
import math
import os
import random
import sys
import uuid
from dataclasses import dataclass, field


def new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def configure_logging(*, level: str, json_logs: bool, run_id: str) -> None:
    import structlog

    processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer = (
        structlog.processors.JSONRenderer()
        if json_logs
        else _multiline_console_renderer
    )
    processors.append(renderer)

    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory()
        if not json_logs
        else structlog.PrintLoggerFactory(sys.stderr),
        wrapper_class=structlog.BoundLogger,
        cache_logger_on_first_use=True,
    )
    structlog.contextvars.bind_contextvars(run_id=run_id)

    # Squelch noisy loggers
    logging.getLogger("pyspiel").setLevel(logging.WARNING)
    logging.getLogger("open_spiel").setLevel(logging.WARNING)


def bind_worker_context(game_index: int, worker_pid: int) -> None:
    import structlog

    structlog.contextvars.bind_contextvars(game_index=game_index, worker_pid=worker_pid)


# ---------------------------------------------------------------------------
# Custom console renderer — one key=value per line
# ---------------------------------------------------------------------------

_LEVEL_COLORS = {
    "debug": "\033[36m",     # cyan
    "info": "\033[32m",      # green
    "warning": "\033[33m",   # yellow
    "error": "\033[31m",     # red
    "critical": "\033[1;31m",  # bold red
}
_RESET = "\033[0m"
_GREY = "\033[90m"


def compute_percentiles(values: list[float]) -> dict[str, float]:
    """Return p50/p90/p95/p99 percentiles for a list of floats."""
    if not values:
        return {"p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0}
    s = sorted(values)
    n = len(s)
    return {
        "p50": s[math.floor(n * 0.50)],
        "p90": s[math.floor(n * 0.90)],
        "p95": s[math.floor(n * 0.95)],
        "p99": s[min(n - 1, math.floor(n * 0.99))],
    }


def _multiline_console_renderer(_logger, _method_name, event_dict: dict) -> str:
    timestamp = event_dict.pop("timestamp", "")
    level = event_dict.pop("level", "info")
    event = event_dict.pop("event", "")
    run_id = event_dict.pop("run_id", "")

    color = _LEVEL_COLORS.get(level, "")
    header = f"{_GREY}{timestamp}{_RESET} {color}[{level:<7}]{_RESET} {event}"
    if run_id:
        header += f"  {_GREY}#{run_id}{_RESET}"

    lines = [header]
    for key, value in event_dict.items():
        if isinstance(value, float):
            value = f"{value:.1f}"
        lines.append(f"  {_GREY}{key}{_RESET}={value}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# RunMetrics — in-process metrics collector
# --------------------------------------------------------------------------


@dataclass
class RunMetrics:
    moves_total: int = 0
    games_completed: int = 0
    games_failed: int = 0
    worker_exceptions: int = 0
    simulation_seconds_total: float = 0.0
    games_truncated: int = 0

    _move_latency_ms: list[float] = field(default_factory=list)
    _game_wall_sec: list[float] = field(default_factory=list)
    decisions_by_phase: dict[str, int] = field(default_factory=dict)

    _MAX_MOVE_SAMPLES: int = 4096

    def record_move_latency(self, wall_ms: float, phase: str) -> None:
        self.moves_total += 1
        self.decisions_by_phase[phase] = self.decisions_by_phase.get(phase, 0) + 1
        buf = self._move_latency_ms
        if len(buf) < self._MAX_MOVE_SAMPLES:
            buf.append(wall_ms)
        else:
            idx = random.randint(0, self.moves_total - 1)
            if idx < self._MAX_MOVE_SAMPLES:
                buf[idx] = wall_ms

    def record_game_wall(self, wall_sec: float) -> None:
        self._game_wall_sec.append(wall_sec)

    def record_game_truncated(self) -> None:
        self.games_truncated += 1

    def _percentiles(self, values: list[float]) -> dict[str, float]:
        return compute_percentiles(values)

    def to_jsonable(self) -> dict:
        cpu_count = os.cpu_count() or 1
        total_wall = sum(self._game_wall_sec)
        return {
            "counters": {
                "moves_total": self.moves_total,
                "games_completed": self.games_completed,
                "games_failed": self.games_failed,
                "worker_exceptions": self.worker_exceptions,
                "simulation_seconds_total": round(self.simulation_seconds_total, 3),
                "games_truncated": self.games_truncated,
            },
            "latency": {
                "move_latency_ms": {
                    "count": len(self._move_latency_ms),
                    **self._percentiles(self._move_latency_ms),
                },
                "game_wall_sec": {
                    "count": len(self._game_wall_sec),
                    **self._percentiles(self._game_wall_sec),
                },
                "sims_per_sec_avg_overall": (
                    round(self.moves_total / total_wall, 1) if total_wall > 0 else 0.0
                ),
            },
            "saturation": {
                "cpu_count": cpu_count,
                "total_games": self.games_completed + self.games_failed,
                "total_wall_sec": round(total_wall, 3),
            },
            "breakdown": {
                "decisions_by_phase": self.decisions_by_phase,
            },
        }
