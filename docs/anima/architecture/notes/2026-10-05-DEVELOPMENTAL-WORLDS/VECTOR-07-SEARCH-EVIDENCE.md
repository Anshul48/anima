# Vector 7 evidence: programme search representations

Date: 2026-10-06. Status: bounded primary-source inspection and proposed macro architecture. No representation, algorithm, programme intervention, or implementation is adopted here.

Read with [Vector 7: programme search](./VECTOR-07-PROGRAMME-SEARCH.md), [Expert worlds and organizational search](./EXPERT-WORLDS-AND-SEARCH.md), the [Synthesis vector-7 row](./SYNTHESIS.md), and [Vector 6’s construction-repertoire conclusion](./VECTOR-06-CONSTRUCTION-REPERTOIRES.md).

The user’s 3A ambition is larger than software construction: substantial projects and an organization’s workflows, alternatives, and relationships should become navigable search material. A separate capability builds the representation; TRACE contributes organization at scale; SST explores consequential possibilities. The question is which distinctions make this useful without confusing a candidate programme with an executed organization.

The evidence below was selected to discriminate three architectural choices: whether alternatives need explicit joint obligations; whether shared conditions and interactions require more than a tree; and whether task decomposition can substitute for modeling time, resources, and actual state. These are precedents for particular functions, not evidence that organizational reliability follows from adopting their notation.

## Three inspected primary precedents

All inspection occurred on 2026-10-06. Entries summarize selected primary passages; the subsequent engineering proposals are independent reasoning, not additional reported findings.

### HyperTree Proof Search: alternative tactics and joint subgoals

