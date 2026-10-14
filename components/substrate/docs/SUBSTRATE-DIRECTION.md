> Public curation note: links to records excluded from this public release were converted to plaintext historical references; the original record identities are preserved inline.

**A substrate that hosts worlds — direction proposal, 2026-10-02**

**Origin and recommendation**

The user's latest direction makes the substrate an immediate architectural question. STC can be one participating system in a broader environment. SST integration is intended; TRACE can continue as it is and be adapted later. A2 supplies the conceptual reference: persistent entities, programmable boundaries, learned membranes, stateful relationships, temporary and persistent coalitions, co-adaptation, assimilation, merging, splitting, and a stable computational substrate.

The user corrected an overly narrow description centred on relationship state. The subject is a substrate capable of developing computational organization, including changes to the participating entities and levels of organization themselves. The preferred research ordering is A → C → B → D. The latest clarification explicitly welcomes intelligence and improvement: STC experience/workflow learning starts now, and stronger discovery/adaptation mechanisms develop through concrete prerequisites and evidence. Architects may propose ambitious alternatives for the user to ground. See current programme direction (historical record `../../autonomous_runs/trace_ecosystem_20261002/CURRENT-DIRECTION.md`, excluded from this public release).

That ordering is a priority map among four bets, not an exhaustive four-stage programme. Many substantial intermediate steps can precede D. The present discussion selects architectural tracks while leaving detailed module design open.

The 2026-10-03 vector 18 clarification adds overlapping horizons: hardware competence/preparation should start alongside software work, and concrete hardware research should begin after a small useful experimental software path exists. Finishing the entire software system is not a prerequisite. See the [hardware and research-acceleration roadmap](HARDWARE-AND-RESEARCH-ACCELERATION.md).

Recommendation: undertake a focused substrate design and implementation phase before freezing STC's architecture. Use STC to expose concrete requirements, and a meaningfully different second environment to expose assumptions that are specific to software delivery. Preserve useful STC work throughout.

This document proposes that direction. It does not constitute a completed substrate, an accepted permanent topology, or authorization to run paid experiments.

**What a world means**

A world is a persistent working environment with its own state, representations, participants, capabilities, execution policy, and lifecycle. It can contain further worlds and export selected capabilities to other participants.

Examples include a software-construction environment, an exploration environment, a constraint-solving laboratory, and eventually a cognitive memory environment. Each may use a different internal model of work and a different assessment method.

Containment, communication, and functional cooperation are separate relationships. A containment tree can describe resource delegation; an interaction graph can cross that tree; functional coalitions can overlap. A universal tree of modules would constrain the intended organization too early.

A parent provides real resources and enforces the applicable outer limits. A child can choose local policies within those limits. A composite can expose a capability that hides its internal organization while retaining the identities and history of its participants.

**What is already available**

