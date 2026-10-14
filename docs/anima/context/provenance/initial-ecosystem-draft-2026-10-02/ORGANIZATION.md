# Future workspace organization

> Public curation note: links to records excluded from this public release were converted to plaintext historical references; the original record identities are preserved inline.

Date: 2026-10-02. Status: proposed target and transition approach, grounded in the current directory inventory and the user's direction. Folder names and permanent package boundaries remain revisable. The user has requested a coherent future-facing organization; this document does not declare the physical migration complete.

## Recommendation

Use one ecosystem home with independently versioned source components, reusable world definitions, procedures, studies, programme records, and concrete runs. Start with a catalogue pointing to existing code. Consolidate or relocate particular implementations when their dependencies, consumers, and operating paths are understood.

The current Utilities root contains source repositories, several distinct memory implementations, historical variants, studies, platform proposals and run artifacts. STC and SST are Git repositories; the broader substrate currently contains design documents; trace-architecture contains several candidate and source families. A directory rename would not resolve those distinctions.

The six current tracks are a work decomposition. They need not remain six permanently isolated projects, or six equivalent runtime entities.

## Target view

This is a navigational/source layout, not the runtime containment hierarchy. Only the entry point, proposal, catalogue and curator materials have been created so far.

```text
ecosystem/
  context/                   current intent, decisions, ideas, source index
  catalog.json               identities, implementations, roles, relationships
  substrate/                 hosting, lifecycle, composition, change machinery
  components/                maintained source implementations
    tl/
    trace/
    sst/
    stc/                     current mixed implementation; extract as justified
    ...                      learners, executors, compilers as reuse develops
  worlds/                    environment definitions and domain adapters
    construction/            first STC-powered world
    research/                a meaningfully different initial environment
    ...
  procedures/                supplied/learned workflows, skills, applicability
  labs/                      hypotheses, evaluators, protocols, prototypes
  programmes/                objectives, contracts, DAGs, progress, closeout
  runs/<run-id>/             actual arrangements, state, costs, evidence
```

The components subtree may be a federation of repositories, workspace packages, or a mixed arrangement. Choose physical consolidation from actual coordination and dependency costs. The initial catalogue references the existing siblings directly; no symlinks, duplicated source trees, or import aliases are required.

## What belongs where

| Area | Owns | Relationship to evolution and development |
|---|---|---|
| Context | Human intent, governing decisions, unresolved ideas, provenance | Preserve objectives and useful prior reasoning across revisions |
| Components | Maintained implementation, its contracts, dependencies and local checks | Reusable machinery can acquire new implementations and expose several capabilities |
| Substrate | World/participant identity, lifecycle, delegated resources, hosting, composition and controlled change | Supplies the surfaces through which organization can develop |
| Worlds | Domain state, representations, goals, tools, outcome interpretation and exported obligations | Participants specialize and composites can act at another level |
| Procedures | Conditional scripts, workflows, coordination policies, construction recipes and revision evidence | Retained acquired behavior, variation and inheritance |
| Labs | Repeatable studies, candidate mechanisms, independent evaluators and experiment code | Discover and compare changes with attributable evidence |
| Programmes | Sustained objectives, assignments, dependency DAGs and completion criteria | Coordinate development across several executions |
| Runs | Actual instances, participants/topology, candidate versions, observations, interventions and costs | Establish what happened and which changes produced which results |

World definitions and composition recipes can reference components or procedures. A run records the actual instantiated arrangement. An exported capability can be implemented by one component or a composite; several implementations can provide alternatives. Source location, role, runtime containment, ownership, access and physical execution placement are separate properties.

## Placement of today's work

