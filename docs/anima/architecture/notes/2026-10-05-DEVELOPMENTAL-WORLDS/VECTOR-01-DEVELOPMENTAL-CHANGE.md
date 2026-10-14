# Vector 1 — What is a developmental change?

> Public curation note: links to records excluded from this public release were converted to plaintext historical references; the original record identities are preserved inline.

Architecture discussion, 2026-10-05. This is the full treatment of the first proposed vector. Its recommendations remain open for the user's later response. It develops [the macro synthesis](SYNTHESIS.md) and the earlier [world-boundary proposal](../../../../../components/substrate/docs/WORLD-BOUNDARIES.md), without selecting a runtime or beginning implementation.

**My starting position:** ANIMA should accommodate changes to the organization that produces a capability. Those changes can involve representations, procedures, participants, relationships, state, responsibilities and physical resources together. We should let the boundaries of an adaptation follow that causal problem, rather than require every adaptation to fit a module, an edge or a single atomic update.

This makes the first vector more precise. The question is not merely what is allowed to change. It is how useful organization can change while the system continues to operate, learn and understand the consequences.

## The thing that develops

Imagine a research capability that includes a memory expert, a planner, a simulator and an experimental procedure. Its performance depends on more than the individual quality of those ingredients. It also depends on which evidence reaches the planner, how conditions are represented, which disagreements prompt an experiment, how the simulator is interpreted, and what survives into the next task.

Those arrangements are part of the computational machinery. A relation can implement a learned consultation policy. A shared representation can eliminate repeated translation. A recurring coalition can acquire common state and procedures. A successful procedure can alter the way later capabilities are constructed.

The developing object is therefore an organization with behavior and a history. A graph can describe parts of it, but edges alone cannot express every relevant consequence. A new grouping in a visualization might change nothing operationally. Conversely, a changed shared procedure could substantially reorganize work without adding a vertex.

We should be able to identify development by what becomes possible, how work is performed, what dependencies arise, and what the organization can sustain. A topology diagram, a new identifier or a successful installation is evidence of a particular change; each leaves the broader capability question open.

This also preserves the user's larger canvas. The same question applies to a construction world, a society of experts, an embodied participant or an environment containing other environments. The mechanisms need not be the same at all those scales.

## There are three useful units, not one universal unit

The phrase “unit of developmental change” can conceal three different questions.

| Unit | What it describes | Example |
|---|---|---|
| Enacted change | What was actually modified and what effects occurred | A consultation policy changed; two participants began maintaining shared state |
| Assessed adaptation | The arrangement or trajectory whose usefulness is being investigated | A series of changes made exception-aware planning more effective |
| Inherited adaptation | What another instance receives or reconstructs | A conditional procedure for establishing that cooperation |

These boundaries may overlap, but they need not coincide.

A single code revision could enact changes to several mechanisms. Several revisions and many interactions could collectively produce a useful adaptation. A successor might inherit a short procedure rather than the whole accumulated state.

This distinction avoids a misleading search for the smallest universal cognitive “gene.” A representation, policy, composite or developmental rule may be the appropriate unit in one investigation. For another, the relevant unit is a sequence of coordinated changes. We can still study smaller contributions; doing so requires an account of their dependencies.

For the macro architecture, I would use **an adaptation episode** as a working description of a problem, developing arrangement and observed consequences. It is an analytical boundary we choose and revise. It need not be a mandatory database entity, a new service, or a claim that every process has a clean beginning and end.

An episode can overlap another. A relationship can develop before it has a formal name. Naming a composite can recognize organization that already exists, rather than cause it to exist.

## Development includes continuity and discontinuity

Some changes are incremental: a policy consults an expert more often, a representation gains an exception, a resource allocation shifts.

Other changes alter the available organization: a participant becomes an internal component; shared state replaces duplicated mechanisms; a composite acquires an exported capability; a world splits into descendants with different responsibilities.

The two can be connected. Repeated cooperation may gradually make a shared model indispensable. Eventually maintaining two independent copies becomes wasteful or misleading. Assimilation can then consolidate the mechanism. The useful transition is a trajectory, not necessarily an instantaneous merge.

The substrate should support that trajectory without forcing either permanent independence or immediate fusion.