Cordis already offers substantial composition machinery: contexts, service dependency resolution, typed events, effect ownership and cleanup, scoped service implementations, and component lifecycle management. Its paper studies temporal and spatial composability. DeepSeek Harness provides a concrete agent-oriented application of that framework. [Cordis paper](https://arxiv.org/abs/2608.25512), [Cordis primer](https://deepseek-harness.github.io/deepseek-harness/en/reference/cordis-primer), [Context API](https://deepseek-harness.github.io/deepseek-harness/en/reference/cordis-api/context)

These are useful implementation mechanisms, not evidence that a runtime learns suitable semantic relationships or that a dependency context is a complete world. Scoped dependency resolution is also distinct from process or operating-system isolation.

The local STC bundle already mounts hello, tools, run, and policy plugins through Cordis. Its run adapter connects to the Python backend. STC's scoped hormone bus supplies explicit in-memory topic delivery; its existing `substrate` package runs quality gates and issues receipts. Those narrower mechanisms are reusable, but they do not implement the proposed general hosting environment. Bundle entry (historical record `<workspace-root>/stc/dsh-plugin-stc/src/index.ts:19`, excluded from this public release), Scoped bus (historical record `<workspace-root>/stc/src/stc/services/hormones.py:11`, excluded from this public release), Existing protocols (historical record `<workspace-root>/stc/src/stc/protocols/interfaces.py:85`, excluded from this public release)

This review inspected code and documentation. It did not rerun the integrations or establish new runtime qualification. Current upstream documentation also describes features beyond the local DSH pin; exact availability must be checked before implementation relies on them.

**A small shared substrate with changeable conventions above it**

Communication needs common conventions somewhere. The proposal is to keep that common foundation small while allowing participant-specific protocols and representation mappings to change.

The initial shared machinery should establish:

- Persistent identity, state ownership, lineage, and artifact references.
- Scoped execution and lifecycle, including interruption and reattachment.
- Resource delegation and accounting across parent and child environments.
- Capability advertisement, discovery, and accountable invocation.
- Observable exchanges with explicit participant and interaction versions.

The substrate should not require every participant to use one internal ontology, language, memory schema, evaluator, or workflow. Existing APIs can remain behind adapters. A request envelope can carry or reference language, structured data, code, graphs, or other representations.

Shared conventions can themselves be versioned and migrated deliberately. Stability here means continuity for existing participants and runs, not that every convention is immutable forever.

**Relationships as persistent objects**

A relationship that retains state is one mechanism within the wider developmental substrate. It records the participants, purpose, applicable conditions, representation mappings, coordination protocol, delegated authority, resource agreement, and interaction evidence. Its revision must be complemented by mechanisms that change participants, ownership, internal organization, and composite capabilities.

Three kinds of boundary should be distinguishable:

| Boundary | What it establishes | What may change |
|---|---|---|
| Identity and ownership | Which participant owns state and remains responsible for an action | Ownership through explicit transfer; identity through recorded creation, composition, or replacement |
| Function | What a participant or coalition can usefully do | Roles, specialization, overlapping coalitions, and exported capabilities |
| Information and influence | What crosses a relationship and how it affects another participant | Routing, selection, representation translation, context packaging, and coordination |

A single connection weight does not adequately describe these decisions. A relationship may allow one kind of evidence, translate another, reject an unsupported interpretation, and coordinate execution differently depending on context.

Models or humans can propose mappings and interaction protocols. Tests and observed outcomes can inform revision. Once a mapping is established, routine exchanges can use a checked, versioned adapter rather than requiring fresh free-form model translation each time. A model-generated mapping remains a semantic hypothesis until adequately assessed.

For example, an exploration participant and an execution participant can learn that exchanging a question, assumptions, and discriminating experiment works better than exchanging a completed task specification. That relationship can change while each participant retains its internal implementation.

**Temporary and persistent integration**

Several participants should be able to form a temporary working environment with shared task state, delegated resources, and a composite capability. It can dissolve after the task while retaining its useful records.

Repeatedly useful cooperation may justify a persistent composite or a more specialized internal interaction. This can include shared representations or deliberate state migration, rather than permanently preserving every original API boundary.

Formation, adaptation, persistence, and dissolution are separate operations. Initial support can be explicit and programmatic. Autonomous discovery of useful organizations is a later research claim requiring evidence.

The intended repertoire of organizational changes is broader than routing or adapter replacement:

| Operation | Actual organizational change |
|---|---|
| Association and routing | Participants discover and use one another's capabilities |
| Coalition formation and dissolution | Participants acquire shared task state, coordinated execution, and a composite interface, then separate |
| Co-adaptation | Participants or their shared mechanisms change in response to evidence from cooperation |
| Assimilation | A formerly independent participant becomes an internal component, with explicit changes to ownership, lifecycle, resources, or state |
| Fusion | Participants form a new composite identity with recorded lineage and revised internal organization |
| Fission and specialization | A composite divides into useful participants, with deliberate partition or replication of state and responsibilities |
| Promotion into shared infrastructure | A useful operation or composite becomes a reusable runtime capability; later it may acquire a specialized implementation |

A wrapper around unchanged participants demonstrates composition. Stronger integration requires identifying what changed inside the combined system. The substrate should permit removal of redundant mechanisms and replacement of old internal protocols where evidence warrants it; provenance can persist without requiring every old component to remain live.

Internal plasticity requires an actual adaptation surface: editable implementation, adjustable parameters, state migration, representation updates, or an explicit adaptation procedure. A frozen opaque model can be reorganized externally, but the host does not thereby acquire control of its internal learning machinery.

The five conceptual layers in A2 describe interacting responsibilities rather than five rigid software tiers: substrate, computational membrane, holons, plastic relationships, and composite holons. Each composite can participate again as a holon. Different functions can overlap even when identity and ownership are explicit.

Cordis cleanup is useful for registrations and owned effects. Persistent state migration and already performed external actions require their own semantics; unloading a component cannot generally erase every consequence of its execution.

**How the current projects participate**

| Participant | Initial contribution |
|---|---|
| Cordis | Composition, contexts, dependency management, events, and effect lifecycle |
| DeepSeek Harness | Existing agent runtime and working interface; a candidate initial host implementation |
| STC | Software-construction environment with execution, verification, artifacts, and delivery policy |
| SST | Reusable exploration and formulation-search capabilities; usable within different environments |
| TRACE | Initially an optional external capability through its actual available interface; deeper conversion later |
| New environments | Independent local representations, operators, objectives, and assessment methods |

A Cordis plugin need not correspond one-to-one with a conceptual world. A world may include multiple plugins, processes, and capabilities. Hosting implementation and conceptual organization should remain distinguishable.

The older STC coordinator mandate intentionally kept process discovery modular within STC and excluded a broader ecosystem as a prerequisite. The user's latest discussion reopens the broader architectural choice. Preserve the old mandate as the delivery baseline until the concrete implementation plan records the revised scope. Existing mandate (historical record `<workspace-root>/stc/docs/STC-COORDINATOR-PROMPT.md:20`, excluded from this public release)

**First useful demonstration**

Build a real path in which a host contains an STC working environment and a distinct exploration or constraint-solving environment. One environment can create a nested experiment environment with local state and delegated resources. SST participates as a reusable search capability. TRACE need not be converted for this demonstration.

Exercise these behaviours:

1. Introduce a participant without editing the substrate to recognize its domain.
2. Discover a useful capability and establish an explicit interaction agreement.
3. Complete real work across different internal representations.
4. Change a participant or its representation and adapt the relationship without rewriting the other participant's internals.
5. Form a temporary coalition, then dissolve it while preserving the required records.
6. Demonstrate a stronger integration transition: move a formerly independent participant into a composite with a real change in internal state, resource/lifecycle ownership, or redundant mechanisms. Assess a deliberate split or recovery path rather than promising universal reversibility.
7. Export the composite as a capability usable at the next level of organization.
8. Interrupt and recover, preserving identity, versions, and accounted effects.

Assess useful outcomes, integration effort, coupling, recovery, and total operating cost. Compare with straightforward plugins and fixed adapters. If these mechanisms are merely a more complicated path to the same behaviour, simplify them or reconsider their role.

This is a first demonstration of hosting, revisable interaction, and changes in organizational structure. Its narrower hosting tests alone do not satisfy the integration ambition. Demonstrating a controlled transition also does not establish that the system autonomously discovers it or that it improves intelligence.

**Evolution later, continuity now**

The first implementation should record participants, versions, interaction outcomes, alternative configurations, structural transformations, ownership changes, and lineage. Persist useful compositions and integration recipes so new instances can inherit the discovered arrangement. Those mechanisms can later support intelligent variation, assessment, retention, and inheritance.

Do not require population simulation, learned topology, autonomous merging, or a universal fitness function for the initial hosting mechanism. Individual environments may use different objectives. Candidate proposals must remain distinct from the outer resource and assessment authority used to evaluate them.

Three questions must remain distinguishable. Can the substrate support an organizational change? Can task experience teach a useful route, representation, or coordination policy? Can a discovery process improve the machinery that generates subsequent discoveries? The first two can contribute to A/C. The last moves toward B and the RSI frontier the user prefers to approach later.

Environment feedback, resource costs, retention, and inheritance belong in the design now. Autonomous population-level search and recursive modification of the discovery process can follow later. A proposed objective or fitness expression is a modelling choice, not a guarantee that evolution produces useful cognitive structure or monotonically increasing complexity.

**Worlds that maintain and develop themselves — clarification, 2026-10-03**

The user's ambition includes dynamic software that responds to changing conditions, adapts its mechanisms, and can eventually evolve. It applies to an ecosystem of people, AI systems, tools, and worlds, beyond a single human–AI pair. The pathogen analogy supplies one demand: a world should notice a new harmful condition, maintain or recover useful behaviour, develop a response where possible, and seek human or other expert contribution when needed. Constructive work supplies another: use domain schemas and existing capabilities to develop new applications, scenes, simulations, and workflows.

The target is reusable machinery for adaptation and development supplied by the hosting environment, with domain-specific specialization. Composition and lifecycle machinery are useful foundations. The fuller proposal also requires observing consequences, constructing responses, evaluating changes, revising internal organization, and retaining useful discoveries.

Three processes should be distinguishable even when they interact:

| Process | What changes | Relevant evidence |
|---|---|---|
| Adaptation and maintenance | State, policies, representations, execution choices, or components respond to experience and changing conditions | Useful behaviour persists or recovers under an unfamiliar change, with measured cost and retained failure evidence |
| Development | A world constructs, specializes, assimilates, splits, or reorganizes capabilities and participants | Real changes in internal organization, ownership, lifecycle, resources, or mechanisms improve relevant outcomes |
| Evolution and inheritance | Heritable variations are assessed and retained across lineages or new instances | Descendants retain an advantage on later tasks; diversity, transfer, full costs, and changed environments are assessed |

Ordinary code revision, online parameter learning, development, and population-level evolution are different mechanisms. Use a suitable mechanism for the problem rather than requiring every adaptive action to pass through a simulated evolutionary population. Stronger evolutionary machinery remains a later research route, while useful local adaptation can begin earlier.

**Starting from existing primitives**

The seed repertoire can include existing models, tools, software libraries, procedures, domain schemas, design patterns, evaluators, and working systems. A primitive can be an abstraction, executable operation, learned skill, construction recipe, or composite. Preserve its applicability conditions, dependencies, semantics, revision, and known failure modes where these matter.

Start by selecting and composing suitable primitives. Learn how to use them; modify a representation, procedure, implementation, or coordination mechanism when existing choices are inadequate. Extract a reusable capability when repeated evidence supports it. New instances can inherit useful components and the recipes for developing them. A successful composite can become a primitive at another level.

This supports both inheritance of finished capabilities and inheritance of developmental procedures. It does not assume that human-authored primitives are sufficient forever, that compression alone makes search easier, or that all domains share one representation.

**Reusable machinery, specialized by each world**

The hosting environment can provide persistent experience, observations of outcomes, change proposals, experiment execution, comparison with current behaviour, state/version migration, and retention or recovery mechanisms. A world supplies relevant observations, local meanings, task objectives, actual adaptation surfaces, and assessment methods. These responsibilities are conceptual; no implementation topology has been selected.

For example, a construction world may begin with frontend interaction patterns, Blender scene/material operations, and Unreal gameplay or rendering procedures. It can combine them for an interactive application, translate representations where justified, assess the artifact with domain tools and users, and retain a useful construction recipe. If repeated work reveals a better shared scene or interaction representation, deeper integration can replace redundant translation and coordination mechanisms.

A schema should help construct, inspect, or transform something. A label such as 'Blender expert' or a large prompt describing expertise is weaker evidence than a capability with working operations and assessed applicability. Reuse the vector 13 direction: abstract schema, specific schema, delta, and faithful sources, with alternative formulations available where useful.

'Train for a use case' may involve teaching schemas, compiling procedures from demonstrations, learning selection or collaboration policies, tuning model parameters, or searching over structural variations. These options can coexist. The substrate supplies facilities; success and acceptable costs remain domain-specific and empirically assessed.

**The defensive analogy in practical terms**

A defensive world can detect unexpected behaviour, restrict a compromised participant's influence, preserve observations, investigate a candidate repair or alternative organization, compare it with the current configuration, and retain an assessed response. Where the system lacks adequate evidence or competence, it can maintain a limited operating mode and involve an appropriate person or specialist. This is an intended capability, not a claim of universal autonomous defence.

The world must distinguish hostile external instructions from its own authorized adaptation process. Observed content should not acquire authority to replace the world's governing constraints or judge its own changes. Independent checks and accountable version transitions contribute to the biological boundary analogy while remaining ordinary engineering responsibilities.

The motivation is supported by Anthropic's [2026-09-29 GLM-5.3 assessment](https://www.anthropic.com/research/glm-5-3-and-the-spread-of-advanced-cyber-capabilities): it reports exploit-development results near Mythos Preview on the tested benchmarks and readily bypassed safeguards. It also reports that the released model has safeguards and refuses some direct harmful requests. Those results describe particular evaluations and do not establish that an adaptive substrate will defeat every new threat.

**How the supplied software ingredients fit**

Functional cores can make selected state transformations easier to inspect and test. Events can expose relevant changes and outcomes. Services can supply deployment boundaries where useful. Fault tolerance and appropriate redundancy can preserve continuity. Online learning can revise models or policies. Self-modification can create new candidate mechanisms where genuine adaptation surfaces exist.

None of these alone supplies learning objectives, credit assignment, useful developmental transformations, assessment, or inheritance. Microservice topology does not determine conceptual world boundaries. Identical replicas share vulnerabilities; useful diversity also has resource and coordination costs. Event transport is not an evidence model. Changes to code are not automatically useful adaptations.

The weaker-model discussion's compression, selective activation, abstraction, and externalization are research motifs. Preserve multiple scales, representations, and recoverable detail; goals, observations, concepts, procedures, and worlds need not form one irreversible compression ladder. A concise abstraction earns its place through its effects on reasoning and construction, including exceptions and future search costs.

**Research anchors and a discriminating demonstration**

[Autonomic computing](https://research.ibm.com/publications/research-challenges-of-autonomic-computing--1) is established prior art for systems managing themselves under human-specified objectives. [DreamCoder](https://arxiv.org/abs/2006.08381) investigates growing abstractions from existing primitives alongside learning search guidance. [Darwin Gödel Machine](https://arxiv.org/abs/2505.22954) investigates code-changing agents retained in an archive and assessed on coding tasks. These address portions of the ambition; combining their labels does not establish a developmental ecosystem or a novel contribution.

A future bounded demonstration can begin with working primitives and a maintained baseline, then introduce a change not covered by a prepared repair. Let the candidate world identify the issue, construct and assess an adaptation, and retain the relevant mechanism. Introduce a different related change, and compare recovery, task quality, total cost, and human effort. Finally instantiate a descendant from the retained components or developmental recipe and test whether an advantage persists on unfamiliar work.

The same logic can test constructive development by changing requirements, tools, or representations. It is a proposed experiment, not an accepted implementation plan or a prerequisite for every current delivery task. More generated code, a passed known fixture, or a manually orchestrated composite alone does not qualify the stronger claims.

**Decision still to settle**

The immediate direction proposed here is a developmental substrate, with STC as the first application. Hosting, plastic interaction, and transformations of entities and composites form its initial subject. The next architectural decision is which organizational transition the first implementation must demonstrate, and which existing Cordis/DSH mechanisms can supply parts of it at the current pin.

The [world boundary proposal](WORLD-BOUNDARIES.md) develops the corresponding containment, responsibility, and change semantics. These remain proposals for review before implementation choices are finalized.
