# Vector 2 — Attention, commitments, and legitimate revision

Architecture discussion, 2026-10-05. This is the full second-vector treatment. It follows [Vector 1](VECTOR-01-DEVELOPMENTAL-CHANGE.md) and develops the user's 4C ideas using the [creativity-and-constraints dossier](CREATIVITY-AND-CONSTRAINTS.md). Recommendations remain proposals while the user reads the vector round.

**My starting position:** an adaptive world needs both selective attention and continuity of commitments. Attention determines which information helps the current decision. Commitment continuity keeps applicable obligations effective through distraction, compression and reorganization. The two should cooperate without making relevance, familiarity, truth and authority interchangeable.

The architectural opportunity is broader than attaching a rule checker to an LLM. We want a world that can use limited context intelligently, recognize when its interpretation is inadequate, preserve what it has undertaken, and change its beliefs and methods without silently changing the meaning of success.

## Why this follows developmental change

Vector 1 allowed representations, procedures, relationships, participants and responsibilities to develop together. That creates a difficult continuity problem.

A planner can acquire a different representation. Two experts can form a composite. A temporary experiment can become a recurring procedure. The conditions supporting an old decision may change. Some commitments persist through the transition; others may be fulfilled, transferred or deliberately revised.

Neither a longer transcript nor a persistent identifier resolves that problem. We need to know which obligations apply now, what they mean in the current representation, and how a proposed action affects them.

At the same time, most historical material should remain outside active attention. A system operating across enormous archives cannot load every explanation and inspect every disagreement at every step. Its working context needs to be selective and expandable.

The aim is useful continuity with limited attention. This is a capability problem as well as an accountability problem: the system should spend less effort reconstructing settled intent, retrieve the exception that changes a decision, and ask fewer unnecessary questions while continuing useful work.

## The two jobs in 4C are different

The user's first job is to select salient information for each micro-step. Its practical interpretation should be decision-conditioned context selection.

A model drafting a hypothesis, a tool applying an edit and a composite transferring shared state need different information. Relevance depends on the intended operation, current conditions, unresolved uncertainty and consequences. Selecting context once at task entry will often be inadequate.

The second job is long-horizon consistency and constraint enforcement. It includes retaining applicable requirements, recognizing revisions and avoiding unsupported reinterpretation.

An obligation can be absent from the immediate prompt yet remain binding. Conversely, a remembered statement can be obsolete, hypothetical, incorrectly interpreted or irrelevant to the present scope.

The two jobs have different failure measures. Attention can fail by omitting decisive evidence, retrieving distractions or narrowing exploration too soon. Commitment continuity can fail by losing an obligation, applying a superseded one, misinterpreting its scope or permitting effects inconsistent with it.

A single relevance score cannot reliably settle all those questions. It can contribute to several judgments, but their meanings and consequences need to remain distinguishable.

## Five distinctions I would preserve

| Kind of information | What it contributes | How it can change |
|---|---|---|
| Learned salience | Estimated relevance, urgency, surprise or information value | Experience changes attention allocation |
| Schema or procedural preference | Expectations about plausible structures and useful methods | Exploration and outcomes revise the prior |
| Belief or hypothesis | A claim about the world, with evidence and uncertainty | New evidence changes support or interpretation |
| Commitment or governing rule | An obligation with a source, scope and applicable decision rights | Fulfillment, authorized revision, transfer, expiry or other declared conditions |
| Check and coverage claim | A method for assessing a represented condition | New measurements and methods change what can be established |

These are roles that can overlap, not a prohibition on integrated learning. A useful learned representation may help both relevance and applicability. The architecture still needs to distinguish the decisions it supports.

For example, “this procedure usually succeeds” is a belief. “Prefer it for this task family” is a policy. “Preserve source attribution in the exported result” is a commitment. A checker establishing that cited identifiers resolve supplies a narrower assessment. None of these substitutes for the others.

Accepted facts and accepted obligations also differ. A scientific claim should be revisable through evidence. An obligation should follow its legitimate scope and revision process. Treating every accepted statement as an immutable instruction would entrench mistakes.

Similarly, a person's observed habit is not automatically an objective. The user may choose to depart from a habit or invest in an unfamiliar direction. A personal model can help predict useful assistance while preserving the distinction between observation, aspiration and instruction.