Lample et al., [HyperTree Proof Search for Neural Theorem Proving](https://proceedings.neurips.cc/paper_files/paper/2022/file/a8901c5e85fb8e1823bbf0f755053672-Paper-Conference.pdf), NeurIPS 2022, published 13-page paper; [16-page supplement](https://proceedings.neurips.cc/paper_files/paper/2022/file/a8901c5e85fb8e1823bbf0f755053672-Supplemental-Conference.pdf) accessible. Inspected selected §§3–5 passages and supplement C’s definitions. A tactic is an alternative hyperedge; its entire child-goal set must be solved. Children can already exist in the graph. Formal environments evaluate tactics; learned policy and critic guide search. Endpoints are proof rates in Equations, Metamath, and Lean, with transductive cumulative rates distinguished from unseen-statement tests. Value propagation assumes independent child solvability. “Invalid” can mean sampled tactics failed, not proven unprovability. Training and repeated search consume substantial compute. This supports structured formal search, not organizational completion rules, calibrated business probabilities, or execution/resource reliability. No artifacts were reproduced.

### SHOP2: procedural decomposition with modeled time and resources

Nau et al., [SHOP2: An HTN Planning System](https://www.cs.umd.edu/~nau/papers/nau2003shop2.pdf), JAIR 20, December 2003, published 26-page author-hosted PDF. Inspected §§2–3, selected §§4–5 passages, and correctness caveats. Methods provide alternative decompositions into partially ordered subtasks; planning progresses forward through modeled deterministic state, permitting interleaving. Operators express preconditions, effects, numeric calculations, and resource availability. Temporal information is encoded by multi-timeline preprocessing, done by hand in the reported work. IPC-2002 endpoints include problems solved, planning time, and plan quality. Authors report substantial method-crafting effort; algorithmic correctness does not establish fidelity of the domain description. Search therefore exploits supplied procedural knowledge rather than discovering a reliable organization from records. Runtime benchmarks do not account for the complete acquisition and maintenance cost of that knowledge. No code or competition runs were inspected.

### VHPOP: causal support, interference, and limited ordering

Younes and Simmons, [VHPOP: Versatile Heuristic Partial Order Planner](https://www.cs.cmu.edu/afs/cs/project/jair/pub/volume20/younes03a.pdf), JAIR 20, December 2003, published 26-page archive PDF. Inspected §2, action-reuse heuristic, temporal representation, competition results, and discussion. Search refines partial plans with open preconditions, causal links, ordering constraints, and threats to established support. Existing actions can support multiple conditions; reuse-aware heuristic benefits vary by domain. A temporal network represents duration and ordering constraints. IPC-2002 evaluates solved problems, runtime, and plan quality; trying several strategies broadens coverage at additional search cost. The reported version lacks numeric preconditions/effects and assumes supplied action models. It therefore supplies useful distinctions without being a complete quantitative resource planner or a model of organizational uncertainty. Formal models and source code were not independently checked.

## Proposed meaning before representation shape

The programme representation should make different relationships intelligible before choosing a universal graph format. The following are proposed distinctions, not a fixed schema or separate services.

| Relationship | Proposed meaning | Consequential confusion to avoid |
| --- | --- | --- |
| Alternative | Different candidate routes for a declared purpose | Combining incompatible pieces from different candidates as one plan |
| Joint obligation | Conditions or work that a chosen route requires together | Treating completed easy work as sufficient for the whole outcome |
| Shared support | One attributable artifact, condition, or operation can serve several demands | Assuming similar descriptions imply interchangeable support |
| Temporal or causal dependency | A condition must hold at a relevant time or be produced and preserved | Treating an organizational association as a prerequisite |
| Capacity or consumption | Work competes for availability or changes a quantity | Counting a shared pointer as additional available capacity |
| Reformulation | The purpose, scope, assumptions, or success criterion changes | Calling an easier different objective a solution to the earlier one |

A tree can be a useful navigational projection. It need not contain every relationship or become the authoritative organizational model. Work can recur, several branches can share support, and different participants can require different views. A selected search projection might be acyclic while the wider organization includes recurring control and feedback. Repeated episodes and cycles should not be erased merely to fit a proof-tree analogy.

Joint obligations themselves need grounds. Some express adopted requirements; others are procedural hypotheses or uncertain predictions about what will help. A graph builder proposing that two activities depend on one another should preserve the evidence and uncertainty behind that interpretation. Presence in the representation should not silently make the relationship mandatory, true, or currently satisfied.

## Graph building is a capability with its own failure modes

The separate builder could turn accessible records into attributable, revisable views and expose missing or conflicting information. Its useful output would help a participant answer a consequential question: which alternative is blocked, what changed, where a common resource becomes limiting, or which formulation is worth investigating. A larger graph is not intrinsically a better organizational capability.

Record reconciliation can fail through mistaken identity, stale conditions, omitted work, duplicate obligations, or ambiguous language. A task title can describe a future intention, an ongoing action, or a retrospective result. A shared artifact might be valid only for a particular configuration. Inferring these meanings is partly semantic work; exact checks can enforce specified relationships while remaining silent about missing or incorrectly interpreted ones.

TRACE could organize interpretations, histories, conflicts, and conditional lessons across the macro canvas. SST could investigate candidates against a scoped, versioned view. Domain worlds would retain evaluation and execution meaning; STC is a construction caller within this broader canvas. This allocation is proposed continuity with the packet, not a claim about current integrated runtime. Updating a search view should neither enact a candidate nor substitute for the owners’ observations of what actually happened.

## Completion, feasibility, and resource estimates remain different

A useful candidate can be incomplete, a complete modeled plan can be infeasible in current conditions, and a feasible action can produce an unexpected outcome. These states deserve different treatment. Failure to find a route within a search budget should remain distinguishable from showing that a particular route violates an explicit condition or demonstrating impossibility under stated assumptions.

For programme search, a product of branch scores would be a heuristic unless its interpretation and assumptions were established. Shared personnel, infrastructure, correlated mistakes, and common evidence can make branches dependent. Even individually feasible activities may be jointly infeasible when they compete for capacity. Numerical scores should help prioritize inquiry without making unknown relationships look like measured organizational probabilities.

Likewise, the length of a route does not determine its duration, cost, or risk. Some work can overlap; other work occupies a resource for an interval, consumes stock, or changes conditions needed by another activity. Reusable knowledge and consumable capacity have different semantics. Estimates should remain qualified by the state, versions, and observations on which they depend.

These distinctions do not require a human approval event for every ordinary action. Established authority can support continuing work and routine revisions. Changing a consequential objective, governing condition, resource commitment, or execution scope is a different kind of transition. Search should make that distinction visible without becoming a universal central executive.

## Reformulation and a concrete difficult case

Search should be able to question decomposition, acquire missing observations, or propose a different formulation. Merely choosing among known procedures would leave the developmental ambition incomplete. A reformulation should preserve how it relates to the earlier question: equivalent under conditions, a relaxation, a new objective, or a proposal awaiting the relevant authority. It may change what counts as success and which earlier evidence remains applicable.

Consider an organization coordinating a product release and a manufacturing experiment. Both need the same test bench, while a calibration result may be reusable by both under a particular configuration. One candidate runs the experiment first; another reserves the bench for release qualification. Each has several joint obligations, and each can look feasible when assessed alone. Together they may violate the bench’s availability. An experiment can also change the configuration and invalidate the release’s assumed calibration.

The useful search capability would expose the shared condition, capacity conflict, and threatened evidence, then compare legitimate sequences or identify an observation that changes the decision. It could preserve a creative proposal to replace some work with simulation while distinguishing the changed evidence standard. A calendar entry or favorable graph score would not establish that the bench is ready, the qualification passed, or the new standard was accepted.

## Stronger simple alternatives and discriminating questions

A strong baseline combines an attributable workflow/dependency map, existing schedules and resource records, capable generative reasoning, and local domain checks. For bounded decisions, an authored task model or a conventional scheduling/constraint tool may provide most of the useful structure. These alternatives should have access to equivalent evidence and expertise. A new SST representation earns its cost when it finds useful alternatives, preserves dependencies, or supports revision better than those arrangements.

Three questions could discriminate the proposal without launching an organizational audit:

1. Does the representation change a consequential decision by exposing a shared condition, interference, capacity conflict, or viable alternative that a capable simpler view misses?
2. Can it revise the formulation and reconcile changed evidence without silently inheriting obsolete completion claims or discarding still-applicable obligations?
3. Do useful gains remain after graph acquisition, correction, synchronization, search, evaluation, and attention costs, including unfinished work and mistaken recommendations?

## Inspection and transfer boundary

The three full primary papers and HTPS supplement were accessible; inspection was selective. Two SHOP2 archive fetches failed before the author-hosted published PDF was obtained. Source repositories, benchmark artifacts, and live organizational records were not opened; their present availability and reproducibility were not verified. This is neither a systematic survey nor source reproduction, acceptance, or programme qualification. No experiment, implementation, paid call, private-corpus access, or active-programme audit occurred. All extensions to ANIMA remain proposals for later user direction.
