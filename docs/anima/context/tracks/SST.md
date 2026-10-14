# SST track brief

> Public curation note: links to records excluded from this public release were converted to plaintext historical references; the original record identities are preserved inline.

*See [`ANIMA/START-HERE.md`](../../START-HERE.md) and [`ANIMA/context/integrations/2026-10-08/SYNTHESIS.md`](../integrations/2026-10-08/SYNTHESIS.md) for macro integration context and the 2026-10-08 independent-module delivery policy.*


**Owner/source home:** `sst/`. **Evidence class:** repository contracts, caller source, tests, and historical integration records were inspected; this pass did not execute a current search or caller test.

## Responsibility and relationship to other tracks

SST supplies bounded search across hypotheses, formulations, candidate solutions, and workflow alternatives, with attributable alternatives and outcomes. It does not own a domain's authoritative evaluator, verdict, or state custody. The user directly says SST integration into STC is current work to complete; keep that distinct from whether every TRACE release integrates SST.

SST remains independently useful and can later serve several worlds or participate as part of a composite. Current source ownership does not fix its future runtime placement.

## Evidence and limitations

- STC M1 selected the SST controller with an STC-side verification wrapper and explicitly kept SST read-only. The historical P03 evidence used clean SST Git commit `079f4de6fd43881c2f1b529f0612f1df64a62f32` under `INT-2026-09-13.2` and establishes a bounded pinned compatibility path.
- Later M1 B5 integration records state that live-model search produced zero proposals; live custody, gates, veto, champion, and mutmut behavior were not demonstrated. That limit is not cured by dry-run/fixture e2e success.
- SST's TRACE-feedback integration test defines a synthetic `MockTraceDatabase`. `ContextCapsuleCompiler` accepts an optional duck-typed provider and swallows some lookup exceptions; the CLI currently does not provide a memory provider. This is not a real TRACE caller path.
- No current source revision, dependency/configuration set, frozen ANIMA release, or current consumer pin is selected. Historical `079f4de` remains a dated integration pin only.

## Current obligations

The active programme's SST0–SST2, M2, and M3 nodes remain `planned`. SST0 maps callable search and failure/feedback semantics; SST1 qualifies bounded callable search; SST2 qualifies a real caller; M2 checks real STC candidate execution/search through an independently checked path. A mock, imported symbol, or catalog link does not satisfy caller acceptance.

**Primary sources:** [SST README](../../../../components/sst/README.md), [data contracts](../../../../components/sst/docs/03_DATA_CONTRACTS.md), [TRACE feedback test](../../../../components/sst/tests/integration/test_trace_feedback.py), [CLI](../../../../components/sst/src/sst/cli/main.py), [context capsule](../../../../components/sst/src/sst/context/capsule.py), [STC M1 state](../../../../components/stc/docs/builds/stc-integration/STATE.md). Historical locations and direct user turns are indexed in `../SOURCES.jsonl`.