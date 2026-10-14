#!/bin/sh
# Migrate the STC-on-DSH scratch install (/tmp/toolchain, /tmp/dsh-upstream)
# to durable user-owned WSL locations. Idempotent; verifies each step.
# Requires home-directory writes (currently sandbox-denied: run after the
# approval-capable restart, or with equivalent permission).
#
# Layout (canonical):
#   ~/dsh                        pinned DSH checkout (see ../DSH_PIN)
#   ~/.local/share/stc/toolchain node22, pnpm store, corepack/XDG homes, browsers
#   ~/.local/share/stc/homes     DSH homes (profiles, sessions)
#   ~/.local/share/stc/runs      default STC_DSH_STORE
set -eu

PIN_COMMIT=$(sed -n '1p' "$(dirname "$0")/../DSH_PIN")
DSH_DEST=${DSH_DEST:-"$HOME/dsh"}
TC_DEST=${TC_DEST:-"$HOME/.local/share/stc/toolchain"}
ST_DEST=${ST_DEST:-"$HOME/.local/share/stc"}

echo "== dirs =="
mkdir -p "$TC_DEST" "$ST_DEST/homes" "$ST_DEST/runs"

if [ -d /tmp/toolchain/node22 ]; then
  echo "== toolchain copy =="
  for d in node22 corepack-home pnpm-store xdg-cache xdg-data xdg-state xdg-config; do
    [ -d "/tmp/toolchain/$d" ] && cp -rn "/tmp/toolchain/$d" "$TC_DEST/" || true
  done
  for f in SHASUMS256.txt node.tar.xz; do
    [ -f "/tmp/toolchain/$f" ] && cp -n "/tmp/toolchain/$f" "$TC_DEST/" || true
  done
  [ -d /tmp/toolchain/chrome-headless-shell-linux64 ] && cp -rn /tmp/toolchain/chrome-headless-shell-linux64 "$TC_DEST/" || true
  [ -d /tmp/firefox ] && cp -rn /tmp/firefox "$TC_DEST/" || true
  "$TC_DEST/node22/bin/node" --version
else
  echo "no /tmp/toolchain/node22; skipping copy (fresh provision needed)"
fi

if [ ! -d "$DSH_DEST/.git" ]; then
  echo "== DSH clone @ $PIN_COMMIT =="
  git clone https://github.com/deepseek-ai/deepseek-harness "$DSH_DEST"
  git -C "$DSH_DEST" checkout "$PIN_COMMIT"
else
  echo "DSH checkout exists: $(git -C "$DSH_DEST" rev-parse --short HEAD)"
fi

echo "== DSH install + build =="
export PATH="$TC_DEST/node22/bin:$PATH"
export COREPACK_HOME="$TC_DEST/corepack-home"
export XDG_CACHE_HOME="$TC_DEST/xdg-cache"
export XDG_DATA_HOME="$TC_DEST/xdg-data"
cd "$DSH_DEST"
pnpm install --frozen-lockfile
pnpm run build
pnpm dsh --version
export DSH_HOME="$ST_DEST/homes/smoke"
pnpm dsh --profile web --dump-config 2>/dev/null | grep -c "^- id:" || true

echo
echo "== canonical env =="
echo "export PATH=\"$TC_DEST/node22/bin:\$PATH\""
echo "export COREPACK_HOME=\"$TC_DEST/corepack-home\""
echo "export XDG_CACHE_HOME=\"$TC_DEST/xdg-cache\""
echo "export XDG_DATA_HOME=\"$TC_DEST/xdg-data\""
echo "export DSH_HOME=\"$ST_DEST/homes/<profile-home>\""
echo "export STC_DSH_STORE=\"$ST_DEST/runs\""
echo "durable migration complete"
