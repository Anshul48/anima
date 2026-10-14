# ANIMA responsibility and organization map

Status: approved organization starting point, recorded 2026-10-03. The future runtime host and permanent source topology remain unselected. This map groups responsibilities; it does not prescribe a fixed runtime anatomy or imply that a folder is a working capability.

## Responsibility areas

| Area | Owns | Current location/status |
|---|---|---|
| Direction and preserved context | Operative objectives, scoped decisions and corrections, ideas, requirements/evidence, source coverage, open issues, excerpts, and the preservation audit | `ANIMA/context/` is the canonical curated record. Original conversations and owning project records remain their sources. |
| Component projects | Standalone implementations, local contracts, dependencies, candidate identity, bounded releases, and their own checks | Existing source projects stay in place and independently versioned. `ANIMA/catalogue/MODULES.json` maps them. A future move requires a deliberate path/dependency/launch/evidence inventory. |
| TL | Attributable organization and retrieval of source material, with its own release scope and broader organization obligations kept distinct | Selected delivered source family: `trace-architecture/tl-candidate-batch` plus `trace-architecture/tl-sys`. Do not conflate with `trace-lite`. |
| TRACE | Episodes, interpretation, revision, display, and conclusions only within the specific evidence and semantic authority granted to TRACE | Product landing: `trace-architecture/trace-build`. Its accepted duties and conditional inference/activation gates remain in TRACE’s owning records. |
| STC | First construction-world implementation, workspace execution, verification/recovery, and early experience-to-procedure/workflow learning | `stc/`. STC’s package named `substrate` is an internal mechanical subsystem, not the broad world-hosting substrate. |
| SST | Bounded exploration/search and attributable alternatives/outcomes, without owning a domain’s authoritative evaluator | `sst/`; a real STC caller is a separate qualification obligation. |
| Broad substrate | Hosting/lifecycle/resources, nested environments, local responsibility, revisable cooperation, controlled organizational change, and reusable composites | Design home currently `substrate/`; no permanent runtime host or qualified substrate implementation is selected by this map. |
| Worlds | Domain state, local goals/representations/tools, state custody, outcome interpretation, exported obligations, and a composition’s actual participants | Construction and research environments are proposed; their concrete contracts and host are not yet selected. A world can compose components or other worlds. |
| Procedures | Conditional workflows, scripts, skills, recipes, applicability, lineage, and evidence for reuse/revision | The user-supplied debate/forage/architecture/build/audit process is an initial seed, not a mandatory universal workflow or a demonstrated learner. |
| Labs and experiments | Hypotheses, protocols, evaluators, prototypes, comparisons, and dispositions | Current programme experiments stay in `autonomous_runs/trace_ecosystem_20261002/experiments/` while that programme owns them. Future durable cross-programme studies can have an ANIMA lab home. |
| Programmes | Objectives, DAGs, assignments, dependencies, resource posture, status, and closeout | Active programme remains canonical at `autonomous_runs/trace_ecosystem_20261002/`. `ANIMA/programmes/` is an index, not a second charter. |
| Runs | A particular instantiated arrangement, exact pins, participants/topology, state, observations, interventions, costs, and evidence | No ANIMA-owned runtime run is created by this organization pass. Existing preparation/run artifacts retain their current identities and paths. |

## Coordination and authority

- The user owns objectives, intended semantics, consequential architecture choices, and any new material authority or spending boundary.
- The programme coordinator owns the active programme’s DAG, shared state, assignment, reconciliation, and integration reporting at its current canonical path.
- Each module owner retains local implementation and release ownership, subject to its accepted contract and any explicit consumer agreement.
- Architects maintain cross-project responsibility boundaries and bring consequential unresolved alternatives to the user.
- Integration owners qualify actual producer/consumer behavior. Catalogue references, imports, or compatible-looking interfaces alone do not establish integration.
- Independent verifiers check consequential acceptance claims against the actual candidate and its evidence.

Independent project ownership is the current arrangement for parallel development and bounded release work. It does not permanently prevent integration, later ownership changes, or forming a composite. Such changes require explicit records of transferred obligations, state custody, lifecycle, compatibility, and evidence. A source move and a runtime organizational transformation are different events.

## Placement rules

1. Keep source identity and release identity separate from a runtime participant or world identity.
2. A component may expose multiple capabilities and serve multiple worlds. A composite may be reused as a participant in another world.
3. Record ownership, containment, state custody, access, capability, and physical execution placement as distinct relationships.
4. Keep domain interpretation and authoritative verdicts with their responsible world/evaluator. Shared envelopes do not force a universal ontology.
5. Let biological/developmental inspiration motivate mechanisms—specialization, conditional activation, adaptation, inheritance, assimilation, merging, splitting, coalition formation, and plastic boundaries—without fixing one permanent anatomy.
6. Treat structural integration as a real change in state, ownership, responsibility, lifecycle, or internal machinery, followed by evidence of subsequent reuse. Messages or adapters alone do not establish it.
7. Extract shared learning, coordination, or execution machinery after actual reuse identifies a useful contract and owner.

## Initial logical tree

```text
ANIMA/
  context/       canonical intent, history, decisions, requirements, and audits
  architecture/  responsibility map and small versioned boundary contracts
  catalogue/     source identities, release records, and explicit consumer pins
  components/    independently owned sources if/when a deliberate source-home move is justified
  worlds/        actual environment definitions and composition records
  procedures/    versioned conditional workflows, skills, and recipes
  labs/          durable study protocols, prototypes, and evaluators
  programmes/    objectives, DAGs, status, and handoffs
  runs/          actual arrangements and evidence, pinned to exact candidates
```

The last five areas are created as records or code acquire real content or an assigned responsibility. The active programme and its experiment home remain at their current locations for now. `components/` is not populated with copies or symlinks; the current catalogue points to the existing project directories.
