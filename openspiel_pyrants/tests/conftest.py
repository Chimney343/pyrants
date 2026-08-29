"""Shared fixtures for openspiel_pyrants tests."""

from __future__ import annotations

import ctypes
import os

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
    dll_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "engine_c", "engine_c.dll"
    )
    dll_path = os.path.abspath(dll_path)
    if not os.path.exists(dll_path):
        return False
    try:
        ctypes.CDLL(dll_path)
        return True
    except OSError:
        return False


@pytest.fixture
def requires_c_engine(_c_engine_available):
    if not _c_engine_available:
        pytest.skip("engine_c DLL not available")
