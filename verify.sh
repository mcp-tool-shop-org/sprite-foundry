#!/usr/bin/env bash
set -euo pipefail

echo "=== Sprite Foundry — verify ==="

FAIL=0

# 1. Python module imports
echo "Checking Python module imports..."
python -c "from foundry import db; from foundry import cli; print('OK: foundry module imports')" || { echo "FAIL: foundry module import"; FAIL=1; }

# 2. Database schema
echo "Checking database constants..."
python -c "
from foundry.db import DIRECTIONS, LIFECYCLE_STATES, SCHEMA_VERSION
assert len(DIRECTIONS) == 8, f'Expected 8 directions, got {len(DIRECTIONS)}'
assert SCHEMA_VERSION >= 2, f'Schema version {SCHEMA_VERSION} too old'
print(f'OK: {len(DIRECTIONS)} directions, {len(LIFECYCLE_STATES)} states, schema v{SCHEMA_VERSION}')
" || { echo "FAIL: database constants"; FAIL=1; }

# 3. CLI parser builds without error
echo "Checking CLI parser..."
python -c "from foundry.cli import build_parser; p = build_parser(); print('OK: CLI parser builds')" || { echo "FAIL: CLI parser"; FAIL=1; }

# 4. Export packs structure
echo "Checking export packs..."
PACK_COUNT=0
PACK_ERRORS=0
for manifest in exports/*/manifest.json exports/*/*/manifest.json; do
    [ -f "$manifest" ] || continue
    PACK_COUNT=$((PACK_COUNT + 1))
    pack_dir=$(dirname "$manifest")

    # Check required directories
    for subdir in albedo normal depth; do
        if [ ! -d "$pack_dir/$subdir" ]; then
            echo "  MISSING: $pack_dir/$subdir"
            PACK_ERRORS=$((PACK_ERRORS + 1))
        fi
    done

    # Check albedo has 8 files
    albedo_count=$(find "$pack_dir/albedo" -name "*.png" 2>/dev/null | wc -l)
    if [ "$albedo_count" -ne 8 ]; then
        echo "  WRONG COUNT: $pack_dir/albedo has $albedo_count PNGs (expected 8)"
        PACK_ERRORS=$((PACK_ERRORS + 1))
    fi

    # Validate manifest JSON
    python -c "import json; json.load(open('$manifest'))" 2>/dev/null || {
        echo "  INVALID JSON: $manifest"
        PACK_ERRORS=$((PACK_ERRORS + 1))
    }
done

echo "  Packs checked: $PACK_COUNT"
if [ "$PACK_ERRORS" -gt 0 ]; then
    echo "  FAIL: $PACK_ERRORS pack errors"
    FAIL=1
else
    echo "  OK: all packs valid"
fi

# 5. Roster index
echo "Checking roster index..."
if [ -f "exports/roster_index.json" ]; then
    python -c "
import json
with open('exports/roster_index.json') as f:
    idx = json.load(f)
print(f'OK: roster_index.json — {idx[\"total_packs\"]} packs')
" || { echo "FAIL: roster_index.json parse"; FAIL=1; }
else
    echo "WARN: exports/roster_index.json not found (non-blocking)"
fi

# 6. Required files
echo "Checking required files..."
for f in README.md LICENSE CHANGELOG.md SECURITY.md; do
    if [ -f "$f" ]; then
        echo "  OK: $f"
    else
        echo "  FAIL: $f missing"
        FAIL=1
    fi
done

echo ""
if [ "$FAIL" -eq 0 ]; then
    echo "All checks passed."
else
    echo "Some checks failed."
    exit 1
fi
