# Vector 7 evidence note — Computation allocation and programme search

Status: bounded primary-source inspection, 2026-10-06. All ANIMA implications below are proposals. No allocation policy is selected, experiment launched, or programme capability accepted. Companion: [Vector 7 — Programme search](VECTOR-07-PROGRAMME-SEARCH.md).

The current organizational distinction is between alternatives, dependencies, adopted execution and supporting evidence. A displayed search tree cannot become the authoritative project graph merely because it is convenient to traverse. This note follows [EXPERT-WORLDS-AND-SEARCH.md](EXPERT-WORLDS-AND-SEARCH.md), the vector-7 row in [SYNTHESIS.md](SYNTHESIS.md), and Vector 6's [lifetime-cost and comparison treatment](VECTOR-06-CONSTRUCTION-REPERTOIRES.md). The question is when additional investigation, construction or coordination is worth its resources, including shared infrastructure and later reuse. Three precedents address different parts of that question.

## Selected primary precedents

**1. Hay, Russell, Tolpin and Shimony, _Selecting Computations: Theory and Applications_.** Inspected [arXiv:1207.5879v1](https://arxiv.org/html/1207.5879v1), submitted 2012-07-25, UAI 2012: selection formulation, context effects, myopic/blinkered policies, selected sampling comparisons and reuse discussion. The full proofs and implementation were not independently audited.

The paper models gathering evidence before selecting an action, maximizing expected selected utility minus computation cost. It constructs a case where optimal computation priorities change with a competing alternative, even with independent action values. A one-step policy can stop prematurely because several computations are needed to change the eventual choice. A blinkered approximation considers repeated computations affecting one action under independence assumptions. Comparisons use Bernoulli selection problems and Go-related sampling. Bounded utilities, modeled evidence and simplified sampling costs constrain the results. Future reuse of rollouts is identified as requiring a nontrivial extension, rather than solved by the basic local formulation. This supports decision-sensitive allocation, not a complete organizational allocator. [Primary revision](https://arxiv.org/html/1207.5879v1).

**2. Li, Jamieson, DeSalvo, Rostamizadeh and Talwalkar, _Hyperband: A Novel Bandit-Based Approach to Hyperparameter Optimization_.** Inspected the fixed [JMLR 18(185) article](https://jmlr.org/papers/volume18/16-558/16-558.pdf), revised 2017-12, published 2018-04: resource-allocation algorithm, selected experiments and practical discussion, and theoretical problem formulation. Proofs and code were not independently audited.

Hyperband runs successive-halving brackets that trade the number of configurations against the resource initially allocated to each. Poorly ranked configurations receive no further allocation within that bracket; other brackets use less aggressive stopping. Its finite-horizon algorithm takes a maximum resource and an elimination parameter. Experiments cover deep-learning and other configuration problems, with benefits varying across cases. Initialization, resumption and validation overhead can erase speedups on cheap trials. Resource-dependent hyperparameters make small-resource performance less informative about larger-resource performance. The theoretical setting uses convergent loss trajectories, while practical allocation lacks their convergence envelopes. This is a precedent for staged screening under a declared fidelity model, not evidence that research programmes can be safely pruned by early scores. [Published primary article](https://jmlr.org/papers/volume18/16-558/16-558.pdf).

**3. Policella, Smith, Cesta and Oddi, _Generating Robust Schedules through Temporal Flexibility_.** Inspected the [ICAPS 2004 proceedings paper](https://icaps04.icaps-conference.org/icapspapers/ICAPS04PolicellaN.pdf), pages 209–218: resource/temporal model, partial-order schedule definition, selected construction methods, benchmark evaluation and concluding limitations. No code or execution data was reproduced.

The paper constructs partial-order schedules for project scheduling with minimum/maximum time lags and limited renewable resources. Activities have declared durations and demands. It compares resource-envelope conflict resolution with constructing an earliest-start solution and converting it into flexible resource chains. On the tested benchmark, the latter arrangement generally gives better efficiency and robustness measures. Comparisons of solution quality use instances solved by all tested approaches; none solves every instance. Robustness includes flexibility metrics and a disruptibility measure restricted to one unexpected temporal event at a time. A resource-feasible family of schedules remains conditional on the modeled problem. This supports retaining execution flexibility, not predicting unknown research value or solving arbitrary organizational change. [Primary proceedings PDF](https://icaps04.icaps-conference.org/icapspapers/ICAPS04PolicellaN.pdf).

## Proposed separation of five questions

Programme allocation should keep several kinds of judgment distinguishable:

| Question | Relevant meaning | What it does not establish |
|---|---|---|
| Task assessment | Whether a result addresses the governing objective | That the work is authorized or resources are available |
| Alternative valuation | Predicted benefits, uncertainty and possible information gain | An observed outcome or a trustworthy numerical utility |
| Scheduling | Which admissible activities can coexist or follow one another | That durations, dependencies and capacities were modeled adequately |
| Execution state | What was adopted, started, observed, interrupted or completed | That a completed activity achieved its desired effect |
| Authority and bounds | Who may commit resources or change consequential state | Which permitted alternative is most useful |

These are responsibilities, not five new services. A dependency can be observed, proposed or mandatory. A local allowance does not create additional shared capacity. An attractive search branch cannot silently reserve someone else's apparatus or relax its own objective. Domain owners retain assessment and operational custody; SST can explore attributable alternatives against an available view. Existing source and episode responsibilities are not transferred by this note.

## Information is valuable through decisions and future use

Additional computation can sharpen a prediction without changing a useful action. Conversely, a modest observation can change a consequential choice. Proposed allocation should therefore connect investigation to what it could alter: a candidate, an applicability condition, a schedule, an experiment, or a retained method. Uncertainty reduction alone is an incomplete target.

Immediate action change is also too narrow. A computation can reduce expected failure consequences, enable a later decision or develop reusable machinery. Its intended horizon should be declared without pretending the number of future uses is known. Predictions about such benefits remain estimates, distinct from later evidence of reuse.

Joint value is a further complication. Two checks may together distinguish explanations although neither alone changes the current choice. A representation repair may be needed before an experiment becomes informative. Scoring each step by its immediate marginal result can reject the whole useful sequence. Small packages of related work and bounded lookahead are candidate responses. They introduce their own search cost; no exhaustive sequence search or universal value oracle follows.

The allocation computation itself competes for resources. Estimating precise values for many cheap tasks can cost more than simply doing useful work. Coarse priorities, explicit prerequisites, ordinary queues and occasional targeted comparisons remain serious alternatives to elaborate metareasoning.

## Fidelity, delayed evidence and false pruning

A cheap screen needs an account of what it predicts about the eventual objective. A short simulation, static check, preliminary measurement and complete task trial provide different evidence. Their costs and biases may change as the candidate develops. Faster feedback is helpful only when its omissions are acceptable for the decision being made.

A slowly developing candidate can look weak before a prerequisite or calibration is available. A branch with absent evaluation is not a branch with observed poor quality. Delayed outcomes and unfinished work also create censoring: the allocator sees more results from whatever it already prefers. Shared models, fixtures and data can correlate apparently separate observations. Counting them as independent successes exaggerates confidence.

Proposed pruning should distinguish stopping current allocation, retaining a recoverable candidate, and claiming that a method is unsuitable. A changed task, new evidence or a repaired prerequisite can justify reconsideration. These recovery routes need actual artifacts and available conditions; permanent active tombstones are unnecessary. Nor should every dormant candidate acquire an unlimited future claim on resources.

## Shared infrastructure and a hypothetical decision

Consider two fictional component-investigation worlds and a control-integration project sharing a calibrated test rig. One candidate has good preliminary results under ordinary loading. Another needs a diagnostic sequence before its history-dependent model can be assessed. A common measurement problem affects both investigations.

Independent early-score racing could terminate the second candidate and cause both worlds to repeat the same calibration work. A dependency-aware alternative could investigate one shared probe, retain competing explanations, and allocate the rig around ongoing work. If useful, the probe and resulting interpretation could become a reusable joint procedure. The participants might then revise their experiment selection and their relationship's custody of that procedure.

Those benefits are hypothetical. The shared investigation could delay more valuable work or fail to transfer. The allocator needs evidence of current occupancy, relevant constraints, expected cost and who may revise the schedule. A proposed cancellation does not release the rig before execution acknowledges the resulting state; some physical work cannot be paused cheaply. The adopted schedule and observed apparatus state must remain distinguishable.

Shared prerequisites, retained models and common tools also make project benefits nonadditive. A capability can help several tasks, while incompatible users can impose coordination and maintenance costs. An organizational graph should express those relationships without duplicating the shared resource in each displayed branch.

## Proposed capability comparisons

A strong simpler comparator is a competent coordinator using explicit dependencies, ordinary priority rules, shared records, suitable checks and capable domain methods. It should be allowed to revise plans and reuse tools. Learned allocation, staged fidelity and richer programme models should be added separately where feasible, rather than compared with a deliberately inert scheduler.

Include late-improving candidates, jointly informative checks, uncertain dependencies, shared bottlenecks, delayed/correlated feedback and misleading cheap evaluations. Include routine cases where added coordination is wasteful. Examine actual useful outcomes, consequential omissions, false pruning, unnecessary investigation, deadline effects and later transfer.

Charge assessment, state reconstruction, allocation, scheduling, synchronization, setup, restart, execution, repair, retention and human attention. Compare fixed-resource capability and resources needed for a specified outcome where meaningful. Keep total expenditure and elapsed time separate. Discovery and maintenance costs belong to both learned and authored baselines, following Vector 6's experience-horizon accounting.

Transfer should test changed task families, resource conditions and callers. Reusing a value predictor or scheduling method differs from reusing a domain capability. Successful local selection, tuning or scheduling establishes a scoped mechanism; none alone demonstrates an adaptive programme across worlds. Diagnostic interventions should remain separate from autonomous end-to-end results. These are research comparisons, not launched experiments or acceptance thresholds.

## Access and provenance limits

All three selected primary texts were accessible. A CP Optimizer lead exposed subscription-only body text and was replaced by the accessible ICAPS precedent; its abstract supplies no empirical claim here. Inspection was selective, not reproduction or a complete proof audit. No model APIs, experiments, real project audits, private corpus or B archives were accessed. Only this assigned note was written.

Current ANIMA documents govern the interpretation; no historical project qualification is asserted.
