"""Assert that Python ctypes mirrors match the C engine's memory layout.

The engine exports ``engine_layout_size(type)`` and
``engine_layout_offset(type, field)`` from a table built with ``sizeof`` and
``offsetof``. ``assert_layout`` compares every mirrored ctypes struct against
that table; ``engine_bindings`` calls it once at import, so a stale DLL or a
drifted mirror fails before any state is read through it.
"""

from __future__ import annotations

import ctypes

_MISSING_SIZE = ctypes.c_size_t(-1).value


class LayoutMismatch(RuntimeError):
    """Raised when a Python ctypes mirror disagrees with the C layout table."""


def assert_layout(lib, specs) -> None:
    """Check every ``{c_name: ctypes_type}`` pair against *lib*.

    Raises ``LayoutMismatch`` with the struct/field, both sizes or offsets, and
    a rebuild hint. A missing export or an unknown struct/field is a mismatch,
    not a silent pass.
    """
    for type_name, cls in specs.items():
        expected_size = ctypes.sizeof(cls)
        actual_size = int(lib.engine_layout_size(type_name.encode("ascii")))
        if actual_size == _MISSING_SIZE:
            raise LayoutMismatch(
                f"C layout probe has no size for {type_name}; "
                "rebuild engine_c.dll with 'just build-c'"
            )
        if actual_size != expected_size:
            raise LayoutMismatch(
                f"{type_name}: C size {actual_size} != Python size {expected_size}; "
                "update the ctypes mirror or rebuild engine_c.dll"
            )

        for field_name, _field_type in cls._fields_:
            expected_offset = getattr(cls, field_name).offset
            actual_offset = int(
                lib.engine_layout_offset(
                    type_name.encode("ascii"), field_name.encode("ascii")
                )
            )
            if actual_offset != expected_offset:
                raise LayoutMismatch(
                    f"{type_name}.{field_name}: C offset {actual_offset} "
                    f"!= Python offset {expected_offset}; "
                    "update the ctypes mirror or rebuild engine_c.dll"
                )
