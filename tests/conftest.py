"""Shared fixtures for the top-level tests package."""

from __future__ import annotations

import ctypes
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def _c_engine_available():
    """Check if the engine_c DLL can be loaded.

    Note: do NOT call ``intern_init`` here — the intern table is global C
    state owned by ``CEngine.initialize()`` (guarded by
    ``_globally_initialized``). Re-initializing it here would wipe Syms
    referenced by any already-loaded game definition and corrupt the C
    engine for every subsequent test in the session.
    """
    dll_path = Path(__file__).resolve().parents[1] / "engine_c" / "engine_c.dll"
    if not dll_path.exists():
        return False
    try:
        ctypes.CDLL(str(dll_path))
        return True
    except OSError:
        return False


@pytest.fixture
def requires_c_engine(_c_engine_available):
    if not _c_engine_available:
        pytest.skip("engine_c DLL not available")
