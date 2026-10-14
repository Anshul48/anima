# Expert worlds, outlier discovery, and organizational search

**Status:** Proposed architecture dossier integrating the supplied 2A, 3A, and 4C direction. This is a research framing, not an accepted design, implementation instruction, qualification claim, or protocol selection.

## The expert as a developing world

A specialized model, a specialist cluster within TRACE, and a whole TRACE expert are different units of specialization. A model changes the inference substrate. A cluster can organize a region of knowledge and associated operations. A whole expert can additionally maintain its own developmental history, working methods, interpretations, responsibilities, and feedback. Current TRACE is already hierarchical; the distinction is where a participant acquires enough persistence and independence to develop a trajectory.

These forms can coexist. One expert world could contain several specialist models and clusters; several experts could temporarily form a composite around a shared problem. Containment, source access, responsibility, runtime placement, and authority should remain distinguishable. Merely nesting components does not create learned integration.

The architectural hypothesis is that persistent specialization plus useful cooperation can improve capability. It remains possible that a well-organized single TRACE, equipped with equivalent retrieval and methods, performs better. A society of experts does not itself establish intelligence beyond its components or guarantee AGI.

## Ownership and coupling are several axes

The choice is not a binary between internal clusters and federation. Useful axes include:

| Axis | Possible arrangements | Consequence to investigate |
| --- | --- | --- |
| Inference | Shared model, different methods, specialized models | Whether gains arise from organization or model capability |
| Sources | Shared versioned base, partially overlapping bases, separate custody | Coverage, duplication, access, and common errors |
| Interpretation | Shared overlay, separate overlays, negotiated composite | Ability to retain unresolved disagreement |
| Commitments | Advisory conclusions, local decisions, delegated responsibilities | Which participant can change consequential state |
| Coordination | Common working context, exchanges, occasional consultation | Bandwidth, latency, independence, and revision costs |
| Adaptation | Retrieval and workflow changes, learned routing, model changes, reorganization | What develops and how improvement is attributed |

Shared evidence does not require shared interpretation. Shared interpretation does not automatically authorize a commitment. Independent instances may still share the same blind spot through a common model or source base; agreement is therefore not independent corroboration.

The supplied track briefs currently place source identity, provenance, retrieval, and broader source organization with TL; TRACE owns its historical and epistemic overlay; SST supplies bounded exploration rather than domain verdict or execution custody. Expert-world proposals do not transfer these responsibilities. Future redistribution would need explicit semantics and an accepted change. Historical ActivityStreams/AS2 or TraceSync discussion supplies possible communication context, not a protocol decision here.

## Context selection and commitment continuity

4C makes active context selection an interface requirement for the network. Before a consequential step, the acting participant needs an account of the operation, relevant goal, evidence versions, unresolved uncertainty, applicable constraints, prior commitments, and available resources. Selecting context once at task entry is insufficient if later steps depend on new evidence, changed scope, or another expert's decision.

The context interface should support a bounded working set and a route to request omitted material. It should distinguish evidence omitted because it was assessed as irrelevant from evidence unavailable or never inspected. Selection can combine immediate relevance with a reserved allowance for counterexamples and poorly represented regions. The consequence of omission matters more than similarity alone.

A commitment interface should preserve who made a decision, under what authority, with which scope and conditions, and what would invalidate or supersede it. A proposed action can then be checked against applicable commitments before adoption. This is stronger than hoping a long transcript remains salient.

Consistency checking must allow legitimate differences across time, scope, and evidence. A changed conclusion is not necessarily a violated commitment; disagreement is not necessarily an inconsistency. Checks should surface applicable conflicts and missing support, while remaining fallible. Neither longer context nor a checker warrants a claim of complete global consistency. These are functional interfaces, without requiring universal brain anatomy.

## Salience and preserving outliers

A holon signpost answers how to enter a region. It need not adequately describe every member. A centroid that is useful for navigation can nevertheless suppress exceptions, competing interpretations, or combinations that become important only under a later question.

Preservation therefore has two obligations: retain attributable material, and maintain ways to discover material inadequately described by current organization. Keeping an item on disk satisfies only the first. Candidate mechanisms include:

- Several representatives per region, including boundary cases and counterexamples.
- Member-specific residuals that retain conditions absent from the common description.
- Direct source retrieval that can bypass the summary hierarchy.
- Overlapping memberships and alternative organizations of the same evidence.
- Bounded exploration of underexamined regions and candidate bridges across regions.

Vector embeddings are one possible bridge proposal mechanism. Similarity does not establish support, contradiction, identity, or causal relevance; distance does not establish uselessness or breakthrough value. Novelty must therefore be treated as a reason to inspect, not as a reason to promote.

Salience is relative to a task and changes over time. A minority result can be low priority for ordinary navigation yet high priority for a decision whose failure it predicts. A useful architecture can preserve such material economically while activating it when relevant. The hard question is which residuals and routes prevent consequential loss without making every operation inspect everything.

## History cost, inheritance, and compositional forgetting

Whole experts have costs beyond model calls: historical state, indexes, duplicated evidence, reconciliation, and maintenance. Giving each expert an unlimited private archive risks spending growing resources on repeated material rather than new capability. Shared versioned sources with distinct overlays are one candidate compromise, subject to access, retention, and ownership rules.

Compression introduces a subtler risk: compositional forgetting. An expert exports a useful procedure but omits its preconditions; another packages it into a composite; a successor inherits the package without its counterexamples. Each local summary looks adequate, while the final capability loses the conditions that made it trustworthy.