## Attention should be conditioned on a decision

The useful starting question for a context selector is what the next decision could change.

A retrieval query such as “planning” is broad. A decision such as “choose whether this precedent applies to the proposed intervention” calls for the conditions of that precedent, relevant counterexamples, the present situation and the consequences of an incorrect match.

A proposed working context should therefore include a compact account of the current objective, the operation under consideration, relevant state and versions, applicable commitments, supporting and challenging evidence, and consequential unknowns.

The proportions vary. A routine exact transformation may need little domain history. A formulation change may need alternative representations and failures. A shared-state transition may need information from several custodians.

Selection can use lexical retrieval, structured indexes, learned policies, prediction models and cheap decision tools. A powerful generative model can help diagnose what is missing. None should be a mandatory universal front door.

“Only what is needed” is a useful optimization target, but it presumes knowledge the selector may not yet have. A short context can appear sufficient precisely because it omits the evidence that would expose its insufficiency.

The context should be expandable. Missing dependencies, contradictions, unexpected observations and changing objectives can prompt another retrieval or consultation. Some exploratory capacity should reach beyond the currently favored interpretation.

Prediction-error recovery alone will miss errors that never produce a visible discrepancy. Periodic contrast, selected counterexample searches and externally measured outcomes are candidate complements. Their benefits and cost need assessment.

## Stored, supplied, used and enacted are different

A requirement can be stored in the archive without being retrieved. It can be retrieved without influencing the model. It can influence a generated explanation without governing the actual tool action.

This gives four distinct questions:

1. Was the relevant information retained and accessible?
2. Was it supplied to the right decision?
3. Did the decision process interpret and use it appropriately?
4. Did the realized action have the intended constrained effects?

A retrieval benchmark mostly addresses the first two. A reasoning evaluation may address the third. The fourth needs an account of actual execution and consequences.

The architectural implication is that some continuity mechanisms must exist outside a model's present recollection. A resource limit can remain effective through resource management even when it is not repeated in prose. A precise requirement about an artifact can be checked against that artifact. An uncertain semantic obligation still needs interpretation.

Discovering applicable commitments is itself a coverage problem. Ordinary relevance ranking cannot establish that every applicable obligation has been found. Scoped inventories, operation-linked dependencies and targeted obligation searches are possible aids. Where discovery remains incomplete, the system should expose that limitation; omission is not evidence of inapplicability. Retaining a requirement somewhere does not establish that the responsible operation can recover it.

This does not justify moving all rules into a central controller. It suggests locating each responsibility where it can observe and affect the relevant state, with clear boundaries for cross-world obligations.

## Selection, influence and effects

A useful functional decomposition distinguishes selecting what enters a working context, determining which information influences a candidate, and controlling consequential effects.

The first can recover context. The second can maintain a task frame, compare alternatives or challenge a learned schema. The third concerns what actions actually occur.

These functions can interact throughout work. A check may reveal missing context. A candidate may reveal an inadequate rule interpretation. An observation may justify a belief update. This need not be a rigid serial pipeline.

