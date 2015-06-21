#!/bin/bash

set -o errexit -o nounset

# Allow this script to be run from any directory for convenience.
cd "$(dirname "$0")"

# Add switch_mod to PYTHONPATH for convenience.
export PYTHONPATH="$(pwd):${PYTHONPATH:-}"

# The doctests expect to be run from the "switch_mod" directory in
# order to find test_dat.
cd switch_mod

failed=0
for module in $(find . -name "*.py" | sort); do
  echo "$module"
  if ! python -m doctest "$module"; then
    failed=1
  fi
done

if [ $failed = 0 ]; then
  echo PASS
else
  echo FAIL
fi
exit $failed
