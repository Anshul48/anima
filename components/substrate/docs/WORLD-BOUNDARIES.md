**Worlds, responsibilities, and changeable relationships — proposal, 2026-10-02**

**Scope**

This develops the three architectural questions raised in the discussion: what a world can contain, what remains its responsibility, and what a relationship may change. It proposes tracks and boundaries; it does not select concrete module implementations or a permanent API.

The user's research ordering A → C → B → D is a preference among four bets, not an exhaustive four-stage development plan. Many substantial intermediate steps may precede physical co-design. Evolutionary mechanisms should be accommodated now while much of their implementation follows later.

**A world as a coherent environment**

A world is an identifiable computational environment in which participants, state, representations, operations, and local rules can function together. It can contain further worlds and expose selected capabilities to others. It may be temporary or long-lived, passive or actively coordinated.

A holon is a recognized computational whole that can participate in a larger whole. A world is a role such a whole can occupy: providing an environment for participants. World, module, and composite are useful roles at different scales rather than permanent classifications that prohibit later transitions.

One world need not correspond to one process, directory, agent, model, or objective. Its participants can have distinct purposes and representations. Its implementation can span processes or services, with actual execution placement recorded separately from conceptual organization.

**What a world can contain**

The available kinds of content should be extensible. Relevant initial kinds include:

- Agents, models, tools, operators, solvers, and independently developed systems.
- Memories, evidence, artifacts, local state, and shared working state.
- Schemas, representations, languages, interpretation rules, and mappings.
- Coordination policies, learning procedures, curricula, local objectives, and assessment mechanisms.
- Resource allocations, delegated capabilities, and lifecycle procedures.
- Child worlds, temporary coalitions, persistent composites, and relationship entities.

Containment does not require complete ownership or copying. A world can own an instance, borrow a capability, reference an external artifact, or participate in a shared facility. Those arrangements should be explicit.

For example, a construction world can use a memory capability hosted elsewhere. It can create a local experiment world and let that experiment cooperate with an external analysis participant. A useful arrangement can become a composite exported to other worlds without importing the construction world's entire internal machinery.

**Separate organizational axes**

| Axis | Question |
|---|---|
| Containment | Which environment hosts a participant's operation? |
| Ownership | Who may change particular state, resources, or commitments? |
| Access | What may a participant read, invoke, contribute, or influence? |
| Function | Which tasks or capabilities does a participant or coalition serve? |
| Execution placement | Where does the computation actually run? |

These axes can have different structures. Resource delegation may form a hierarchy, cooperation may form a graph, and functions may overlap. A participant can contribute to several coalitions without acquiring several conflicting owners of the same state.

Shared state needs an identified custodian or joint coordination rule. Creation of a coalition alone does not settle who can mutate the shared representation or how inconsistent updates are reconciled.

**What remains a world's responsibility**

A world should own the interpretation and operation of its declared local rules. It is responsible for the capabilities and commitments it actually exports, the resources it controls, and the organizational changes it performs within its authority.

| Responsibility | Implication |
|---|---|
| Local meaning and validity | Declare how representations and operations are interpreted, including assumptions and uncertainty |
| Exported commitments | Define what a capability returns, its applicability, and relevant failure or revision behaviour |
| State stewardship | Identify custodians, update rules, persistence needs, and any state required for recovery |
| Resource use | Account for actual consumption and deliberate delegation; share resources without counting them as newly created |
| Lifecycle | Distinguish suspension, interruption, detachment, termination, and replacement where applicable |
| Adaptation | Identify what can change, how feedback informs change, and what an updated instance inherits |
| Composite results | Distinguish constituent reports from conclusions made by the combined system |

The substrate supplies common means to enforce ownership and delegated limits, execute operations, track lifecycle, and preserve the relevant records. It need not define each world's subject matter or evaluate every domain claim itself.

Delegation transfers specified work and authority. A world retains its external commitment unless that commitment is deliberately transferred or revised. Fusion can move it into a new composite; fission must allocate it rather than leave it without an owner.

