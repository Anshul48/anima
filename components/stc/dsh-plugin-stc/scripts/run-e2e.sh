#!/bin/sh
# Run an STC e2e spec inside a DSH checkout's workspace vitest.
# Usage: sh scripts/run-e2e.sh /path/to/deepseek-harness [vitest args...]
# Env: STC_ROOT (default: this checkout), SST_SRC, PROMPT_KIT, SPEC_FILE
# (default: stc-bundle.e2e.spec.ts), POLICY_RESULTS (battery output JSONL),
# PATH must include node 22 + pnpm (see docs/STC-DSH-RECORD.md).
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
DSH=${1:?usage: run-e2e.sh /path/to/deepseek-harness [vitest args...]}
shift || true
SPEC_FILE="${SPEC_FILE:-stc-bundle.e2e.spec.ts}"
DEST="$DSH/packages/shell/tool-bash/tests/$SPEC_FILE"
if [ ! -d "$DSH/packages/shell/tool-bash/tests" ]; then
  echo "not a DSH checkout: $DSH" >&2; exit 2
fi
cp "$ROOT/tests/e2e/$SPEC_FILE" "$DEST"
export STC_ROOT="${STC_ROOT:-$(cd "$ROOT/.." && pwd)}"
# Rewrite in-repo plugin imports to absolute paths valid at the destination.
sed -i "s#'../../src/#'$STC_ROOT/dsh-plugin-stc/src/#g" "$DEST"
export SST_SRC="${SST_SRC:-/mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/sst/src}"
export PROMPT_KIT="${PROMPT_KIT:-/mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/prompt-kit}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-/tmp/toolchain/xdg-cache}"
export XDG_DATA_HOME="${XDG_DATA_HOME:-/tmp/toolchain/xdg-data}"
export XDG_STATE_HOME="${XDG_STATE_HOME:-/tmp/toolchain/xdg-state}"
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-/tmp/toolchain/xdg-config}"
export COREPACK_HOME="${COREPACK_HOME:-/tmp/toolchain/corepack-home}"
cd "$DSH"
status=0
pnpm vitest run "packages/shell/tool-bash/tests/$SPEC_FILE" "$@" || status=$?
rm -f "$DEST"
exit "$status"
