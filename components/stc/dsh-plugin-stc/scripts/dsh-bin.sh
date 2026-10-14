#!/bin/sh
# dsh_bin wrapper for SDK-driven qualification (test fixture, not release).
# Env overrides (defaults = scratch install):
#   DSH_CHECKOUT, STC_TOOLCHAIN, STC_COREPACK_HOME, STC_XDG_CACHE, STC_XDG_DATA
set -eu
TC="${STC_TOOLCHAIN:-/tmp/toolchain/node22/bin}"
export PATH="$TC:$PATH"
export COREPACK_HOME="${STC_COREPACK_HOME:-/tmp/toolchain/corepack-home}"
export XDG_CACHE_HOME="${STC_XDG_CACHE:-/tmp/toolchain/xdg-cache}"
export XDG_DATA_HOME="${STC_XDG_DATA:-/tmp/toolchain/xdg-data}"
cd "${DSH_CHECKOUT:-/tmp/dsh-upstream}"
exec pnpm dsh "$@"
