# REVIEW — consumer/reviewer entry point (10 minutes)

You need: Linux, Python 3.11–3.12, the release wheel. Nothing else.

## 1. Install (2 min)

```
pip install anima_substrate-0.1.1-py3-none-any.whl   # from the release
python -c "import anima_substrate; print(anima_substrate.__version__)"
# expect: ver 0.1.1
```

## 2. Run the journeys (3 min)

```
python examples/quickstart.py            # project world + delegation +
                                         # close/reopen + recover + settle
python examples/external_participant.py  # add your own world kind
                                         # (zero host edits)
```

Both use fresh temp state and print each step with expectations.

## 3. Check the contracts (2 min)

- `docs/CONTRACTS.md` — host ops + family contract v1 (frozen rules).
- `docs/RECOVERY.md` — interruption, repair paths, what is promised.
- `docs/ARCHITECTURE.md` — how it fits together.

## 4. Check the evidence (3 min)

- `prototype/programme-20261004/PKG-ACCEPTANCE.md` — independent
  acceptance (207 passed, 11 SST-conditional skips, 147 subtests).
- `prototype/programme-20261004/U-execute/runs/U-OVERALL-FINAL.md`
  + `INDEPENDENT-ACCEPTANCE.md` — preserved negative: no host
  advantage demonstrated; change legs VOID (adaptation untested).
- `docs/ROADMAP.md` — what is done vs explicitly future work.

## 5. Know the envelope

Single host, toy scale, process-crash-only (no fsync). No learning
of any kind. STC material unqualified. Full statement in README +
`docs/ROADMAP.md`. Anything beyond this page's claims is a bug in
the docs — file it against `docs/`.
