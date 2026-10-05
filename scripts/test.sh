#!/bin/sh
set -eu
python -m pytest tests -q
for name in common landing workspace portal; do node --check "web/assets/$name.js"; done
node tests/frontend_test.cjs
