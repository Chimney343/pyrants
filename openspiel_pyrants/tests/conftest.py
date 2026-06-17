"""Shared fixtures for openspiel_pyrants tests."""

from __future__ import annotations

import ctypes
import os
import pytest


@pytest.fixture(scope="session")
def _c_engine_available():
    """Check if the engine_c DLL can be loaded."""
    dll_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "engine_c", "engine_c.dll"
    )
    dll_path = os.path.abspath(dll_path)
    if not os.path.exists(dll_path):
        return False
    try:
        _lib = ctypes.CDLL(dll_path)
        _lib.intern_init(4096)
        return True
    except Exception:
        return False


@pytest.fixture
def requires_c_engine(_c_engine_available):
    if not _c_engine_available:
        pytest.skip("engine_c DLL not available")
