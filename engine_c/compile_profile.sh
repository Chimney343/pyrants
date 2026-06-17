#!/bin/bash
# WSL profiling build script for engine_c.
# Compiles with gcc -pg (profiling) and links into profile_runner.
# Usage: wsl -e bash engine_c/compile_profile.sh [release|debug]

set -euo pipefail

PROJECT_ROOT="/mnt/c/Users/mkkom/pyrants"
cd "$PROJECT_ROOT/engine_c"

BUILD_TYPE="${1:-release}"

CFLAGS="-std=c11 -Wall -Wextra -fPIC -DPROFILE_BUILD"
LDFLAGS=""

if [ "$BUILD_TYPE" = "debug" ]; then
    CFLAGS="$CFLAGS -g -O0 -pg"
    LDFLAGS="-pg"
else
    CFLAGS="$CFLAGS -g -O2 -pg"
    LDFLAGS="-pg"
fi

# Exclude test files and cJSON (linked as object)
SRCS="intern.c arena.c rng.c state.c moves.c rules.c helpers.c \
      phases.c scoring.c generic_runtime.c actions.c selection.c \
      player_view.c loader.c cJSON.c"

OBJ_DIR="build_profile"
mkdir -p "$OBJ_DIR"

echo "=== Compiling with gcc -pg ($BUILD_TYPE) ==="
OBJS=""
for src in $SRCS; do
    obj="$OBJ_DIR/${src%.c}.o"
    echo "  $src"
    gcc -c $CFLAGS "$src" -o "$obj"
    OBJS="$OBJS $obj"
done

echo "  profile_runner.c"
gcc -c $CFLAGS profile_runner.c -o "$OBJ_DIR/profile_runner.o"

echo "=== Linking profile_runner ==="
gcc $LDFLAGS $OBJS "$OBJ_DIR/profile_runner.o" -o "$OBJ_DIR/profile_runner"

echo "=== Build complete: engine_c/build_profile/profile_runner ==="
