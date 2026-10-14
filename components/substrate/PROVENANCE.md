# PROVENANCE.md — anima-substrate copy-forward + maintenance record

`s006 style <prototype/successor-006/PROVENANCE.md>`_: per-file
sha256 + exact adaptation list + NOT-carried list. Nothing under
`prototype/*` was modified; all frozen trees were read-only sources.

## Copy-forward sources

- Host engine, org ops, recovery, procedures, routing, demos,
  accept pack, sched fixtures: the frozen `prototype/successor-006/`
  tree (which itself carries `prototype/successor-005/` bytes —
  see the s006 PROVENANCE for the s005 shas).
- SST snapshot manifest pins: `prototype/successor-005/vendor/
  SNAPSHOT-MANIFEST.json` (relpaths + sha256 digests only — no SST
  bytes; the 54-file snapshot itself is caller-staged, see
  `docs/SST-STAGING.md`).
- Consumer-doc procedure sections: `prototype/successor-005/
  CONSUMER.md` §§4–8 (terms kept verbatim for the wording audit).
- Coupling-contract text: `prototype/successor-006/
  COUPLING-CONTRACT.md` CC1–CC9 (carried into `docs/CONTRACTS.md`).

## Adaptation edits (base tree, prior builder)

- Flat modules repackaged under `src/anima_substrate/` (`host/`,
  `participants/sched/`, `demos/`, `accept/`); imports rewritten
  from flat (`import api`) to package-relative (`from ..host import
  api` / `from anima_substrate...`). Behavior unchanged.
- `release.py` CLI → `src/anima_substrate/cli.py` (`anima-substrate`
  entry point + `python -m anima_substrate`); child-drill spawn
  lines use `-m anima_substrate.demos.*`.
- `api.run_tasks(..., with_sst=True)` / `demos.run_demo`: s006
  always-refused; now staged-or-refuse over the caller-provided SST
  root (`SUBSTRATE_SST_ROOT`, compat probe, see `docs/SST-STAGING.md`).
- `host/api.py`: NEW public `birth_world` (the only host mutation
  participant families need) — added BEFORE any family, so every
  family below is a zero-host-edit addition.
- `host/routing.py`: `ChannelRegistry` gained an optional backing
  file (M3 channel persistence; default in-memory, unchanged
  behavior when unbacked); `api.open_run` restores it.
- `host/api.py`: NEW org-state surface (M3: `relate_op`,
  `org_snapshot_op`, `export_composite_op`, `import_composite_op`).
- NEW participant contract + registry
  (`participants/__init__.py`); NEW families `sched@v1`,
  `relcheck@v1`, `relcheck@v2`, `sst@v1` (zero host edits each).
- NEW recipe loop (`host/recipes.py`, M4) + CLI family/recipe ops.
- SST adapter (`participants/sst/`): carried hash construction +
  child protocol from frozen s005 `make_snapshot_manifest.py` /
  `verify_snapshot.py` / `sst_leg.py`, retargeted at caller-staged
  roots (no vendored bytes, no pydantic in base).

## NOT carried (deliberate, recorded)

- SST snapshot bytes (`vendor/sst-snapshot/`, 54 files): caller-
  staged at the pinned commit instead (LICENSE-AUDIT T2-Option-A).
  No SST bytes ship in this package.
- `vehicle/` (s5-readiness throwaway split): stays with s005.
- H2 lane-task routing (`task_json`/`lane_override`/derived
  routing): H2 stays FROZEN as-verified, out of scope for this
  package (see `docs/ARCHITECTURE.md` §H2). No half-carry.
- `test_procedure_smoke.py` (s006 3-test smoke): SUPERSEDED by the
  full ported 57-test procedure suite; not carried.
- U-execute harness, w1-harden bridge, reuse-demo bridge: evaluation
  history / superseded-as-code; stays frozen.
- Suite files `test_conformance.py` / `test_fission.py` were ported
  (not copied byte-identical): import/CLI/tmpdir retargeting only,
  asserted counts unchanged (9/9, 7/7).

## Maintained package file record

sha256 of every shipped file (regenerated on every source change;
`tests/test_successor.py::test_14` and
`tests/test_coupling.py::test_cc9` enforce consistency —
regenerate with the command below, never hand-edit):

```
.venv/bin/python -c "
import hashlib
from pathlib import Path
for p in sorted(Path('src/anima_substrate').rglob('*')):
    if p.is_file() and '__pycache__' not in p.parts and p.suffix in ('.py', '.json'):
        print('-', hashlib.sha256(p.read_bytes()).hexdigest(), p.as_posix())
"
```