A temporary coalition can also remain the best answer. Deep integration has costs: independence may decrease, separation may require reconstruction, and a formerly reusable component may become specialized to its host. Development does not require monotonic growth in size, dependency or complexity.

We need positive mechanisms for simplification too: pruning an unhelpful relationship, retiring a projection, removing redundant computation, dissolving a coalition, or extracting a useful specialization. Their success should be judged by retained capability and resulting costs.

## A concrete example: an exception-aware planning capability

Consider two initially independent worlds.

A historical-evidence expert can retrieve precedents and explain what happened. A planning expert proposes interventions. Both use source evidence organized by the responsible source system; neither owns arbitrary facts merely because it discussed them.

A recurring problem appears: plans look plausible but fail when a precedent depended on an unusual condition that was omitted from the handoff. This supplies a demand for change.

### Cooperation

At first, the planner requests a precedent and receives a passage. The worlds remain independent. Improving retrieval may help, but the failure might instead concern how the precedent is interpreted.

They try a richer exchange: situation, intervention, relevant conditions, observed outcome, counterexamples and uncertainty. This is a relationship change. It might be authored by an architect or proposed through search.

The important outcome is whether the richer exchange prevents consequential omissions. An elaborate format by itself is not an improvement.

### Co-adaptation

Experience shows that the historical expert's categories differ from the planner's. One groups situations by project topic; the other needs conditions governing whether an intervention can work.

The historical expert changes which distinctions it extracts. The planner changes how it requests and uses them. The relationship learns which unresolved conditions deserve clarification.

Both sides changed. A static adapter translating between unchanged categories would miss this kind of co-adaptation. The adaptation surface might initially be prompts, procedures and structured records; a trainable participant could later expose other surfaces.

### Shared machinery

The worlds begin maintaining a joint model of conditions and exceptions for a recurring task family. One participant may maintain evidence links, another may propose updates, and a joint rule may resolve conflicting edits. Responsibility is specified by operation rather than reduced to the word “co-owned.”

This shared machinery can exist before a named composite. The participants might still export different conclusions and preserve unresolved disagreement.

A single weight between them cannot describe this organization. We need the meaning of shared state, how it changes, who can use it, and what observations support it.

### A persistent composite

If the arrangement repeatedly helps, it can acquire a persistent working history and export an exception-aware planning capability. New callers need not reconstruct the cooperation themselves.

This can already be a useful composite while retaining its constituents. The functional interface, shared procedures and responsibility for the result are real organization; physical process consolidation is optional.

Deeper assimilation is a further possibility. A duplicated exception mechanism might be retired, its state transferred and its lifecycle coupled to the composite. A formerly external interaction becomes internal machinery. That transition changes dependencies and responsibility, even if the underlying model weights remain frozen.

We should not imply that every useful composition must rewrite its constituents. The point is that the architecture also permits stronger integration when it is justified.

### Separation and inheritance

Later, the shared work divides into two task families. Fission might create new experts with different state and obligations. It need not recover the original two worlds.

For example, an evidence expert can retain responsibility for supported historical conditions and their source links, while a new intervention expert retains planning procedures and responsibility for proposed actions. The shared exception model can be divided into domain views or remain a jointly maintained facility. Each successor needs the evidence and interpretation rights required by its obligations. If an old independent mechanism was retired, recreating it is additional work rather than a consequence of naming the split.

Another environment could inherit a mature exception model, a procedure for building one, or rules for detecting when this cooperation is useful. Those are different inheritances. Each needs conditions for use and a way to discover when it does not fit.

One inherited rule could respond to repeated mismatches between predicted plan outcomes and historical cases by creating a temporary exception-review arrangement. It would investigate missing conditions alongside competing explanations, construct an appropriate conditional representation, and retain cooperation only when its benefits justify the cost. The descendant can produce a different expert arrangement under a different workload. It inherits a way to develop, rather than an instruction to preserve the ancestor's exact organization.

This example tests the proposed abstraction. It is inadequate if it can describe the entire trajectory only as added edges or installed plugins, cannot represent shared responsibility before a named composite, assumes splitting restores the originals, or equates inheriting a procedure with copying a snapshot.

## What has to develop together?

The relevant boundary is the set of coupled mechanisms whose change is needed for the intended effect and whose compatibility must be maintained or revised.

