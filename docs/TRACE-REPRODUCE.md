# TRACE reproduction (frozen seam12a, o94-scale10m)

TRACE is the memory layer for this ecosystem: an experimental retrieval
architecture that organizes continuous document streams into an
overlapping multi-tier DAG without global clustering recomputation.
The frozen build below is measured, not projected.

Source: [github.com/Anshul48/trace](https://github.com/Anshul48/trace).
Live explorer: [live explorer](https://anshul48.github.io/trace/explorer/).
What exists is a Python package plus the `tools/product_pilot.py`
CLI — no SDK, no API, and no hosted endpoint is claimed. Built for
memory-over-streams research; use it to explore schema priors and
negative knowledge (what failed, and what must never ship) on your
own corpora at small scale.

## Freeze identity (pinned)

**seam12a**, tarball sha256
`8d3bbb6bf53e1731811065a9de156a9997be740d598cd1dfa0a3d946928dbf64`,
run **o94-scale10m**, probes `b332d62d...`, harness `9f78479a...`,
final commits `164195`. The freeze holds 253 files (`frozen_ok=true`).

## Measured headline

10,003,381 tokens, 13,081 docs, 63,441 atoms;
guided recall@10 0.7367 all / 0.4883 leave-schema-out; self-repair
5,847 to 0 over 6 iterations; wall 9,494.9 s (~2.6 h); peak RAM
~8.5 GB (parent-process peak 8489.1 MB, rss-hwm).

## Benchmarks (frozen seam12a, o94-scale10m)

| Benchmark | Score |
|---|---|
| Guided recall@10, all sources (120 probes: chunk/noisy/cross) | 0.7367 |
| Guided recall@10, leave-schema-out | 0.4883 |
| Flat recall@10, all sources (baseline, same probes) | 0.055 |
| Flat recall@10, leave-schema-out (baseline, same probes) | 0.0017 |
| Self-repair debt over 6 iterations | 5847 to 0, 0 pending |
| Query-complete latency p50/p95 (n=33, all within 5 s) | 96.8/115.5 ms |
| Append ack-to-query | 0.114 s |
| Reader load, 2 threads, 27796 requests, p50 | 74.7 ms |

No broad-benchmark claim is made: this is the project team's
prototype evaluation protocol, nothing more.

## Reproduce the benchmark

From inside the extracted seam12a dir, with the environment kept
inside that dir:

```bash
uv venv .venv --python /usr/bin/python3
uv pip install --python .venv/bin/python numpy==2.5.4 blake3==1.0.11
SUP_PYTHON=$PWD/.venv/bin/python bash runtime.sh tools/product_pilot.py --help
PYTHONPATH=$PWD/fork/tl-sys:$PWD/tools:$PWD/tests $PWD/.venv/bin/python -B -m unittest tests.test_integration
PYTHONPATH=$PWD/fork/tl-sys $PWD/.venv/bin/python -B fork/tl-sys/tests/test_o93_repair_columnar.py
```

Expected: `--help` exits 0, integration 6/6 OK, repair-columnar
221 checks PASS. A 10k-token synthetic pilot with the same flags
exits 0 with `status=PASS, claim=measured`:

```bash
SUP_PYTHON=$PWD/.venv/bin/python bash runtime.sh tools/product_pilot.py --tokens 10000 --profile local --source-root $PWD --data-dir ./synth-data --out ./out-pilot --drain-attribution --drain-census --holon-descriptor-columnar --overrides-columnar --descriptor-matrix-all --per-view-sharing --cold-scan-chunk 4096 --repair-columnar --candidate-source hnsw --drain-bounded-k 32 --candidate-shadow-audit 8
```

`./synth-data` must hold `docs-100m.jsonl` (one JSON object per line,
fields `doc_id` + `text`) plus `emb_cache/` in `tl-gpu-embcache-v1`
layout (`meta.json`, `index.jsonl`, FP32 `shard_NNNNNN.f32` files).
Non-VM runs are capped at 1M tokens via `--profile local`.

A full 10M-token reproduction is blocked by two facts, and there is
no one-click 10M repro today: (a) the external corpus
`docs-100m.jsonl` plus its embedding cache is absent — the 1.2 MB
freeze tarball is source-only and ships no dataset; (b) the
`--profile vm` path exits unless the hostname is `trace-build500`
(`VM profile requires existing trace-build500; local runs capped at
1M TOK`). Behind that gate the corpus is absent too, so the 10M
numbers above stay receipt-labeled, not re-measured here. Scaling to
100M+ tokens is roadmap, not a claim.

See also: [TRACE quickstart](https://github.com/Anshul48/trace#run-it-in-5-minutes)
· [TRACE benchmarks](https://github.com/Anshul48/trace/blob/main/docs/BENCHMARKS.md)
· [TRACE repro](https://github.com/Anshul48/trace/blob/main/docs/REPRO.md)
· [portable 20k reproduction](https://github.com/Anshul48/trace/blob/main/repro-20k/README.md).
