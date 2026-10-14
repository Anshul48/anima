"""Reverse-reconstruction: prove B2 debt edits are exactly the B1 plan.

For each file with a PINNED pre-debt hash, reverse-apply the planned fixes
to the CURRENT bytes and require the sha256 to equal the pinned pre-image.
Any extra/missing/different B2 byte fails the hash comparison.
"""
import hashlib
import sys

WS = "<workspace-root>/stc"

failures = []


def check(name, actual, expected):
    ok = actual == expected
    print(f"{'PASS' if ok else 'FAIL'} {name}")
    print(f"  actual   {actual}")
    print(f"  expected {expected}")
    if not ok:
        failures.append(name)


# --- 1. cli.py: reverse the single yaml-ignore line -------------------------
p = f"{WS}/src/stc/cli.py"
lines = open(p, "rb").read().split(b"\n")
assert lines[19] == b"import yaml  # type: ignore[import-untyped]", lines[19]
lines[19] = b"import yaml"
recon = b"\n".join(lines)
check(
    "cli.py pre-image",
    hashlib.sha256(recon).hexdigest(),
    "2ddfd6cbced44cf205aa061364c3681f52d4f28311294d008bfd3b41e50d82f1",
)

# --- 2. test_integration_dialectic.py: reverse the 4 mypy fixes -------------
p = f"{WS}/tests/unit/test_integration_dialectic.py"
raw = open(p, "rb").read()
lines = raw.split(b"\n")

# (a) :176 ignore-code correction -> stale [dict-item]
assert lines[175] == b'        self.profiles["test"] = "test"  # type: ignore[assignment]', lines[175]
lines[175] = b'        self.profiles["test"] = "test"  # type: ignore[dict-item]'

# (b) :577 deleted comment -> restore
assert lines[576] == b"        receipt.synth_score = 0.1", lines[576]
lines[576] = b"        receipt.synth_score = 0.1  # type: ignore[misc]"

recon = b"\n".join(lines)

# (c)+(d) two typed-local blocks -> bare `return base(request)`
fixed_block = b"        text: str = base(request)\n        return text"
bare_block = b"        return base(request)"
n = recon.count(fixed_block)
print(f"  typed-local blocks found: {n} (expect 2)")
assert n == 2, n
recon = recon.replace(fixed_block, bare_block)

check(
    "test_integration_dialectic.py pre-image",
    hashlib.sha256(recon).hexdigest(),
    "eea1a7eea04eebbe21680836e4823e01bb2bfa62729f4bcd41bcb219f52a0ec0",
)

if failures:
    print(f"FAILURES: {failures}")
    sys.exit(1)
print("ALL RECONSTRUCTIONS EXACT")
