> Public curation note: links to records excluded from this public release were converted to plaintext historical references; the original record identities are preserved inline.

**Memory tiers and graph retirement — macro discussion, 2026-10-04**

Status: proposed macro architecture and questions for the TRACE architect. This records the user's preference and a possible refinement; it does not supersede TL/TRACE contracts, select the B-01 winner, or change runtime behaviour. No benchmark was run or campaign completion audited here.

The user wants space in the main graph to be costly and contested. Retired bodies should leave it; pointers or small records can indicate that something existed and was deleted. Historical analysis should account for the cost of locating and reconstructing material from a separately retained immutable ledger. The user also proposes a hierarchy: a hot creative/cognitive layer, a warm knowledge layer, and cold historical evidence, with further sublayers and edge types inside each.

**Recommendation at macro scope**

Develop these as functional zones: bounded active cognition, reusable organized knowledge, and faithful historical/source retention. They need not correspond one-to-one with TRACE, TL, a service, or a physical storage device. TRACE can participate in multiple zones; its responsibilities and TL's evidence/organization contracts remain separately defined.

Hot cognition may include several expert working graphs, shared representations or operators, task workspaces, compressed schemas, and provisional associations. Allocate active resources across useful current work, rare or unresolved possibilities, and longer-term learning. Creative exploration is one consumer; planning, construction, and verification also need active state.

Warm knowledge can retain reusable schemas, procedures, expert capabilities, richer typed relations, unresolved interpretations, and source/episode references. Learned capability should remain reusable when its current activation ends. Cold retention supplies source versions and the historical records promised by its actual capture contract, with derived indexes and locators where useful.

These zones can have internal hierarchies. Resource residency, semantic role, and validity are separate axes. A valid source can be cold; a retired assertion can have a rich historical record; an active hypothesis need not be established knowledge.

**Three distinct operations**

- Eviction or demotion ends hot residency while leaving knowledge eligible for appropriate future use.
- Retirement removes eligibility as current knowledge and requires the corresponding dependent views and serving paths to respond.
- Historical access deliberately reads retained earlier material with its time and status, rather than silently restoring it as current knowledge.

This distinction supports lossy active representations without repeatedly rebuilding useful expertise from raw sources. Retain the schemas, procedures, definitions, versions, and construction recipes needed to reuse or reconstruct those representations. The cost and quality of reactivation remain experimental questions.

**Retirement records outside cognitive traversal**

Remove retired bodies from current graph/routing structures. Small identity/status records, exclusion sets, or generation metadata can live behind resolution and serving-control interfaces. They are accounted-for state, but need not consume semantic vertices, participate in spreading activation, or appear in ordinary results.

During asynchronous cleanup, old indexes, caches, delayed consumers, and pinned readers can still exist. Physical removal from one graph does not by itself make every path consistent. Retain the minimum exclusion/recovery information required by the actual serving contract, then reclaim it when the relevant conditions clear. A small record is not automatically free at large scale; measure its growth and read/update costs.

Historical work should bear its actual retrieval, I/O, reconstruction, and computation costs. Useful archive indexing reduces wasted work. An analyst can construct a temporary historical graph within its own budget without expanding the default current cognitive graph or implicitly making retired assertions eligible again.

**Prediction and expert organization**

Compressed schemas and summaries can propose routes, interpretations, or operations. Bottom-up discrepancies and outcome feedback can prompt targeted inspection, repair, or reorganization. Distinguish routing error, task failure, missing coverage, changed conditions, and contradictory evidence; low aggregate prediction error does not establish correctness.

A society of expert worlds can have distinct active representations and budgets while sharing useful knowledge and operators. No single brain model, shared ontology, or literal biological forgetting rule is prescribed. Assess compression through task capability, exception preservation, novelty, and total reactivation cost as well as memory savings.

**Existing decisions that constrain the handoff**

The original three-way bakeoff is S-01 §6 (historical record `../../trace-architecture/sessions/S-01-CLOSURE.md`, excluded from this public release): C1 tombstone filtering, C2 active-graph removal with exclusion enforcement, and C3 graph/routing removal with markers for scan/list structures. The branch log (historical record `../../trace-architecture/decisions/BRANCH-LOG.md`, excluded from this public release) identifies C2 as the user's preference while retaining the experiment. Its shared pinned-generation correctness and resource accounting remain relevant; the current discussion does not declare a new winner.

S-02 citation and retention decisions (historical record `../../trace-architecture/sessions/S-02-CLOSURE.md`, excluded from this public release) promise no permanent tombstones and require retention only where current publications, pins, dependencies, or recovery need it. The contracts permit compact metadata and leave physical placement open.

TL has no historical-reconstruction promise after reclamation. A complete cold history therefore needs an explicit capture frontier, failure/retry behaviour, and retention owner, as identified by the TL/TRACE boundary review (historical record `../../trace-architecture/reviews/TL-TRACE-BOUNDARY-RECONCILIATION-2026-09-30.md`, excluded from this public release). A recovery WAL or readable current snapshot alone does not establish such an archive. The macro proposal must not silently assign archive duties to TL.

**Next discussion with the TRACE architect**

Resolve how these zones fit current graph types and publication boundaries; which compact control records are required and when they can be reclaimed; what the archive actually captures; and how promotion, demotion, retirement, dependency invalidation, and historical rehydration remain distinct. Preserve the current macro ambition while assessing its concrete tradeoffs through the existing bakeoff and later capability experiments. Match correctness and source-retention scope across candidates, and account for churn, stale-result prevention, maintenance backlog, historical recovery, and total cost.