Inheritance should therefore consider a procedure together with its dependencies, applicability, known failures, provenance, and uncertainty. This does not imply copying every transcript. It means identifying which history is necessary to use and revise the inherited capability. References also require continued availability; a pointer to discarded evidence cannot support later reopening.

Forgetting should distinguish reducing activation, removing a rebuildable projection, and irreversibly discarding evidence. Each has different consequences. Fusion and fission likewise need an account of which responsibilities, interpretations, and history remain attributable afterward. Persistent individuality can be useful, but preserving every distinction forever can prevent consolidation and overwhelm retrieval.

## Diverse methods and learned cooperation

Psychological diversity is an inspiration for variation, not a list of preset algorithms. Big Five traits and neurodivergence categories do not specify AI mechanisms. More useful dimensions are observable methods: abstraction versus concrete cases, counterexample seeking, experimental intervention, analogy, decomposition, and tolerance for unresolved uncertainty.

Variation should concern what participants actually do and retain. Giving identical models personality descriptions may change style without producing complementary competence. Conversely, the same model could develop different working methods through different tasks and feedback. These remain hypotheses to compare.

Learned cooperation includes when to consult, what intermediate state to share, how to resolve a failed handoff, and when recurring collaboration warrants a composite. Expert extraction is attractive when an identifiable responsibility benefits from a separate trajectory. Copying an overlay does not immediately create an independent expert. Useful divergence requires subsequent experience and adaptation; extraction also incurs duplicated maintenance and possible loss of shared context.

The trillion-token ambition should distinguish cumulative work across many episodes from one coherent reasoning episode. Aggregate generation is neither accumulated reliable knowledge nor a single extended argument. The relevant target is useful capability retained and composed across that work, together with its verification and coordination cost.

## SST and a large organization's project structure

3A suggests separating four connected objects:

| Object | What it represents | What it must not silently imply |
| --- | --- | --- |
| Alternatives | Candidate plans, hypotheses, assignments, formulations | That a candidate was adopted or executed |
| Dependencies | Prerequisites, shared resources, compatibility, conditions | That dependencies are satisfied |
| Execution | Adopted actions and observed operational state | That execution achieved its intended outcome |
| Evidence | Records supporting observations and evaluations | That a recorded plan proves success |

A search tree can display alternatives, while the organization's projects require a graph: branches can share resources, converge on a dependency, or belong to several workflows. The displayed tree should not become the authoritative organizational model.

A separate graph-building capability is plausible. It could construct an attributable view from available project and workflow records. SST could explore alternatives against a versioned view, while domain owners retain authoritative evaluation and operational custody. TRACE could retain decision histories, interpretations, contradictions, and lessons; TL retains its current source responsibilities.

A proposed dependency, an observed dependency, and a mandatory constraint may need different treatment. Without that distinction, search can turn speculative edges into planning restrictions or omit restrictions because they were represented as ordinary associations. This direction does not assume access to private Anthropic or OpenAI datasets.

## A concrete tradeoff and bounded comparisons

Consider an organization choosing a migration sequence. A reliability expert preserves a rare rollback failure that a delivery expert regards as peripheral. Tight shared working context makes joint planning faster, but repeated summary consolidation may bury the exception. Separate histories preserve it, but increase consultation cost and can produce incompatible assumptions.

A candidate arrangement keeps shared source references, distinct interpretations, and a temporary planning workspace. The proposed migration invokes the relevant commitment and counterexample checks before adoption. This costs extra retrieval and coordination. Its justification would be fewer consequential omissions or less rework, rather than greater discussion volume.

Three bounded research comparisons could distinguish mechanisms without committing to a build campaign:

1. **Organization:** compare one hierarchical TRACE, internal specialists, and separate expert worlds on the same available evidence and model pool. Account for inference, retrieval, coordination, and maintenance costs; assess outcomes, disagreement handling, and later transfer.
2. **Outlier access:** compare centroid navigation with multiple representatives, source bypass, and bounded discovery. Use questions requiring exceptions or cross-region combinations; assess evidence coverage, conditional correctness, noise, and cost.
3. **Inheritance and context:** compare summary-only handoffs with condition-preserving handoffs and step-specific context selection. Include revisions and interrupted workflows; assess unsupported assumptions, missed commitments, recovery, and inherited utility.

These comparisons should isolate mechanisms and expose failures. Planted cases can test mechanics, but cannot establish real-world creative breakthroughs or broad capability. Shared baselines and retained unsuccessful outcomes matter more than an impressive cooperative demonstration.

## Architect ownership and open decisions

The macro architect should specify participant responsibilities, relationships, structural transitions, and continuity obligations. Module architects should determine how their capabilities realize those semantics. Communication details, placement, and storage strategies should remain revisable until evidence discriminates them.

The next decisions are what specialization deserves an independent trajectory; which disagreements must survive consolidation; what history a composite must inherit; and which decisions require network agreement because they alter shared commitments or custody. These questions leave room for bounded independent critique before any synthesis becomes accepted architecture.

**Source basis:** supplied 2A, 3A, and 4C direction; [TRACE track brief](../../../context/tracks/TRACE.md), [TL track brief](../../../context/tracks/TL.md), and [SST track brief](../../../context/tracks/SST.md). Prior substrate-direction memory was used only to preserve the broader transformation, lineage, inheritance, and outcome-oriented framing; it supplies no current project qualification.