A representation change may require an interpreter change. A shared-state change may affect update authority, consistency and recovery. A hand's tendon routing may require revised calibration and control. The scope follows those dependencies.

A useful conceptual starting point is the **dependency closure of the proposed change**: identify the affected mechanism, then follow the commitments and interpretations that depend on it. Stop where unchanged surroundings have a supported way to continue functioning.

This closure is relative to the task, available evidence and actual model of the world. We cannot reliably compute every semantic consequence of an arbitrary change. New observations can reveal missed dependencies and expand the scope.

The architecture should accommodate discovery of scope. A local trial might expose a shared assumption and become a joint adaptation. A concern thought to require widespread migration might instead be solved by a narrow translation.

This is why I would avoid two extremes. Requiring every change to remain inside one predefined box blocks necessary co-adaptation. Treating every dependency as a reason to rewrite the whole system prevents bounded progress. A supported boundary is something to establish and revisit, not merely inherit from the folder tree.

## A mathematical description that leaves mechanisms open

For reasoning about this vector, a world can be described as:

\[
\mathcal W_t=(X_t,\Gamma_t,\mathcal R_t,\mathcal A_t,K_t).
\]

Here, \(X_t\) is operational state; \(\Gamma_t\) describes relationships among participants and resources; \(\mathcal R_t\) contains representations and their interpretation; \(\mathcal A_t\) contains available operations and procedures; and \(K_t\) contains applicable commitments and rules.

This is bookkeeping for distinct responsibilities, not a proposed serialized universal schema. The description may be partial. Shared state, multi-party relationships, physical state uncertainty and overlapping functions need not fit an ordinary pairwise graph.

An enacted transition can be written:

\[
\mathcal W_t \xrightarrow{a_t\;\text{under observed conditions}} \mathcal W_{t+1}.
\]

The operation may be stochastic, gradual or composed of local steps. The environment also changes, so observed consequences should include effects outside the internal description. A sequence of such transitions can be the adaptation we assess.

A developmental rule is different:

\[
\widehat{\mathcal W}_{t+1}=D_{\phi}(\mathcal W_t,o_t,c_t).
\]

It uses observations \(o_t\) and relevant context \(c_t\) to propose a candidate organization, indicated by the hat. The rule could instead produce candidate operations. The parameters \(\phi\) could describe authored procedures, a learned policy, a generative program or a combination. The actual successor depends on enacted operations, interactions and environmental effects; it need not match the candidate. The notation does not promise that the rule is differentiable, autonomous or globally optimal, or require centralized adoption of every local update.

An inherited seed and rule can generate a trajectory in a new environment. A copied mature world supplies a starting state instead. These are useful separate claims about inheritance.

The formulation becomes misleading if we mistake the description for complete causal access. We might observe a better outcome without knowing which transition caused it. We might also preserve all identifiers while changing a representation enough that an old commitment no longer has a clear interpretation.

The practical obligation is to expose consequential uncertainty, not to pretend one equation formalizes the whole organism.

## What mechanisms could produce the changes?

Three complementary responsibilities from the macro synthesis become more concrete here.

**Available transformations.** Participants expose ways to adjust procedures, revise representations, transfer or share state, change relationships and develop composites. Some can initially be explicit operations. Domain mechanisms perform the actual reconciliation. A generic “merge” command cannot know how to merge arbitrary memories, models or physical artifacts.

**Adaptive selection and construction.** Local policies, architects or SST-like search identify useful moves, propose new operations when the repertoire is inadequate, and inspect feedback. A policy may learn when to consult, which condition to ask about, or when deeper integration is worth its cost. It may also modify its own domain mechanism through an exposed adaptation surface.

**Retention and inheritance.** Useful arrangements, procedures and developmental rules become accessible to future work. Applicability, dependencies, uncertainty and known failures accompany the reusable capability. Retention should permit eventual retirement or revision.

Those responsibilities can live in different places. A world can own its transformation mechanisms while the substrate supplies generic lifecycle and resource effects. A relationship can own a jointly developed translator. A composite can own a shared procedure. There is no need to select one universal executor before examining useful transitions.

The research frontier is not solved by naming these responsibilities. It concerns learning or constructing their content: which local signals predict useful reorganization, which transformations are adequate, and which forms of inheritance transfer.

