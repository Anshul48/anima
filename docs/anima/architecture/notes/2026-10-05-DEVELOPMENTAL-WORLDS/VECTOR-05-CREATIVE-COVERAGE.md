# Vector 5 — Creative coverage under compression

> Public curation note: links to records excluded from this public release were converted to plaintext historical references; the original record identities are preserved inline.

Architecture discussion, 2026-10-06. This is the full fifth-vector treatment in the current round. It builds on [developmental change](VECTOR-01-DEVELOPMENTAL-CHANGE.md), [attention and commitments](VECTOR-02-ATTENTION-AND-COMMITMENTS.md), [expert individuality](VECTOR-03-EXPERT-INDIVIDUALITY.md) and [physical construction](VECTOR-04-PHYSICAL-CONSTRUCTION.md). Recommendations remain proposals while the user reads the round.

**My current bet:** make compression a revisable guide to attention, while preserving several ways for unfamiliar evidence and combinations to change the work. The stronger developmental target is a system that learns where its representations and search methods are inadequate, then changes them through investigation.

A faithful source store, an efficient summary hierarchy and occasional random exploration are useful ingredients. The larger ambition concerns what the system can construct from them: new distinctions, explanatory variables, translations, experiments, procedures and forms of cooperation.

The user's concern is well placed. A signpost can describe a region accurately enough for routine navigation while concealing the unusual member that matters for a later insight. Two such members can be individually unpromising and jointly useful. A society of experts can preserve different views, but it can also repeatedly exchange summaries that remove exactly those differences.

Creative coverage therefore concerns opportunities to notice, construct and assess useful possibilities under finite resources. It is not a promise that every possible breakthrough remains discoverable.

## What would count as a useful creative result?

We should distinguish a retrieved clue, a new association, a proposed explanation, an effective intervention and a reusable capability.

Two distant passages appearing together provide an opportunity. A model describing a connection constructs a candidate. That candidate may introduce a meaningful variable, change the formulation or suggest a discriminating experiment. Its usefulness depends on what happens next.

A new procedure that works under assessed conditions is a stronger result. Retaining it so that another task benefits adds another claim. A scientific breakthrough also needs domain significance and appropriate external evidence; unfamiliar wording or a high novelty score cannot supply that.

Novelty has several reference points. Something may be new to this run, this expert, the wider programme or the scientific field. Those distinctions should survive the report. A capability rediscovered by the system can still be useful without being a new human discovery.

This matters for the user's larger canvas. The construction environment may discover a better calibration method. A research world may uncover a neglected relationship. A software world may invent an abstraction that makes a previously difficult class of tasks tractable. Each needs a different account of validity and value.

The common architectural question is whether current organization can be challenged and improved through those encounters.

## The losses occur at different places

Source preservation is only the first part of the problem.

| Stage | How an opportunity can be lost | What would address that particular loss |
|---|---|---|
| Preservation | The observation or its conditions were never captured, or were discarded | A declared capture and retention contract |
| Access | The useful item is retained, but current routes never reach it | Alternative routes, source access and deliberate investigation |
| Activation | The item is retrieved, then excluded from the context that influences the decision | Selection that permits consequential exceptions to affect the work |
| Representation | The item is visible, but its important distinction cannot be expressed in the working model | Revisable representations and inspection of what the mapping omits |
| Construction | Relevant ingredients are present, but no useful combination or operation is formed | Analogy, decomposition, candidate transformations and informative trials |
| Assessment | A useful candidate is rejected by an inadequate test, or an exciting false candidate is rewarded | Domain evaluation with explicit coverage and independent evidence where needed |
| Retention and reuse | A success is compressed into a recipe that loses its applicability conditions | Conditional capability records and assessed later reuse |

These stages can interact and repeat. The table is a diagnostic decomposition, not a compulsory execution sequence or seven services.

A larger archive cannot repair a biased evaluator. Better retrieval cannot make a missing variable expressible. More candidate generation cannot make a poor experiment discriminate its explanations. Several agreeing experts cannot restore a condition that all their summaries omit.

Conversely, the same modest change can help at several stages. A sequence-sensitive representation might improve retrieval, interpretation and control. A relationship that learns to exchange failed predictions could create better routes and better experiments.

