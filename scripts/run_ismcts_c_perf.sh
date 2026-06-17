#!/bin/bash
# WSL IS-MCTS C engine profiling script.
# Compiles with gprof instrumentation, runs benchmark, analyzes.
# Usage: wsl -e bash scripts/run_ismcts_c_perf.sh [top_n]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENGINE_DIR="$PROJECT_DIR/engine_c"
BUILD_DIR="$ENGINE_DIR/build_profile"
ARTIFACTS_DIR="$PROJECT_DIR/artifacts/ismcts_c/performance_testing"
TOP_N="${1:-30}"

echo "=== Building C engine with gprof instrumentation ==="
cd "$ENGINE_DIR"
bash compile_profile.sh release

echo ""
echo "=== Running profile_runner ==="
mkdir -p "$ARTIFACTS_DIR"
cd "$BUILD_DIR"
./profile_runner
if [ -f gmon.out ]; then
    cp gmon.out "$ARTIFACTS_DIR/gmon.out"
    echo "gmon.out saved to artifacts/ismcts_c/performance_testing/"
else
    echo "ERROR: gmon.out not generated"
    exit 1
fi

echo ""
echo "=== gprof flat profile (top $TOP_N) ==="
cd "$ARTIFACTS_DIR"
gprof "$BUILD_DIR/profile_runner" gmon.out > gprof_flat.txt
head -n "$TOP_N" gprof_flat.txt
echo ""
echo "=== gprof call graph (top $TOP_N) ==="
gprof -q "$BUILD_DIR/profile_runner" gmon.out > gprof_callgraph.txt
head -n "$TOP_N" gprof_callgraph.txt
echo ""
echo "Full reports at: artifacts/ismcts_c/performance_testing/"
echo "  gprof_flat.txt      — flat profile"
echo "  gprof_callgraph.txt  — call graph"