## Local feedback without a master directing every microscopic step

The biological attraction is understandable: a high-level intervention can be incorporated through many locally regulated changes. For software, a corresponding research hypothesis is that participants can use limited local models, observations and available actions to repair or improve coordination.

In the example, a failed plan reveals that a condition was missing. The historical expert can improve the conditional representation; the planner can improve its applicability check; the relationship can improve when it requests clarification. The host need not reason through every domain detail.

But the observation does not uniquely identify a repair. A plan can fail because of bad evidence, an inadequate representation, a poor decision, an unexpected environmental change or a defective evaluator. Local feedback needs competing explanations and occasional discriminating intervention.

Prediction error is a useful signal, but minimizing it is insufficient. A participant could reduce error by avoiding difficult work, suppressing informative inputs or predicting an average outcome. The relevant question is whether the proposed adaptation improves the capability we care about.

Local rules should therefore have room to request evidence, revise their explanation, continue a bounded experiment or seek other expertise. Adaptation can pause where its information is inadequate; other independent work can continue.

This is a plausible alternative to a central model maintaining the entire architecture in its context. It still needs shared obligations and communication. Distributed adjustment does not guarantee coherent global behavior, and some changes need joint assessment.

## Three relevant precedents, with narrow implications

Growing Neural Cellular Automata learns local update rules that construct target patterns on a grid. Its experiments distinguish growing a pattern from maintaining it, and explicitly train stronger regeneration by damaging patterns during training. This supports studying learned local dynamics with construction, persistence and recovery as separate properties. It is a controlled spatial model with specified training targets, not evidence that cognitive worlds can discover arbitrary useful organization. The model and experiment descriptions were inspected; no reproduction was run. [Primary Distill article](https://distill.pub/2020/growing-ca/)

Foerster and colleagues study learned communication in specified cooperative tasks. Their DIAL approach uses differentiable communication during centralized training while agents execute in a decentralized manner. This supports treating interaction protocols as learned machinery. It does not give us a method for seamlessly coupling arbitrary frozen systems: that training setup exposes capabilities our heterogeneous worlds may not have. The primary abstract was inspected, not the full experimental methods. [Primary communication-learning paper](https://arxiv.org/abs/1605.06676)

Mergeable Nervous Systems reports robotic bodies and control systems that merge, split and replace malfunctioning parts. Its implementation uses a rooted body representation, identifiable controller roles and morphology-independent commands. The reported robots operate in two dimensions with rigid connections and designed behaviors. It supplies a particularly relevant precedent for coordinated structural and control change; it does not establish an open-ended cognitive ecosystem or a humanoid design. The publisher's indexed primary-article extracts for results and limitations were inspected. Direct browser retrieval failed at an authentication redirect; full-methods inspection and experimental reproduction are not claimed. [Primary Nature Communications study](https://www.nature.com/articles/s41467-017-00109-2)

These precedents provide mechanisms and useful limits. ANIMA's distinct architectural question is how heterogeneous capabilities, domain meanings and responsibilities can develop together across worlds. Combining these papers does not resolve that question automatically.

## What the substrate should supply, and what remains local

A proposed shared foundation should make participants and consequential artifacts identifiable, provide lifecycle and resource operations, carry observations and exchanges, and support attributable transitions. It should permit temporary arrangements and stronger integration.

Worlds supply their internal meaning, domain procedures, adaptation surfaces and assessment of exported capabilities. A host should not need to understand every discipline to contain its worlds.

Relationships can supply translation, consultation, synchronization and shared-state coordination. These mechanisms can themselves develop or be replaced.

A composite becomes a responsible participant when it has a coherent capability and an understandable account of the state and work supporting it. It can contain another world and participate elsewhere. This gives “a world that hosts other worlds” operational meaning beyond recursive naming.

The foundation also needs a route for changing itself. The first shared conventions should not become permanent laws through convenience. A change affecting many worlds has a larger continuity problem than a local adjustment; it needs an explicit transition rather than accidental drift.

There will still be shared conventions. Identity, artifact references, operation invocation and consequential state effects need enough common meaning for cooperation. For the arrangements considered here, cooperation needs sufficient shared operational conventions; learned protocols may develop above that floor. That does not presume their emergent semantics will be human-readable. Semantic interfaces can remain plastic while their operational effects are investigated.

I would keep the floor small and the domain mechanisms expressive. A universal ontology or fixed five-layer implementation could prematurely constrain the very organization we want to study.

## Responsibilities during a developing relationship

Responsibility need not be singular ownership of an entire world. Several participants can maintain different parts of shared machinery under a joint update rule.

The architecture needs to distinguish maintaining state, proposing changes, interpreting evidence, resolving conflicts, authorizing consequential actions and retaining obligations after dissolution. Those powers can be allocated differently.

For example, the joint exception model can have shared update rights, a source custodian responsible for references, and separate experts responsible for their interpretations. A composite can later acquire responsibility for a particular exported result without turning every constituent judgment into shared consensus.

Standing delegation can allow ordinary local adaptation. A world should not need a human interruption for every connection, parameter update or internal representation change. The relevant limits follow its actual commitments and granted powers.

A transformation can deliberately revise or transfer responsibility. Until that happens, a new group label must not leave an external obligation ownerless. This is part of making integration operationally meaningful, not a requirement to freeze today's ownership forever.

The detailed machinery for commitment enforcement belongs to vector 2. Here, the architectural point is that responsibility can change along with organization, and that change needs to be interpretable.

## Fusion, fission and the price of independence

The slogan “merge and split” can hide a false reversibility promise.

Two worlds can fuse while sharing a representation, retiring duplicated mechanisms and developing mutual dependencies. Later separation may require rebuilding a capability that no longer exists independently. If information was discarded, exact restoration can be impossible.

Fission may therefore create successors rather than restore ancestors. Lineage preserves where they came from; it does not preserve every former operational state. A new identity can represent continuity of some responsibilities and discontinuity of others.

This is especially clear in hardware. Two devices made from the same design are distinct specimens. Wear, material changes and calibration affect reuse. Reverting the controller does not restore physical state.

The developmental system should understand available recovery and reconstruction options, rather than pretend all changes are transactions with inverses. An adaptation can still be worthwhile if it deliberately trades independence for capability or efficiency.

That trade must remain visible. Increasing mutual dependence is not itself success. A resilient loose coalition may outperform a tightly fused composite under changed conditions.

## Representation changes and the meaning of continuity

A representation is part of how a world operates. Revising it can alter which distinctions are cheap to express and which possibilities are easy to consider.

Suppose two experts replace several uses of “supports” with different relations for empirical evidence, conceptual compatibility and causal contribution. Existing records may contain meanings that cannot be resolved mechanically. A version label identifies the transition but does not recover those meanings.

Possible responses include preserving the old representation for some uses, translating with explicit uncertainty, reopening consequential interpretations, revising a commitment's scope, or retiring an unsupported capability.

This is a real cost of development. We cannot promise that every new idea will require no migration or revision. What we can seek is a system in which the affected meaning is explicit enough to localize the work and retain operational continuity where justified.

The same principle applies to model-internal changes. A frozen model might support new behavior through external context, tools and coordination. Changing its weights is a separate adaptation surface, with its own evidence and compatibility problems. A host cannot create that surface by declaration.

Structured representations should also preserve material that does not fit neatly. Deltas and source references can retain exceptions; alternative views can keep unfamiliar distinctions available. The consequences for creativity and compression receive fuller treatment in later vectors.

## Timescales and the boundary between operation and development

The architecture should distinguish task activity from changes to the machinery used across tasks.

Reading a document is ordinary work. Revising how future evidence is selected can be adaptation. An expert partnership may start as task activity and become a recurring organization through retained experience.

These distinctions depend on the inquiry. An action that changes the external environment can also shape future learning. A small parameter update can influence many later decisions. We should examine consequences rather than rely on a rigid taxonomy.

Fast adaptation can occur inside established operating bounds. Changes to shared meaning or persistent organization may need slower observation. Descendant-level inheritance adds a further horizon. Different mechanisms can operate concurrently.

It would be wasteful to record every microscopic event as a separate architectural decision. Relevant observability can focus on consequential state effects, structural transitions, uncertainties, failure evidence and the information needed to evaluate the claim. Existing source systems retain their own fidelity obligations.

Likewise, a world need not wait for an entire developmental episode to end before learning from it. Local updates and partial findings can accumulate. The assessed episode can be reconstructed as evidence becomes available.

## How do we establish that organization helped?

The natural temptation is to point to a changed graph or a more compressed representation. Neither establishes the desired benefit.

For the exception-aware planner, compare actual outcomes under unfamiliar conditions. Ask whether omissions decreased, applicable counterexamples became easier to use, coordination cost remained justified and the inherited mechanism helped another workload.

Full costs matter: investigation, construction, extra retrieval, maintenance, reconciliation, migration and reconstruction. A locally cheaper message can make the system more expensive overall. A costly new abstraction can be valuable if later tasks become feasible.

Contribution analysis is harder after co-adaptation. Removing one mechanism from a jointly trained arrangement can create an incoherent or unfamiliar configuration. Its failure does not isolate that mechanism's original value. Comparisons should use meaningful alternative arrangements, restore required compatibility where possible, and state where causal attribution remains uncertain.

Measurements can improve. The target should not silently move with them. If success appears only after changing acceptance criteria, separate that change from improvement under the original claim.

Evidence should support increasingly strong statements:

| Claim | Relevant evidence |
|---|---|
| Change is supported | Actual affected state, relationships and responsibilities can transition coherently |
| Change improves a task family | Better relevant outcomes against a capable comparison, with costs visible |
| Adaptation transfers | Useful outcomes persist under held-out demands or changed environments |
| Inheritance helps | A successor obtains an advantage from retained arrangements or developmental rules |
| Development remains useful over time | Continued adaptation avoids accumulating harmful dependency, drift or maintenance burden |

These are claims to investigate, not a compulsory universal gate sequence. A particular world may need a different assessment. No evidence at the first level licenses all the later claims.

## My architectural recommendation

I would preserve five commitments for the next design stage as proposals for discussion.

1. **Adaptation can cross component boundaries.** Representations, relations, state, procedures and responsibilities can develop together. A module boundary is a starting organizational choice, not the mandatory boundary of change.
2. **Continuous co-adaptation is first-class.** Temporary cooperation, partial integration and overlapping development can exist before a named persistent composite.
3. **Change, assessment and inheritance have distinguishable scopes.** We should not force the enacted operation, causal learning problem and descendant's inheritance into one universal object.
4. **The substrate supports real transformations while local worlds supply meaning.** Shared lifecycle and resource machinery can coexist with heterogeneous domain adaptation mechanisms.
5. **Inherited capability retains conditional meaning.** A snapshot, procedure or generator includes enough applicability, dependency and failure context to support responsible reuse and further development.

The shared foundation can begin with existing mechanisms. Their use is valuable when they support real changes and demanding callers; merely wrapping them in new terminology supplies little evidence. Richer local learning and developmental rules can be introduced where they resolve a capability problem.

I would leave open the permanent host, exact operation language, universal schema, degree of federation, model-training method and population-evolution machinery. Choosing them now would not answer the key causal questions. Leaving them open should still permit concrete work on a few transformations.

For the first demanding architectural scenario, I favor the historical-evidence/planning cooperation described above, with a subsequent composite, separation and inherited procedure. A second scenario should change a representation across a construction workflow. A third should change morphology, sensing and control together in a physical-development model. These scenarios test different meanings of development rather than demand three immediate builds.

## What this vector leaves us with

The emerging position is a substrate in which organization is part of the adaptable state, with mechanisms for constructing that organization and retaining what makes it useful.

Its smallest useful unit is contextual. Some adaptations fit a local operation; others are multi-party trajectories. Their boundaries should be discoverable through dependency, observation and consequences.

The next vector can examine how attention and commitments remain effective across those trajectories: which context is brought into an action, what must be checked independently of that context, and how legitimate revision differs from drift.

The user can read the full round before responding. No architectural commitment is ratified by this essay or by proceeding to the next vector.

**Review note:** A separate agent stress-tested the conceptual framing and read the draft. The final text addresses its findings by distinguishing candidate organization from enacted successor state, narrowing the shared-conventions claim, and making separation and inherited developmental rules concrete. It found no major conceptual fault in the inspected draft. This was a documentary review; sources and experiments were not independently reproduced by the reviewer.