There is a relevant biological lead. Chatham, Frank and Badre distinguish admitting information to working memory from selecting which maintained information drives behavior. Their hierarchical-task fMRI results support a corticostriatal output-gating hypothesis. That is useful functional inspiration, not a demonstrated mechanism for indefinite commitment enforcement in software. The primary abstract and indexed article excerpts were inspected; direct PMC access encountered a browser challenge. [Primary Neuron study](https://pubmed.ncbi.nlm.nih.gov/24559680/)

For ANIMA, I would resist assigning each function to one anatomical name or one LLM. The benefit should come from its effect on behavior, not the resemblance of a diagram to brain regions.

## A commitment needs more than its text

A durable commitment should remain associated with its source, accepted status, scope, responsible party, conditions and relevant revisions. Different obligations need different detail.

Scope can concern a task, artifact, phase, participant, environment, time interval or version. “Use an approximate method in the exploratory branch” does not authorize replacing an exact method in the accepted product path.

Conditional commitments also need their conditions preserved. An obligation can become active only when a dependency is used. Another can cease after fulfillment. A third can remain relevant to a result long after the participant that created it has dissolved.

The source matters. A direct user decision, an agreed interface contract, a domain rule, a generated proposal and a quoted document occupy different roles. Recency alone does not determine authority. A new message can contain old quotations or another model's speculation.

Revision must be possible. A commitment can be fulfilled, superseded, narrowed, transferred or revoked under the applicable rights. The operative view should recover the current applicable meaning while retaining enough history to understand past work.

That history does not need to burden every active traversal. Current obligations can have a compact operational view; deeper historical analysis can pay for recovering earlier records. The source systems retain their own provenance and retention responsibilities.

This is consistent with a costly hot graph and colder faithful records. Temperature and authority are independent: an inactive historical decision may explain an old result, while an active suggestion may remain unaccepted.

## How I would think about constraint compilation

The user's knowledge-compiler idea can apply here, with an important boundary: compilation can organize an interpretation, but it cannot make every natural-language obligation precise by formatting it.

A proposed process could retain the original requirement, construct a scoped interpretation, identify relevant conditions and dependencies, and connect any tractable parts to checks. The resulting operational view can be much smaller than the entire discussion.

For “preserve exact ranking,” the interpretation might include score computation, tie handling, stable identifiers and observable output. A mechanical comparison can establish equality for particular inputs or an explicitly represented algorithmic property. The phrase may still leave questions about changed inputs, undefined scores or old ordering conventions.

The compiled form therefore needs coverage and unresolved interpretation. Some clauses can be enforced precisely; others require evidence or further judgment. A successful check should be reported at that actual scope.

Abstract schema + domain schema + delta can help. The abstract layer describes obligations, conditions and revisions. The domain layer supplies meaningful operations and effects. The delta retains unusual requirements, exceptions and ambiguities.

These are possible representational roles, not a selected universal language. A shared schema may itself evolve. Old commitments must remain interpretable or be deliberately migrated; silently changing the compiler's interpretation can change accepted behavior.

Compilation also needs a route back to source. A compact rule that drops the exception can be more damaging than a longer uncompiled requirement. Its economy should be evaluated against downstream outcomes.

## Applicability can be uncertain

Let \(a_t\) denote a candidate operation and \(x_t\) the relevant observed state. For a commitment \(k\), we can describe applicability as:

\[
\alpha(k,a_t,x_t)\in
\{\text{applies},\text{does not apply},\text{unresolved}\}.
\]

For an applicable represented condition, a check can return:

\[
v_k(a_t,x_t,e_t)\in
\{\text{satisfied},\text{violated},\text{undetermined}\},
\]

where \(e_t\) is the evidence available to that check.

These labels describe distinct questions. A condition might not apply to a simulation branch. It might apply to the real output but remain undetermined because an effect cannot be observed. Two applicable commitments might also conflict; that is a further problem concerning their combination.

The labels do not provide guarantees by themselves. An applicability model can be wrong. A precise checker can receive stale inputs. A condition can faithfully encode a mistaken interpretation. The architecture needs coverage and uncertainty, not merely more confident labels.

An unresolved case should lead to a suitable response: narrow the action, obtain evidence, use an established alternative, preserve the candidate for exploration, or seek a consequential decision. It need not freeze all independent work.

For mechanically enforceable boundaries, the responsible executor can enforce a represented condition. For uncertain semantic obligations, models and domain experts can supply assessments. The disposition follows the actual governing policy; we should not prescribe one threshold or one mandatory escalation rule for all worlds.

## Enforcement has to reach the effects

A model judge stating that a candidate complies is evidence from a fallible assessment. It does not prevent a different candidate from being executed.

A dependable check needs a connection to the actual target, relevant state and realized operation. If the state changes between assessment and enactment, the previous result may cease to apply. The appropriate response can be version binding, rechecking or another domain-specific continuity mechanism.

The same problem appears in distributed resources. Several workers can each remain below their local budget while exceeding a shared limit. Shared-resource management needs an account of actual allocation and consumption; a sentence repeated in every prompt cannot supply that account.

Some effects are delayed or emerge through composition. Several locally acceptable operations can jointly violate an obligation. Their local explanations may all look reasonable. Monitoring accumulated effects or assessing the combined plan can be necessary.

The assurance claim should distinguish prevention, retrospective detection and recovery. A mechanism may prevent a represented violation by mediating an operation, detect a problem after it occurs, or help repair its consequences. Delayed monitoring alone cannot support a prevention claim. Some consequences cannot be fully reversed.

A guarantee is consequently conditional on represented semantics, current observations and mediation of the relevant effects. It does not extend to unmodeled consequences or paths that the enforcement mechanism never observes.

This distinction should improve autonomy. Routine operations can proceed through dependable local machinery. Human attention can remain focused on unresolved objectives, meaning and consequential boundaries rather than repeated authorization of settled work.

## A worked case: exactness under an optimization campaign

Consider a hypothetical system tasked with reducing retrieval cost while preserving exact ranking, including tie behavior, and source attribution.

An optimization expert proposes semantic clustering to avoid repeated work. An evaluation expert tests common queries and finds similar-looking answers. A memory summary compresses the requirement to “maintain retrieval quality.” Rare tie cases and the word “exact” disappear from the immediate context.

The candidate explanation sounds compliant. Yet its output changes tie ordering and omits a source distinction. The failure is distributed across attention, interpretation, evidence and realized behavior.

The corrective architecture needs more than another exhortation to remember requirements.

The authoritative commitment should retain exactness and scope. The context view should bring relevant clauses to this optimization decision, including conditions that make ordinary quality metrics insufficient. Evaluation should compare the actual candidate at the required level. Execution should use the assessed candidate rather than a subsequently changed arrangement.

The clustering idea can remain useful. It may be investigated as another mode, or as an internal technique that ultimately preserves the required output. A proposed relaxation should be distinguishable from accepted product behavior.

If the user deliberately authorizes an approximate mode, that creates a legitimate revision with a defined scope. The old exact commitment may still govern other callers. “Latest preference wins everywhere” would mishandle both.

This case also shows why checks need evidence coverage. A finite set of exact comparisons demonstrates equality on those cases. It does not automatically prove equality for every query. A broader equivalence claim needs an appropriate argument and assumptions.

The scenario is illustrative. It reports no defect or current acceptance condition in a particular repository.

## A second case: correct calculations answering a changed question

Consider two scientific-analysis experts forming a persistent composite. One prepares data; the other estimates a quantity and explains the result. Their task specifies a target population and the quantity to estimate. These conditions matter even when the arithmetic is flawless.

The preparation expert develops a filter that removes difficult cases. The estimation expert retains the old description of the target population in a compressed summary. Identifiers resolve, the code runs and local calculations are correct. Yet the composite now estimates a quantity for a selected population while describing it as the original one.

An exact identifier checker cannot detect this meaning change. Useful continuity requires connecting the changed filter to the population definition, retrieving the relevant conditions, and assessing what the result can support. The system may rerun the affected analysis, report the restricted population, or propose a revised research question. Unaffected analysis can continue.

The filter is not inherently illegitimate: it could be the right response to a measurement problem. The failure is losing the relationship between the question, selection assumptions and claim. The improved capability is diagnosing that dependency and developing a suitable alternative, rather than merely adding an approval request.

This hypothetical case illustrates why a developmental architecture needs revisable semantic interpretations alongside precise checks. Preserving the words of a commitment does not preserve its meaning when the underlying representation changes.

## Creativity can challenge assumptions while commitments persist

A novel candidate often departs from the current schema. Treating unfamiliarity as a violation would undermine the user's developmental ambition.

A world should be able to entertain changed objectives, relaxed assumptions or alternative contracts within clearly marked hypothetical work. It can ask what becomes possible under a different condition.

The status of that work must survive later handoffs. A branch's assumption is not an adopted revision. A promising simulated outcome does not establish that the real constraint was removed. A speculative world can reveal a useful question without contaminating accepted task state.

Exploratory branches can vary proposed-world assumptions. Their actual resource use, access and state changes remain subject to applicable commitments. A hypothetical outcome and the real operations used to investigate it have different scopes.

Constraint feedback can also guide invention. An exactness requirement may motivate a new representation that makes exact evaluation cheaper. Resource limits may motivate better abstractions or morphology. Control does not have to act solely as censorship at the end.

Some requirements are themselves provisional and revisable within delegated scope. A learned procedure can change its own internal organization. The architecture should preserve that freedom rather than turn every convention into a permanent rule.

The important distinction is which question is being explored, which change has been adopted, and which effect is permitted. A constraint system that cannot represent legitimate revision would become an obstacle to development.

## Consistency has several meanings

Logical consistency concerns incompatible propositions under specified assumptions. Epistemic consistency concerns what claims and evidence can be maintained together. Instruction consistency concerns applicable obligations. Operational consistency concerns state and effects. Temporal consistency concerns change across conditions and versions.

These can differ. Two experts can disagree without either violating a commitment. A conclusion can change with new evidence. A behavior can satisfy a rule on one input and fail on another. A history can correctly record that different obligations governed different periods.

Consistency should therefore be scoped. “This system must never contradict itself” is too vague to be a useful universal target. It can encourage bland statements, suppress correction or confuse uncertainty with failure.

For a long-running task, it is more useful to identify specific conflicts, unsupported dependencies, obsolete assumptions and unauthorized changes. Conclusions affected by a correction can be reconsidered without pretending every related fact is invalid.

Dependency tracking can help locate affected material, but the dependency model is incomplete. A relation labeled “supports” may conceal conceptual, empirical and causal differences. Automatic propagation of invalidation through that label would overstate what is known.

The architecture should make revision intelligible and recoverable. It should not equate consistency with preserving every prior utterance.

## Distributed worlds need compatible commitments

A society of experts cannot rely on one model holding the entire context. Each world can maintain local commitments, interpretations and current work. Relationships carry the parts needed for cooperation.

A handoff needs the intended result, relevant conditions, dependencies, scope, current evidence and applicable powers. A shared workspace can coordinate a task while participants retain different interpretations.

Some constraints are local; some govern a shared capability or resource. The responsible world or joint arrangement needs to check the effects it controls. A shared substrate can support common identity, resources and lifecycle without evaluating every domain claim.

Fusion and fission create revision events for this machinery. An obligation may persist after its original participant becomes internal to a composite. A split needs to allocate responsibility and preserve the interpretation relevant to each successor.

Reorganization also needs semantic continuity: preserve or explicitly reassess the obligation's meaning under the successor representation, including shared responsibility and combined effects. Changed vocabulary or participant dissolution does not itself discharge an obligation. Splitting a participant does not automatically duplicate its allowance from a shared budget. Unresolved transfer should limit the affected consequential transitions while independent work continues.

Shared commitment does not require shared belief. Experts can agree to investigate a question while disagreeing about its answer. Preserving those distinctions supports useful diversity.

Cooperation also introduces shared failure modes. Several worlds may inherit the same mistaken interpretation, model bias or compressed exception. Agreement among them is insufficient evidence that the commitment has been interpreted correctly.

The degree of coordination remains a design choice. Vector 3 can assess which specializations need independent trajectories and which benefit from common working state.

## The control machinery should learn

An architecture with fixed rules and an unchanging relevance policy would not fulfill the broader ambition. Context selection, interpretation support and evaluation procedures should improve through attributable experience.

Useful learning signals include missed exceptions, unnecessary retrieval, false blocking, violations, successful clarification, recovery effort and later consequences. User corrections can be informative without making the user the only available feedback source.

The signals should remain distinguishable. More retrieved text is not necessarily better context. Fewer conflicts reported can mean improved behavior or a checker learning to overlook them. Lower error can mean avoiding difficult tasks.

A learned policy could discover that a certain proposed action warrants an exception search, that one expert's formulation needs a particular translation, or that repeated uncertainty is better resolved by a short experiment.

The governing target and the measurement should remain distinct. A policy can propose a better evaluation method; it should not silently redefine success to validate its own choices. Routine measurement repair can still occur under established delegation.

Learned salience should be tested against what was omitted and what the resulting action did. A trained judge should be assessed on difficult, ambiguous and revised cases, not merely agreement with its own generated labels.

We can learn control policies while retaining precise effect checks where they are available. The system need not choose between static enforcement and entirely unconstrained learning.

## Architecture choices worth comparing

| Arrangement | Potential advantage | Main limitation |
|---|---|---|
| One large context and capable model | Simple coordination; broad material is immediately available | Supplied context may be unused, costly or stale |
| Selected context with explicit commitments and local checks | Bounded attention and dependable checks for represented effects | Selection and compilation can omit decisive meaning |
| Distributed world-level interpretation and enforcement | Domain knowledge remains local; adaptation can proceed independently | Shared constraints and semantic drift require coordination |
| Hybrid shared effects machinery with local cognitive policies | Combines common resource/lifecycle control with expressive worlds | Shared assumptions and duplicated interpretation can still fail |

These are competing allocations, not four exclusive products. A mixed arrangement can be appropriate. Greater architectural complexity should follow demonstrated needs.

My current bet favors explicit scoped commitments, decision-conditioned context and checks near consequential effects, with domain interpretation local. It preserves a small shared foundation and permits learning above it.

That bet needs comparison with a simpler capable-model baseline. We should not assume the additional machinery helps merely because each part sounds sensible.

## Bounded empirical footing

Lost in the Middle reports position-sensitive use of evidence in multi-document question answering and key-value retrieval by the models it tested. It supports distinguishing available context from effective use. It is historical evidence, not a measurement of the models or architecture we would use now. The primary abstract was inspected. [Liu et al., TACL 2024](https://aclanthology.org/2024.tacl-1.9/)

MultiChallenge studies difficult multi-turn behavior and uses instance-level rubrics for model judging with reported agreement against human raters. It supports separating long-history behavior into assessable problems and evaluating the judge itself. Its published model rankings describe that study, not current frontier performance or typical task failure rates. The primary abstract was inspected in this pass; detailed judge claims are not independently reproduced here. [Deshpande et al., ACL 2025](https://aclanthology.org/2025.findings-acl.958/)

These sources motivate investigation. They do not prove that a particular constraint architecture solves long-horizon cognition. Neither longer context nor a collection of gates establishes complete semantic consistency.

## What a useful comparison would test

A representative evaluation should contain ordinary work and cases where rare conditions change the answer. Include legitimate revisions, stale summaries, negative requirements, ambiguous scope, shared resources and hypotheses that must remain hypothetical.

Measure several outcomes separately: task success, consequential omissions, commitment violations, false blocks, unnecessary human intervention, recovery time and complete cost.

The hardest cases should include:

- A decisive requirement stored but omitted from context.
- A requirement supplied but misinterpreted.
- A valid check performed on stale state or another candidate.
- Several locally acceptable actions whose combined effect violates a shared obligation.
- A legitimate revision mistakenly blocked.
- A familiar but wrong belief preserved as though it were binding.
- An exploratory assumption inherited as an accepted instruction.
- A rare exception erased through repeated compression.
- A semantic obligation whose applicability cannot yet be established.

Controlled cases can test mechanisms. They should be complemented by realistic workflows, because success on planted conflicts does not establish that the system detects unanticipated ones.

Ablations need meaningful comparisons. Removing a component without restoring required context can create an incoherent system. Compare capable alternatives and report what the decomposition actually changed.

No experiment is started by this proposal. These cases define the questions that a focused architect or research team could discriminate.

## What I would carry into the next design stage

I propose five architectural principles for later consideration.

1. **Attention and commitment continuity have distinct objectives.** Selective omission does not cancel an obligation; retention does not make a statement binding.
2. **Commitments retain source, scope, status and legitimate revision.** Beliefs and schema preferences remain revisable through evidence.
3. **Working context can expand and expose consequential uncertainty.** Selection should be evaluated against outcomes and omitted exceptions.
4. **Checks and enforcement state their coverage and reach the relevant effects.** Semantic judgments remain fallible; passing labels do not substitute for realized behavior.
5. **The machinery is distributed and adaptable.** Local worlds keep domain meaning, shared obligations receive suitable coordination, and routine work proceeds under standing delegation.

I would leave open the exact commitment representation, compiler, attention policy, anatomical analogy, model allocation and topology. The meaningful early decision is which responsibilities need explicit continuity and which mechanisms can remain local and provisional.

The resulting vision is a world that can explore unusual possibilities, retain what it has undertaken, learn when it lacks the right context and revise its beliefs without losing operational continuity.

Vector 3 can then ask when a specialist needs its own persistent history, responsibilities and learning trajectory, and how such experts cooperate without erasing their differences.

## Review scope

A separate agent reviewed this essay for conceptual coherence, fidelity to the developmental ambition, and overclaims about enforcement, uncertainty and biological grounding. The review prompted explicit limits on commitment discovery, a distinction between prevention and detection, continuity of meaning through reorganization, and the real effects of hypothetical exploration. It also prompted the second illustrative case. This is documentary review; no mechanism was implemented or experimentally qualified, and the recommendations remain proposals.
