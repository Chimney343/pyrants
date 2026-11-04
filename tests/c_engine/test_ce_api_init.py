"""Regression tests for the CEngine global-initialization contract.

``CEngine.available()`` and ``CEngine.initialize()`` share one initialization
path: intern the symbol table and register the default effect/action/selection
handlers exactly once. These tests replace ``_lib`` with a recorder so they
observe the contract without touching the real native globals.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine_c.bindings import ce_api  # noqa: E402


class _RecordingLib:
    def __init__(self):
        self.calls = []

    def intern_init(self, size: int) -> None:
        self.calls.append(("intern_init", size))

    def register_default_effects(self) -> None:
        self.calls.append(("register_default_effects",))


class _FailingEffectsLib(_RecordingLib):
    def register_default_effects(self) -> None:
        raise RuntimeError("registration failed")


def test_available_registers_effects_once(monkeypatch):
    fake = _RecordingLib()
    monkeypatch.setattr(ce_api, "_lib", fake)
    monkeypatch.setattr(ce_api.CEngine, "_globally_initialized", False)

    assert ce_api.CEngine.available() is True
    assert ce_api.CEngine.available() is True

    assert fake.calls == [
        ("intern_init", 4096),
        ("register_default_effects",),
    ]


def test_available_leaves_flag_false_when_registration_fails(monkeypatch):
    fake = _FailingEffectsLib()
    monkeypatch.setattr(ce_api, "_lib", fake)
    monkeypatch.setattr(ce_api.CEngine, "_globally_initialized", False)

    assert ce_api.CEngine.available() is False
    assert ce_api.CEngine._globally_initialized is False
