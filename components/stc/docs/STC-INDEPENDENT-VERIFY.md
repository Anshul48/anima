# STC independent verification procedure (release gate)

Independent party re-runs these against the frozen candidate WITHOUT
reusing the builder's shell history or /tmp artifacts (fresh DSH_HOME,
fresh workdirs). All quota-free ($0). Versions: node 22.23.3, pnpm
11.7.0, DSH pin 639ed01, SST pin df78f42 (amended 2026-10-04), mypy strict 2.3.1.

Env (per command unless noted):

```sh
export STC_ROOT=/path/to/stc
export PATH=/tmp/toolchain/node22/bin:$PATH
export COREPACK_HOME=/tmp/toolchain/corepack-home
export XDG_DATA_HOME=/tmp/stc-xdg/data XDG_CACHE_HOME=/tmp/stc-xdg/cache
export PYTHONDONTWRITEBYTECODE=1 no_proxy='*' NO_PROXY='*'
unset http_proxy https_proxy all_proxy ftp_proxy \
  HTTP_PROXY HTTPS_PROXY ALL_PROXY FTP_PROXY
```

## 1. Static gates

```sh
cd $STC_ROOT
.venv/bin/ruff check . && .venv/bin/ruff format --check .
export MYPY_CACHE_DIR=/tmp/stc-mypy   # never pollute the lease
PYTHONPATH=/tmp/sst-pin-df78f42/src:/tmp/prompt-kit-pin-4f442a6 \
MYPYPATH=/tmp/prompt-kit-pin-4f442a6 \
  .venv/bin/python -m mypy src tests   # expect: 0 errors, 83 files
```

## 2. Backend suite (pristine SST pin)

```sh
export MYPY_CACHE_DIR=/tmp/stc-mypy   # never pollute the lease (also §1)
export STC_SST_ROOT=/tmp/sst-pin-df78f42
export STC_PROMPT_KIT_ROOT=/tmp/prompt-kit-pin-4f442a6
export MYPYPATH=/tmp/prompt-kit-pin-4f442a6  # in-lease mypy gate resolves the pin
PYTHONPATH=/tmp/sst-pin-df78f42/src:/tmp/prompt-kit-pin-4f442a6 \
  .venv/bin/python -m pytest tests -q -p no:cacheprovider -m "not live" \
  > /tmp/stc-verify-suite.log 2>&1; echo "PYTEST_RC=$?"
# expect: RC 0, all pass; retain the full log (do not tail it away)
```

Live-marked nodes (`-m live`: codex/agy CLI-harness tests) are
deselected in gate runs per D13 and run only as an informational
operator leg with a healthy harness + quota; quota/network failures
there are environmental, not release-blocking. Run them explicitly
when the harness is healthy:

```sh
PYTHONPATH=/tmp/sst-pin-df78f42/src:/tmp/prompt-kit-pin-4f442a6 \
  .venv/bin/python -m pytest tests -q -p no:cacheprovider -m live
# expect with healthy harness: pass; with exhausted quota: honest
# fail-closed (remediation text), recorded as env-blocked
```

Pristine pins (exact-HEAD detached clones; dirty siblings fail closed).
`prove_import_integrity` requires clone-form pins (`.git` + `HEAD ==
pin` + spot-hash vs pin blobs); archive extracts fail the lease gate.
Exact hashes in docs/STC-SST-CALLER-CONTRACT.md.

```sh
rm -rf /tmp/sst-pin-df78f42 /tmp/prompt-kit-pin-4f442a6
git clone /path/to/sst /tmp/sst-pin-df78f42
git -C /tmp/sst-pin-df78f42 checkout --detach df78f42894a65c48f524337a498032617689a013
git clone /path/to/prompt-kit /tmp/prompt-kit-pin-4f442a6
git -C /tmp/prompt-kit-pin-4f442a6 checkout --detach 4f442a6c829bc06b60f9979fdc8d7585e30bac9a
test -z "$(git -C /tmp/sst-pin-df78f42 status --porcelain)" || echo "SST PIN DIRTY"
test -z "$(git -C /tmp/prompt-kit-pin-4f442a6 status --porcelain)" || echo "PK PIN DIRTY"
```

## 3. Plugin units + e2e + probe

```sh
cd $STC_ROOT/dsh-plugin-stc
node --test tests/*.test.ts                       # expect 99/99
export SST_SRC=/tmp/sst-pin-df78f42/src
sh scripts/run-e2e.sh /tmp/dsh-upstream           # expect 7/7
for s in policy-battery stc-brief stc-recovery demo-manual-task; do
  SPEC_FILE=$s.e2e.spec.ts sh scripts/run-e2e.sh /tmp/dsh-upstream
done                                              # expect 3+2+3+1
cd $STC_ROOT
PYTHONPATH=/tmp/sst-pin-df78f42/src:/tmp/prompt-kit-pin-4f442a6 \
.venv/bin/python -m pytest \
  operator-console/tests/test_stc_probe.py -q -p no:cacheprovider  # 6/6
```

Requires the dev dsh-tools symlink after any fresh `pnpm install`
(see dsh-plugin-stc/README.md).

## 4. Boot + journey + rollback (fresh homes)

```sh
python3 dsh-plugin-stc/scripts/boot-check.py      # expect PASS
DSH_CHECKOUT=/tmp/dsh-upstream .venv/bin/python \
  dsh-plugin-stc/scripts/product-journey.py       # expect 13/13
python3 dsh-plugin-stc/scripts/rollback-check.py  # expect PASS
```

## 5. Evidence reproduction

```sh
.venv/bin/python dsh-plugin-stc/scripts/rescore-pilot.py \
  --batch dsh-plugin-stc/evidence/pilot-2026-09-30/raw-batch \
  --out /tmp/rescore-verify.json                  # expect exit 0
# diff (minus `batch` path) vs evidence/.../rescore-v1.json: IDENTICAL
cd dsh-plugin-stc/scripts
python3 test_checker_confined_diff.py             # expect 11/11
python3 test_policy_default.py                    # expect 10/10
```

## 6. SST contract posture

```sh
.venv/bin/python dsh-plugin-stc/scripts/sst_compat_probe.py \
  --sst-root /tmp/sst-pin-df78f42 --git-repo /path/to/sst
# expect: VERDICT: COMPATIBLE
```

## Pass criteria

All six sections green on the frozen candidate, run by a party other
than the builder, with retained (not tail-truncated) summaries. Any
red section blocks release; fixes restart verification from §1.
Out of scope for this procedure (visible prerequisites, not silent
passes): browser-pixel walkthrough, durable-home migration
execution, live-model SST consumption, budgeted quality batch.