The aim is to locate the limiting mechanism before adding more machinery.

## Compression helps, and its sufficiency is conditional

A useful abstraction can expose a relationship that detail obscures. Generalizing several examples into a shared operation can make an unfamiliar task easier to formulate. Compression is part of constructive intelligence.

The difficulty is treating a successful compression for yesterday's tasks as an adequate description for every future one.

Let \(C\) be a compression of an available history. Suppose two histories satisfy

\[
C(H_1)=C(H_2),
\]

but a later question \(q\) requires different answers from them. Any decision procedure given only that common compression and \(q\) receives the same information in both cases. It cannot reliably make the required distinction unless it acquires something else.

This elementary example identifies a limit of the representation. It does not prove that the system needs to load entire histories, that all details deserve preservation, or that one particular residual scheme fixes the problem.

The additional information might come from a source passage, a compact retained condition, another representation, a measurement or a new experiment. Some distinctions cannot be recovered from records that were never captured.

A summary can therefore remain useful while its adequacy remains revisable. It can propose where to look and what to expect. Relevant evidence can challenge those proposals.

RAPTOR provides a concrete retrieval precedent. Its recursive summaries coexist with source-level nodes. The paper compares hierarchical traversal with retrieval across all levels; the latter performs better in its reported small querying-method comparison. The comparison supports considering access beyond parent-by-parent routing, rather than treating summary quality and routing structure as the same question. It does not establish creative discovery or a trillion-token operating envelope. I inspected the methods, querying comparison and selected scalability passages. [Sarthi et al., ICLR 2024](https://proceedings.iclr.cc/paper_files/paper/2024/file/8a2acd174940dbca361a6398a4f9df91-Paper-Conference.pdf)

The architectural inference is modest: a useful hierarchy need not be the only way material becomes available. Its additional routes still need a cost and capability comparison.

## Useful combinations can evade marginal usefulness scores

The user asks what happens when outliers from disparate holons are needed together. This is more difficult than keeping one exceptional fact.

A small mathematical illustration makes the distinction clear. Let \(X_1\) and \(X_2\) be independent fair bits and define

\[
Y=X_1\oplus X_2.
\]

Knowing either bit alone leaves \(Y\) equally likely to be zero or one. Knowing both determines it.

This is a constructed information example, not a model of creative cognition. Its point is that individual predictive value need not reveal joint value.

The same kind of failure can occur in a search policy. An unusual observation from one region and an obscure method from another may each appear irrelevant under the current formulation. Their combination can suggest a new formulation that makes both relevant.

That does not justify searching every pair. With \(n\) items, even pair enumeration grows quadratically; richer combinations grow faster. Preserving all source material does not make that search affordable.

Useful abstractions can reduce the search. A task may exhibit unexplained dependence on order, scale, delay or a boundary condition. Those features can generate hypotheses about mechanisms and methods across domain labels. A learned relationship can also make previously expensive combinations cheap to construct again.

The challenge is choosing promising interactions without knowing their eventual value. Partial failures, contrasting cases, alternative representations and bounded exploratory sampling are candidate signals. None guarantees that the decisive pair will be selected.

This is one reason to preserve prospective learning as an objective alongside immediate completion. An intermediate representation can look unhelpful now while enabling a useful later operation. The programme needs a deliberate allowance for investigating such possibilities, with retained outcomes and actual costs.

## Shared schemas should support composition and reconsideration

The user's generalized abstract schema, specific schema and delta remains a promising way to make common structure cheap.

An abstract schema can describe broad relationships. A domain schema can express local entities and mechanisms. A delta can retain the differences of a particular instance.

That arrangement should distinguish the original material from what the representation currently captures. A compact delta is not automatically complete; its adequacy depends on the schema, the interpretation process and the questions asked.

Some source distinctions will initially remain unmapped. Others may be represented ambiguously. That can be useful evidence about the vocabulary's limits rather than a reason to force the source into the nearest existing category.

For example, a generic relation called “supports” can obscure whether a passage provides an observation, a causal mechanism, a formal derivation or merely a conceptual analogy. A richer working representation might make the relevant distinction. It can still leave unclear cases open.

Multiple views can coexist. One might emphasize mechanisms, another operating conditions, another the sequence of interventions, and another the dependency structure of a procedure. They can share source identity without requiring one permanent interpretation.

The user's observation about different authors also matters. Variations in language can expose different decompositions and assumptions. Some variation merely increases parsing effort. The architecture should preserve access to the source while allowing convenient standardized views; it need not homogenize every internal account.

Changing prompt wording or adding noise is one possible source of variation. Distinct methods and experience can provide deeper differences. Their contribution should be assessed through what the system notices and constructs.

A useful common schema lowers composition costs. An alternative view earns its place when it preserves a distinction or enables an operation the common view repeatedly loses. Repeated equivalence can justify consolidation.

## Several routes can reach the same material

I would investigate a small portfolio of routes, each connected to a failure it could address.

| Candidate route | What it may expose | Cost or limitation |
|---|---|---|
| Summary and representative navigation | Broad structure and common cases | Can suppress details poorly reflected in the representative |
| Direct lexical or dense source retrieval | Specific passages outside the chosen hierarchy | Still depends on query formulation, indexing and ranking |
| Conditions, exceptions and residuals | Applicability limits and departures from a common model | Identifying and maintaining them requires interpretation |
| Alternative groupings and views | Relations hidden by the dominant taxonomy | Additional construction, storage and reconciliation |
| Structural analogy | Similar mechanisms beneath different vocabulary | A plausible mapping may fail on a crucial condition |
| Cross-expert investigation | Different methods, histories and explanations | Consultation and translation can become expensive or correlated |
| Bounded exploratory sampling | Material no current relevance route would choose | Most sampled material may be unhelpful; coverage remains partial |

These are candidate mechanisms, not seven mandatory components.

The routes should differ in what they can reach. Running several embedding searches with slightly altered wording can still reproduce the same omission. An exception index built by the same interpretation process can inherit the same blind spot.

A route also needs to affect the next decision. Reporting that a rare passage appeared somewhere in a long result list does not establish that the system used it.

Source boundaries matter. A passage may be a quoted proposal, a failed trial or a later correction. A bridge should preserve the status and conditions of its ingredients. Citation fidelity establishes where a statement came from; it does not establish that the statement is true.

An uncertain connection can be retained as a candidate association. Its label should distinguish analogy, possible dependence, observed co-occurrence and assessed mechanism. A speculative bridge must not become established support merely because repeated retrieval makes it familiar.

## Analogy needs more than distance

Embedding similarity can propose related material. Distance can help suggest unfamiliar material. Neither quantity directly establishes an analogy's usefulness.

A helpful analogy requires a mapping: which roles correspond, which relations are preserved, what operation transfers and where the comparison breaks.

The mapping can be deliberately partial. A control mechanism and a software workflow may both contain delayed feedback without sharing their physical dynamics. The transferable idea could be an experiment or a decomposition, rather than a copied numerical controller.

Holyoak and Koh's 1987 author abstract distinguishes finding an analogue from using it. In their two experiments, surface and structural features influenced spontaneous selection, while structural features mattered more for successful use once relevance was pointed out. The available publisher abstract supports that limited distinction; the full PDFs were inaccessible through the retrieval tool. This is not a measurement of present-day models. [Holyoak and Koh, Memory & Cognition 1987](https://link.springer.com/article/10.3758/BF03197035)

My proposed computational interpretation is to search partly by problem structure: a goal, constraint, sequence, dependency or unexplained effect. The model can then construct an explicit mapping and propose a check.

For instance, “a change in operation order alters the outcome” may be a better cross-domain cue than the name of the device. Even that cue can be misleading. Many unrelated mechanisms produce order effects.

The useful product is a candidate explanation or action whose assumptions can be inspected. A distant document pair is an input to that construction, not the construction itself.

## A system can be wrong without noticing an error

Prediction error is useful when an observation reaches a prediction that can be compared with it.

It cannot trigger repair for every omission. A hidden exception may never be retrieved, a relevant operating regime may never be tested, or an evaluator may average away the failure. The system can appear coherent throughout.

This rules out a design that explores only after an obvious error. Some investigation needs to challenge the coverage of the current account before failure becomes visible.

Possible triggers include a changed requirement, an unresolved applicability condition, an explanation with little supporting variation, a repeatedly reused but narrowly tested method, or a discrepancy discovered by a different view. Periodic bounded sampling can provide another route.

The investigation might examine a neglected condition, a contrasting source or an alternative formulation. It should state what it is trying to discriminate. Mere disagreement is not proof that the dominant view is wrong.

A coverage challenge should sometimes originate outside the current interpretation: a changed operating condition, independently inspected source material, a different measurement or a view that preserves other distinctions. It can also vary which cases the assessment examines when an aggregate score conceals a regime-specific failure. Several restatements generated from the same summary can repeat its omission. Such investigation can remain targeted; it need not reconstruct the entire archive or pretend that every alternative view is independent evidence.

Novelty and surprise should also differ. An expected failure can be novel in its particulars. An apparently familiar result can be surprising under a specific model. Neither alone tells the system which change would help.

These routes have maintenance and false-alarm costs. A discovery policy that continually opens weak possibilities can consume the work it was meant to accelerate.

The useful question is whether a bounded allowance improves consequential decisions and later capability, including cases where routine predictions would otherwise remain satisfied.

## A hypothetical constructive episode

Consider a fictional compliant component studied by materials and control experts. This extends the examples in the earlier vectors; it is not an empirical claim about a particular actuator.

Most trials fit a simple deformation model. One uncertain archived observation reports a different response after a particular loading sequence. Materials summaries describe variability. Control summaries retain average performance. A later task requires accuracy after sustained loading.

A routine route retrieves the normal model and tunes the controller. It may even retrieve the unusual observation, then exclude it as an isolated outlier. An evaluator dominated by ordinary trials can reward that choice.

The source record can remain perfectly intact throughout this failure.

A more promising path begins with the changed requirement. The current model has little evidence for sustained loading, so the system investigates conditions rather than only the device label. It recovers the unusual sequence and its uncertainty.

An occasional comparison of raw trial sequences with the fitted model's declared coverage could initiate the same inquiry before a new requirement or overt failure. That is a bounded coverage probe, with no guarantee that its sample reaches the decisive case.

The materials expert proposes a history-dependent physical state. A sensing expert suggests a competing explanation involving measurement drift. A control expert asks whether the observation process depends on the actions selected by the controller.

These are candidate explanations, not corroborating votes. Their consequences differ. The participants construct a diagnostic sequence that would separate some of them, identify the measurement assumptions and specify the observations needed.

A model or simulation can help plan that sequence. Actual physical evidence is needed for the relevant physical conclusion. The [physical-construction discussion](VECTOR-04-PHYSICAL-CONSTRUCTION.md) supplies that distinction.

Suppose subsequent evidence supports one explanation within stated conditions. The useful change might include a new state variable, a revised measurement procedure and a controller that selects informative actions. The result is more than an association between two records.

The experts' relationship could retain the joint model and diagnostic procedure. Both participants might revise how they index loading history and export capabilities. Repeated use could justify a composite with custody of the joint work. A later split would need to preserve its relevant conditions.

If the investigation rejects all proposed explanations, it can still identify a missing measurement or an inadequate task model. That finding needs its own status; an unsuccessful hypothesis should not be reported as a capability gain.

The developmental possibility is that the encounter changes how future problems are noticed, represented and investigated. A capable integrated TRACE could accomplish this too. Separate expert worlds earn a stronger claim only through a suitable comparison.

## Exploration should preserve alternatives that matter

An ordinary search can repeatedly choose the candidate with the best current score. That is useful when the score reliably reflects the target and intermediate progress.

It can fail when a promising intermediate looks worse, when several paths receive equivalent scores despite different future possibilities, or when the evaluator favors the familiar formulation.

The [search-evidence note](VECTOR-05-SEARCH-EVIDENCE.md) examines primary examples of novelty and quality-diversity search. Their architectural relevance is to maintaining more than one promising trajectory. Their specific results do not qualify a general creative engine.

Conti and colleagues found novelty-based variants could help in deceptive settings and hurt performance on some other tasks. Their Atari behavioral descriptors used game RAM. This supports task and descriptor dependence, rather than a universal advantage for novelty. [Conti et al., NeurIPS 2018](https://papers.nips.cc/paper_files/paper/2018/file/b1301141feffabac455e1f90a7de2054-Paper.pdf)

Behavioral diversity, source diversity, representational diversity and textual variation should remain distinct. Two differently worded suggestions can perform the same operation. Two similar descriptions can rely on different mechanisms.

A candidate archive can retain several methods with different applicability or consequences. An occupancy map is meaningful only relative to the descriptors used to build it. Those descriptors can conceal unanticipated distinctions just as a topic hierarchy can.

A stronger substrate would allow the search representation itself to change. A newly important variable might require regrouping candidates, constructing a new operator or revising how experts cooperate.

That creates migration and comparison costs. Earlier scores and classifications need their original meanings preserved. Changing descriptors can reveal opportunities without establishing that behavior improved.

The immediate practical hypothesis is modest: preserve useful alternatives under meaningful differences, then assess whether those alternatives become valuable on changed demands. The ambitious hypothesis is that experience improves the system's ability to define and navigate such differences.

## Biological inspiration should identify functions and questions

The user is interested in memory-grounded recombination, replay and changing cooperation between generative and evaluative processes. Those are worth investigating without requiring the pasted universal anatomical cascade.

The [neuroscience-evidence note](VECTOR-05-NEUROSCIENCE-EVIDENCE.md) examines interventions, replay and explicitly separated creative task demands. It distinguishes what the studies observed from engineering proposals and from claims about all creativity.

Liu and colleagues observed reactivation of new stimuli in inferred sequence order after participants had learned the relevant structural rule. This supports reorganization beyond verbatim experience within that task; the rule was supplied, rather than autonomously discovered. [Liu et al., Cell 2019](https://discovery.ucl.ac.uk/id/eprint/10078375/1/1-s2.0-S0092867419306403-main.pdf)

Bartoli and colleagues report that stimulation of selected default-network sites reduced an alternate-use originality proxy based on semantic distance. Clinically constrained sampling and control conditions limit inference, and that proxy does not establish usefulness or scientific novelty. [Bartoli et al., Brain 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11449134/)

One proposed functional loop is to recover fragments, construct a possible arrangement, replay a short consequence, seek contrasting evidence and revise the candidate or representation. The components can interact repeatedly rather than waiting for one fixed generation phase to finish.

Replay can make an assumed transition explicit. It does not make that transition true. A model can simulate several internally consistent trajectories that all omit the same physical constraint.

A process inspired by unconstrained association can also remain bounded by an exploratory budget and the effects it is permitted to produce. Different working modes need not correspond to separate brain regions or permanent agents.

The relevant comparison includes ordinary generation, explicit analogy, counterexample search and short simulated trajectories with the same resources. Anatomical resemblance earns no extra credit if a simpler method provides the same capability.

The biological leads help frame mechanisms. They neither select runtime anatomy nor establish that the proposed system will generate breakthroughs.

## Assess unfamiliar candidates without rewarding unfamiliarity

An evaluator can mistake low familiarity for invalidity. A novelty policy can make the opposite mistake and reward an unsupported proposal for being different.

Both problems require distinguishing the objective from the current method of measuring it.

A candidate that changes formulation should explain how it still addresses the governing task. If the present test omits a relevant condition, the investigation can propose additional measurements or cases. That does not silently relax the objective.

Some conditions can be checked precisely. Others need semantic or empirical judgment. A test that certifies syntax, a model that predicts behavior and an experiment that observes effects support different claims.

For an uncertain proposal, the most useful next action may be a cheap discriminating check. It can reject a wrong mapping or identify an assumption worth measuring before substantial work is invested.

An evaluator also needs appropriate negative cases. A system rewarded only on tasks where a rare clue is essential will learn to overuse rare clues. A system judged mainly on routine cases can learn to ignore them.

Selection across many candidates can exploit evaluator error. Better reported maxima do not establish better underlying results. Preserve the candidate pool and evaluation procedure sufficiently to compare what was selected with what later held up.

The [attention and commitments discussion](VECTOR-02-ATTENTION-AND-COMMITMENTS.md) distinguishes revisable beliefs and schema preferences from obligations. Creative exploration can challenge a belief without acquiring authority to change an accepted constraint.

Routine investigation proceeds under standing delegation. Consequential objective or authority changes remain decisions for the responsible owner. This does not require a human approval ceremony for each candidate.

## Contested hot memory is compatible with discovery

The user's preference remains that active graph space is costly and contested. Retired bodies should not continue participating in ordinary cognitive traversal merely because someone might later want their history.

There are several different cases.

An inactive but still applicable method may reside in warm knowledge and return when a task warrants it. A retired interpretation is historical material with a different status. A live operation may need an active applicability condition because current use depends on it.

Those conditions do not require permanent active tombstones for every retired idea.

Archived records, source indexes and historical views can support deliberate recovery outside the default hot graph. A temporary investigation can pay for retrieval and reconstruction within its own budget.

Historical recovery must preserve time and status. A false old interpretation can still help explain an earlier failure or inspire a new hypothesis. It must not return as current established knowledge merely because it was retrieved.

There is no universal reconstruction promise. The existing [memory-tiers discussion](../../../../../components/substrate/docs/MEMORY-TIERS-AND-GRAPH-RETIREMENT.md) records that TL alone does not promise complete historical recovery after reclamation. A cold archive needs its own actual capture frontier, retention owner and evidence of availability.

The hot representation can contain task state, provisional associations, working models and procedures. It should not be confused with every source or every historical assertion. Warm and cold resources can themselves contain several representations and indexes.

When repeated recovery becomes valuable, an eligible method can justify a maintained representation or procedure. That avoids paying the entire reconstruction cost every time. Keeping historical access costly means counting its cost, not deliberately making useful retrieval inefficient.

Retaining a source transcript does not preserve every capability acquired from it. Model parameters, jointly learned state, executable artifacts, tools or calibration may also be needed to reuse a method. Records can support reconstruction without making it complete or cheap. That distinction matters when a successful creative episode is exported, consolidated or inherited.

## Decide what exploration is for, and account for it

Exploration can improve the current answer, learn a reusable method or investigate a longer-term opportunity. Those purposes have different horizons.

A task-focused policy may favor the next discriminating check. A continuing expert may invest in a representation that helps its future task family. A programme may reserve resources for unfamiliar methods whose near-term value is unclear.

One immediate-success score is unlikely to express all those purposes adequately. The budget and intended contribution should be visible enough to assess what the investigation bought.

The exploratory policy and its budget can be justified and assessed across a portfolio of investigations. Individual clues can enter that portfolio before their usefulness is known. Later results, including unsuccessful searches, help judge whether the policy deserves continued resources. This preserves room for uncertain combinations while preventing every unproductive item from claiming an unlimited future value.

I would leave the exact allocation mechanism open. It might respond to task difficulty, uncertainty, lack of tested coverage, repeated failure or evidence of reuse. A fixed novelty percentage is not selected here.

Resource accounting includes acquisition, indexing, source access, inference, experiments, translation, maintenance, reconstruction and human attention. Extra sampling should not disappear inside the claim that a society reasons better.

The user's attention is a particularly scarce resource. Systems can investigate routine branch points independently, prepare useful contrasts and surface consequential decisions with evidence. The aim is to make the user's direction more effective across many collaborators.

A long list of imaginative suggestions can increase attention cost while producing little progress. A developed candidate, its discriminating evidence and the work it enables is a better unit of contribution.

Bounded background investigation can proceed alongside current delivery. Its outputs should inform later choices rather than turn every speculative mechanism into a prerequisite for useful work.

## The strongest simpler arrangement must get a fair chance

The comparator should be a capable hierarchical TRACE with hybrid retrieval, several representatives, source access, query reformulation, persistent methods and a strong model.

It should be permitted to seek counterexamples and revise working representations. Comparing a sophisticated society against one centroid route would largely test whether the baseline was deprived of useful mechanisms.

A second comparator can add several independent generation or investigation attempts without persistent expert worlds. That helps separate gains from extra sampling from gains due to developing trajectories.

A third arrangement can add different expert histories, alternative views and learned relationships. Its lifetime cost includes how those differences were acquired and maintained.

A fourth can investigate structural development: changing representations, operations or custody so that repeated joint work becomes a reusable capability. This is a stronger claim than consulting more experts.

These arrangements can overlap. The aim is to locate which mechanism helps under which conditions, not declare one permanent topology the winner.

The novelty claim should also be calibrated. Hybrid retrieval, analogy, replay, novelty search and diverse candidate archives have substantial prior art. Combining their names is not a breakthrough.

The frontier proposed here is whether an organization can repeatedly identify inadequacies in its own cognitive machinery, develop useful alternatives and retain their benefit across changed tasks. A successful retrieval enhancement is valuable evidence, but it establishes a narrower claim.

## What a discriminating capability comparison would examine

A useful comparison needs several kinds of demand.

Some tasks should require an explicit exception. Others should require a cross-region combination without naming the relevant ingredients. Some should reward a new representation or operation. Routine tasks and misleading unusual items are needed to measure the cost of overexploration.

Controlled cases can separate failure mechanisms. Supplying a previously missed item tests what happens after access. Restoring a dropped condition tests representation or inheritance. Supplying an adequate evaluator can expose a candidate-selection problem.

Those diagnostic interventions should be reported separately from end-to-end results. A system that succeeds after receiving the decisive clue has not established autonomous discovery of it.

Held-out combinations should differ from those used to build the routes or descriptors. Compare both performance under a fixed resource envelope and the resources needed to reach a fixed outcome, where feasible.

Assess more than retrieval recall: whether the relevant condition influenced the decision, whether the proposed mechanism was valid, whether the intervention helped, whether the result was novel relative to a declared reference, and whether later work benefited.

Repeated investigations should include failed and unproductive searches. Report full distributions and selected-case limits rather than only the most impressive discovery.

For real research, field significance and empirical replication require appropriate domain work. Planted examples can establish mechanics. They cannot demonstrate a general capacity for scientific breakthroughs.

No experiment is launched by this comparison. It gives focused architects and foragers a way to discriminate candidate mechanisms.

## What I would carry into the next design stage

I propose five principles for later consideration.

1. **Compression is useful and revisable.** Its adequacy is assessed against work, with additional evidence or representations available where the contract supports them.
2. **Retention, discovery and constructive use are distinct responsibilities.** Their failures need different remedies.
3. **Alternative routes and formulations can influence active work.** A retained exception or bridge must be able to change a consequential decision.
4. **Useful discoveries can change cognitive organization.** Representations, procedures and relationships may develop together, with conditions and evidence retained.
5. **Exploration remains bounded and outcome-oriented.** Investigative policies are assessed across their outcomes and costs, including longer-term learning where authorized; each clue need not demonstrate its value before being examined.

These proposals fit the [ANIMA responsibility map](../../RESPONSIBILITIES.md). TL retains its attributable source organization and retrieval responsibilities under its own contracts. TRACE owns its granted interpretation and episode duties. SST can support bounded exploration without becoming the domain's authoritative evaluator. Domain worlds assess their effects and maintain their methods. The broad substrate accommodates revisable cooperation and structural change.

Those boundaries can develop through an accepted transition. This essay does not transfer an existing project's backlog or require a new universal creativity service.

The first architectural commitment I would seek later is a recoverable and revisable relationship between compressed cognition, available evidence and constructive search. The particular residual format, discovery policy, schema language, expert topology and memory placement remain mechanisms to investigate.

Vector 6 can then examine construction repertoires: how useful discoveries become executable operations, how cheap selection exploits them, and how the system escapes or expands a repertoire that no longer fits the task.

## Review and evidence scope

A separate agent read the complete initial essay, the amended passages and both evidence notes for conceptual coherence, fidelity to user intent and calibration of claims. The review prompted explicit assessment of exploratory portfolios rather than known value per item, coverage challenges outside the current interpretation, a probe that can precede an overt failure, and a distinction between source recovery and capability reconstruction. The follow-up review found those ambiguities resolved.

Two research agents inspected the primary studies identified in their notes; their access paths, selected sections and limitations are recorded there. The main author read both notes, inspected RAPTOR's methods and querying comparison with selected scalability passages, and read the Holyoak–Koh publisher abstract after full-PDF access failed. Selected primary passages from Liu, Bartoli and Conti were also checked for the compact claims used here.

The conceptual reviewer did not independently inspect those external papers, reproduce their results or audit the linked project contracts. This is bounded literature inspection and reviewed architectural analysis. It establishes neither empirical superiority, runtime qualification nor acceptance of the proposed mechanisms. The canonical context packet and existing project commitments remain unchanged.