- 34fa62d334f41c307728c052aac18208bfb8fb828c37dcad4c77817ed8a152ad src/anima_substrate/__init__.py
- fcb7eb68d0d2ef1e5383297b6bd11d46b80dc1ea9a7cb23657a39562934ee544 src/anima_substrate/__main__.py
- 53a4bf67653760783370c8d95822cd20d4e2a752496e3b811c825f2dee1d6093 src/anima_substrate/accept/EXPECTED.json
- bdf1e38407fc501527e11e907fc3a95a2b5af81a7c66b2904524b4676829a883 src/anima_substrate/accept/S1.json
- fc32edeea1737db96298f1dd0482d009db75a29ed75b1c3164f1fe006aa110ff src/anima_substrate/accept/S2.json
- 0847e159bcc1418e608b5379afe2f0c24b9522355d868fe015cb1da6ffad1157 src/anima_substrate/accept/S3.json
- af81bdcdf8b77686f5fae2eec33bf8aa902e15533fac4f31038dad7b299e688b src/anima_substrate/accept/S4-followup.json
- 0b794b8b5a596e143e4668910e6cb27cc07d4b9b81258d856447f617b20682b8 src/anima_substrate/accept/S5.json
- ce42d0353bfe6cd89b2f8d871cbb64522feefca154553b8c5639d188d15dc5d3 src/anima_substrate/accept/S6-followup.json
- b4d715af19b46b02ef1e6f086ab6e086c55e9173517ee7ceef1bc581d271f421 src/anima_substrate/cli.py
- e184779974860472555f871567d4cb2555c6050799dbf590e4cf40efb8f50714 src/anima_substrate/demos/__init__.py
- aac32f8c5e85a0ca2f07ebcdb83ce9576f07acd89dea251eec7bc1b87e8d20b6 src/anima_substrate/demos/j1_demo.py
- b3ba5b31aa3a8213c06b701ca05ac67c424bacfbc35c046f50d5a6463c147b23 src/anima_substrate/demos/successor_demo.py
- af4b9ee4de4fe66cd547f8acfaa9be8a18e9c4622af714e6ba93314a9c141477 src/anima_substrate/host/__init__.py
- ec12a2770fed6b630ee7daddb9b44afde12c1790608355d3708482619909cd70 src/anima_substrate/host/api.py
- b87535fe5faff926f62811a008285ae5b0d2cea3a89c538d24bb8888b547a12a src/anima_substrate/host/calibrate.py
- 2366275838353ae340816a9322a1778f395c30c74d3938c243334fd87203e2ff src/anima_substrate/host/fusion.py
- f2b97464af9d03f19773696bbb816369a1ef6e52af569c9bdff679eb2105ed35 src/anima_substrate/host/minihost.py
- 5e065a6b846d0aba98f2404269be5bbf68a8afbe6ad3e2ad3a5cb3c9b3852720 src/anima_substrate/host/pipeline.py
- 0bdcc94a0703274bb1b5d608aab5e47e0eb33755e98ba56e868ca756c0aff6b4 src/anima_substrate/host/procedure.py
- f231beb4481918fa291b359bf7af79fcf3c3ca5e5af0e86724831aff13a697b4 src/anima_substrate/host/recipes.py
- 527593a8606fa88d0eaecad0eb6b5b27a1f9b0f7705615baf13afd83c5d7eae7 src/anima_substrate/host/recover.py
- 18631522ac02575618b0c2c7a959f3ae5e8e6186ee560ec95bf2cf870941500b src/anima_substrate/host/resume.py
- bd490af3fa8b8ba4afe15878f8bc7c1f6f2a04373a834426e5be85a2df839825 src/anima_substrate/host/routing.py
- 5493f137062d9715e7a81602c69e1836c0d2900a14fb62bbd5da5f9e508f4543 src/anima_substrate/participants/__init__.py
- 5356593f640991e7a3f9f13c03af0e559f4c12e74a7f99d8ecb930727e7fe463 src/anima_substrate/participants/relcheck/__init__.py
- e9faa2c367cc281f77c77ba9616402e05358057d3c1a115b020afc0e9ecab592 src/anima_substrate/participants/relcheck/checker.py
- 91b2bd92c777499d3ee84f92dfc1879b3655c4a455e6b590ff372366d4b321ee src/anima_substrate/participants/relcheck/runner.py
- b4f74663b435500e48d36e77c63ce2688754baa3fa091b6b9b2192d5ccf3a94e src/anima_substrate/participants/relcheck/v1.py
- ecf460a8546b821f53f5dece14187ece1ba692578f5fa1b5d73d723094d28c75 src/anima_substrate/participants/relcheck/v2.py
- 4c91fc82899ccb8c3c703c30a6c233dd72e2a9c57be02d7308ec92f5f4d22239 src/anima_substrate/participants/sched/__init__.py
- b588a0834f69d7645a140375b2922ce732b5d52bb31ee1502431f499a38de2bc src/anima_substrate/participants/sched/family.py
- a38da091134d0a1c075c9e6749a64246763aaa3d5a1da98d01dcdde70160c8fd src/anima_substrate/participants/sched/sched_checker.py
- e11578d9264970bff2c4d4978fd4091822cccd8cd21d883804695d393fd8867a src/anima_substrate/participants/sched/sched_domain.py
- aa84e54ffc21201aadd63454491caaaa2492fbbf2f244f33089336861e98b30f src/anima_substrate/participants/sched/sched_inputs.py
- e5d8bb0a68403d95f9e5df855d3a9e605df242d8240a720c582d47c61ea70556 src/anima_substrate/participants/sst/SNAPSHOT-MANIFEST.json
- 1e14d0216d96093ba2585293b3cd8e9deb1482eb5f7caa86820c57fa30ce1edc src/anima_substrate/participants/sst/__init__.py
- 67ba5fc292bcb5d593176ede6ecc79ec35e282034905cf1aebfc0c4615aa26d8 src/anima_substrate/participants/sst/manifest.py
- 2439024fbd474e74f13be5542f9426793993874c35b9ed61edae554a8d8ea704 src/anima_substrate/participants/sst/staged.py