- **TL/TRACE:** preserve their distinct identities and semantic responsibilities. Their selected implementations are reusable memory components. The delivered TL source family is trace-architecture's batch candidate plus tl-sys; sibling trace-lite remains a separate implementation. Do not silently replace the selected producer with a more conveniently named directory. Keep TRACE's actual source landing and accepted evidence qualifications visible.
- **SST:** shared search machinery serving different worlds and studies. Domain-specific candidate execution, custody and authoritative evaluation stay with the responsible world or assessment service. Search does not inherit authority over its verdict.
- **STC:** the first construction world is assembled using STC's implementation and shared memory/search capabilities. STC currently mixes domain-specific construction, execution, context preparation, verification and candidate-learning seams. Its source can remain cohesive while those boundaries are understood. Extract generic workflow/learning/execution services when a second actual consumer establishes the reusable contract.
- **Substrate:** the broader world-hosting/change machinery is its own design/development responsibility. STC's existing package named substrate is a mechanical quality-gate subsystem; it is not the entire broader substrate.
- **Early learning:** begin inside STC, retain conditional procedures and attributable episodes, and compare actual fresh-task use. Procedure storage, selection, execution, prediction and revision have separate responsibilities without automatically becoming separate repositories. Domain models and feedback interpretation remain domain-owned.
- **Studies:** use the current programme's experiment home initially. Durable protocols/evaluators can move to labs; individual executions and frozen results receive run identities. Existing evidence remains identifiable at its current location until a deliberate migration.

## Biological inspirations as working mechanisms

Use specialization, local responsibility, conditional activation, adaptation, inheritance and structural change to guide the architecture. Plain folder names keep the implementation legible.

| Inspiration | Concrete mechanism to design and test |
|---|---|
| Gene expression and differentiation | A versioned recipe instantiates machinery according to context, constraints and delegated resources; one recipe can support different roles |
| Membranes | Explicit interaction, access, state-custody and exported-obligation boundaries with authorized change surfaces |
| Development | Instances acquire, specialize, reorganize or consolidate capabilities while continuity of commitments is tracked |
| Inheritance | Procedures, libraries, representations, policies or compatible learned artifacts pass to a new instance with applicability and evidence |
| Variation and selection | Candidate changes compared under stated goals, outside evaluation and complete costs |
| Fusion and splitting | Actual changes to identity, state custody, responsibility, lifecycle or internal machinery, with lineage and subsequent reuse |

These are design analogies and operational requirements to investigate. We are not asserting a biological theory or that a folder structure demonstrates adaptive intelligence.

A composite can participate in another world without copying its source into that world's directory. A component can serve several worlds. A structural integration should record what changed inside the arrangement and which commitments transferred. A later split records its new identities and actual recovery capabilities. Source moves and runtime organizational change have different evidence.

## Transition

1. **Preserve the relevant direction.** Run the [history curator](context/HISTORY-CURATOR.md) and independently check consequential omissions or authority changes. Deliver usable track briefs progressively. Resolve history needed for major new organizational choices before committing those choices.
2. **Map the existing implementations.** Use [catalog.json](catalog.json) as the initial navigation map. Identify the actual selected candidates, source repositories, packages, host pins, consumers and owned evidence. The catalogue is not a second decision authority.
3. **Choose the first world compositions.** Describe construction and a distinct research/constraint environment, their required capabilities and state responsibilities. Keep cross-world interaction and representation choices open.
4. **Build at current locations.** Apply scoped packets and real integration checks. New reusable code can use the target organization as its home once it has a concrete responsibility and owner.
5. **Relocate selectively.** Before a move, inventory imports, editable installs, launch commands, relative/absolute paths, fixtures, local environment configuration, Git/worktree assumptions, documentation and evidence locators. Record checked source/destination paths and candidate identity. Verify launch and affected integration after the move. Preserve repository history and frozen results; update the catalogue and canonical links.

Existing release and execution obligations retain their scope during this transition. The current programme charter (historical record `../autonomous_runs/trace_ecosystem_20261002/PROGRAMME.md`, excluded from this public release) and state (historical record `../autonomous_runs/trace_ecosystem_20261002/RUN-STATE.md`, excluded from this public release) stay authoritative for that prepared tranche until their ownership/location changes deliberately. No comprehensive archive reconstruction is a universal prerequisite for settled inspection or independent ready work.