Identity continuity means the system can relate earlier and later organizations. It does not freeze their code, representations, membership, or responsibilities forever. An explicit transformation can create a new identity or alter ownership while preserving lineage and the meaning of past records.

**What a relationship may change**

A relationship is an active computational arrangement, potentially with its own state, implementation, adaptation procedure, and lifecycle. It can help create a composite and subsequently become an internal part of that composite. It is not limited to transporting messages between permanently fixed endpoints.

| Kind of change | Examples | Condition |
|---|---|---|
| Exchange | Routing, selected evidence, context packaging, timing, compression, communication precision | Meaning, omissions, and applicability remain assessable |
| Coordination | Work allocation, sequencing, synchronization, delegated execution, local resource agreements | Participating worlds provide the needed capabilities and resources |
| Shared machinery | Representations, workspaces, caches, joint state, common operators | Ownership and update semantics are established |
| Participant adaptation | Local strategies, parameters, schemas, code, or learning settings | The relevant participant exposes an authorized adaptation surface |
| Structural integration | Coalition, assimilation, fusion, specialization, splitting, or removal of redundant mechanisms | State, lifecycle, resources, commitments, and lineage are accounted for |
| Reuse and inheritance | Export a composite capability, preserve its construction recipe, instantiate a successor | State what is inherited, what remains local, and what must be reacquired |

A relationship can perform changes under standing delegated authority; ordinary adaptation need not require a human decision every time. Structural changes may require agreement from several custodians, and that agreement can itself follow established policies.

Learning that a participant is useful can affect selection and resource allocation. It does not by itself grant access to all that participant's state or settle the truth of its claims. Relationship confidence and authorization are different properties.

The outer resource and ownership rules remain effective during integration. A child can develop local rules or propose revisions to the shared substrate. Changing the common operating rules is a separate, versioned transition, rather than an accidental consequence of optimizing one local interaction.

**Change with continuity**

The important distinction is between preserving useful commitments and preserving a particular implementation. We should allow implementations and internal protocols to change while maintaining, deliberately revising, or transferring the commitments that other participants depend on.

Changes can be represented as candidate arrangements, tested or observed in their relevant environment, then adopted according to the applicable policy. Record the arrangement and transformation actually used. Existing work can retain its version or migrate explicitly when the new organization is suitable.

Mapping between representations may be approximate or hypothesis-bearing. Its declarations should preserve consequential assumptions and losses. Type compatibility alone does not establish semantic compatibility.

Not every split can reconstruct the original participants, and not every external effect can be undone. Integration should specify the available separation or recovery path rather than treating universal reversibility as a requirement.

**A proposed early path across the three questions**

Use a construction environment, a local experiment environment, and an independently hosted capability. Establish cooperation across their representations, then change how they coordinate in response to results. Demonstrate a subsequent integration that changes actual state or responsibility, and export the resulting composite for use elsewhere.

The first path can be designed by us. Later work can learn which adaptations help. Autonomous invention of new organizations, selection across populations, and improvement of the discovery process remain further research questions.

This path tests the substrate's organizational freedom without requiring each future cognitive module to be specified now. A demonstration of change establishes that the transition is supported; useful adaptive organization additionally requires evidence about outcomes and costs.

**Tracks recommended now**

- Open internal representations and participant kinds, with enough common conventions to exchange and act coherently.
- Separate containment, ownership, access, function, and execution placement.
- Explicit state and adaptation surfaces for relationships and participants.
- Composite capabilities that can operate at another level of organization.
- Deliberate transfer of responsibilities during integration and separation.
- Feedback, resource accounting, lineage, and inheritance information sufficient for later developmental and evolutionary studies.

These choices give the substrate meaningful organizational freedom while allowing implementation to proceed through selected transitions. Specific state stores, schedulers, negotiation algorithms, and module designs remain open.

Cordis provides scoped dependency contexts and formal machinery for dynamic composition. These can implement parts of the proposal; the world semantics above remain a separate design choice. [Context API](https://deepseek-harness.github.io/deepseek-harness/en/reference/cordis-api/context), [Cordis paper](https://arxiv.org/abs/2608.25512)
