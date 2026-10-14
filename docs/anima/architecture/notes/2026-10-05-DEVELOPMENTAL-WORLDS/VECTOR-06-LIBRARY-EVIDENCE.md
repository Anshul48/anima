# Vector 6 evidence: learned construction repertoires and search languages

Date: 2026-10-06. Status: bounded evidence note and architectural proposals; no ratified requirements, implementation, replication, or capability qualification.

Read with [Construction languages](./CONSTRUCTION-LANGUAGES.md) and [Vector 6: construction repertoires](./VECTOR-06-CONSTRUCTION-REPERTOIRES.md). This note develops the user’s ambition of learning increasingly useful ways to construct things. It examines executable abstractions and reusable programs rather than prescribing a neural circuit.

The proposed architectural thesis is that experience could improve both **what a system can express and perform** and **how it finds a suitable construction**. These are separable achievements. A compact library may describe yesterday’s solutions elegantly while making tomorrow’s unfamiliar problem harder to interpret. A useful operation may deserve retention despite weak compression because it handles an uncommon but consequential situation. A better search policy may help without changing the available operations. The desired outcome is useful completed behavior with defensible total costs; language compression is one possible contributor.

## Three inspected primary studies

The entries below keep empirical summaries compact. All inspection occurred on 2026-10-06. Engineering reasoning after these entries is independently proposed, not another result attributed to the papers.

### DreamCoder: representations and search develop together

Ellis et al., [DreamCoder, arXiv:2006.08381v1](https://arxiv.org/abs/2006.08381v1), 2020-06-15. Accessible [22-page primary manuscript](https://courses.cs.washington.edu/courses/cse599j1/22sp/papers/dreamcoder.pdf); inspected algorithm, task definitions, held-out results, ablations, and discussion; supplement not inspected. It learns typed program abstractions from solved tasks and a recognition model guiding search, trained on replayed and generated problems. Held-out task-solving evaluations include list processing, text editing, graphics, and simulated construction. Ablations support contributions from both library and recognition learning. Author-chosen primitives, encoders, and task-specific observational scores bound applicability. Training typically takes about a day on 20–100 CPUs; this is separate from later task-search times. Bootstrap depends on discovering initial solutions; generated problems remain expressible in the current language. These results do not qualify arbitrary software behavior or establish full lifecycle costs.

**Version boundary:** [PLDI 2021 abstract/metadata](https://dspace.mit.edu/entities/publication/86d768ab-558f-4fb1-b92e-9288de643ccb) inspected; final published PDF inaccessible. Detailed findings here come exclusively from 2020 v1.

### Stitch: faster abstraction acquisition, with a different endpoint

Bowers et al., [Top-Down Synthesis for Library Learning](https://doi.org/10.1145/3571234), POPL, January 2023. Accessible [42-page published primary PDF](https://mlb2251.github.io/stitch.pdf); inspected overview, utility, algorithm scope, experiments, and conclusion; proofs not reproduced. Stitch searches for binding-aware abstractions that compress supplied lambda-calculus programs. Its DreamCoder comparison reprocesses saved solution traces; measured time includes abstraction learning and rewriting, not the whole synthesis cycle. Large-corpus evaluation uses eight graphics/construction domains and repeated random 80/20 splits, testing compression of already-written held-out programs. Reported phase speedups and memory savings therefore concern library acquisition. The stated optimality concerns each abstraction under specified utility and search conditions, not a globally optimal language. Repeated library construction and compression transfer do not establish prospective task-solving gains, applicability judgments, or maintenance economics.

### Voyager: interaction, program retention, and prospective reuse

Wang et al., [Voyager, arXiv:2305.16291v2](https://arxiv.org/html/2305.16291v2), 2023-10-19. Full primary HTML accessible; inspected §§2–4, algorithm, verification prompt, experimental setup, and transfer/ablation tables. GPT-4 generates JavaScript over authored Minecraft APIs, retrieves successful programs, and repairs candidates using execution/state feedback without weight updates. New-world transfer tests four item tasks with three trials each. Library use improves prompting efficiency; the ablation still solves three task families in all trials. Metrics cover game progress, not cross-API transfer. Admission uses LLM success judgments, which can err; death recovery preserves inventory. Failed tasks inform curriculum, but admitted skills come from judged successes. Prompting iterations are not full token, execution, acquisition, or maintenance costs. No code reproduction was performed.

## What these distinctions mean for the proposed architecture

An executable repertoire should be understood through the work it enables. A candidate operation might encode a transformation, an investigation method, a repair strategy, or a way to formulate a task. Its useful identity would include the assumptions under which it was assessed, the state it needs, its dependencies, its effects, and the outcomes that would count as success. These are proposed functional responsibilities. They need not become a mandatory metadata ceremony for every small operation.

Three questions should remain separate: can a program be expressed and executed; does it satisfy the observations or checks supplied; and does using it here achieve the user’s intended result? Evidence for one question can help another without settling it. A semantics-preserving rewrite under an explicit formal model gives a precise claim about that model. It does not supply a missing product objective, certify the selected operation’s applicability, or cover effects excluded from the model. Conversely, a useful operational method may have empirical rather than formal support and still deserve scoped reuse.

Compression is a proposed selection signal, not the definition of expertise. Its preference depends on the corpus, representation, coding costs, permitted transformations, and available candidates. A corpus of common successes can reward abstractions that ignore unusual states. Future tasks can require a different decomposition. A construction language would earn its place by helping interpretation, search, adaptation, execution, and assessment together. An optimal result for an explicit compression problem remains valuable within that problem; it does not establish an optimal language for reasoning.

## Proposed co-development without a closed menu

Repertoire growth could shorten useful constructions while increasing the number of plausible choices. Therefore, operation acquisition and the policy for recognizing useful operations should be considered together. The policy would learn conditional relevance from task features and experience, including where reuse fails. Confidence in a choice would remain distinct from evidence of success. A cheap selector can reduce recurrent reasoning expense; uncertain applicability may still call for inspection, a different formulation, or a more capable generator.

The proposed language should include investigation and reframing. Otherwise an apparently intelligent selector can repeatedly choose edits that cannot resolve the actual problem. A system may need to inspect a state transition, establish a missing requirement, compare incompatible interpretations, or identify a dependency before selecting a construction. These methods are also reusable capability. The goal is a repertoire that makes appropriate reasoning and action easier, with room to invent a missing method when existing choices are inadequate.

Different expert worlds could preserve alternative abstractions for the same behavior. One representation might favor compositional control, another diagnosis, another user journeys. Sharing an executable component need not collapse these interpretations into a single vocabulary. Compatibility, translation, and historical meaning would matter whenever worlds cooperate or reorganize. A shorter name alone would not establish successful fusion, and copying a library alone would not reproduce the experience needed to use it well.

## Bootstrap, failure, and incomplete constructions

Learning from successful constructions is a reasonable proposed starting point because observed success supplies concrete material. It also creates a possible coverage trap: the current language and search method determine which problems get solved, and those solved problems determine the next abstractions. A recurring failure may indicate a missing operation, an unsuitable representation, poor search guidance, inaccurate state, or a faulty evaluator. These explanations should remain distinguishable.

Failure and partial work could therefore be retained as evidence with explicit status. An incomplete candidate might reveal a useful subproblem decomposition; an execution failure might establish a dependency or a forbidden assumption. Neither should become a trusted general skill merely because its code is frequent. Extracting a reusable successful subcomponent would require evidence about that subcomponent’s behavior and scope, separate from the failed whole. This is a proposal for preserving learning opportunities, not a claim that any inspected system already provides comprehensive failure-derived expertise.

Recombination and generated practice could widen experience within an existing repertoire. They could also repeatedly exercise familiar biases. A prospective development path would need access to unfamiliar demands, changed conditions, and independent assessment. More elaborate constructions are not automatically broader competence; a new abstraction can redistribute search difficulty or hide it inside a dependency.

## Costs and prospective value

For ANIMA, the proposed accounting question is whether learning and using the repertoire improves useful outcomes after paying the costs it causes. Selected phase speed, compressed program size, number of model prompts, and realized task quality should be kept separately visible. A reported improvement in one is evidence about that measure, not a substitute for the others.

| Proposed cost category | Why it can change the conclusion |
| --- | --- |
| Acquisition and search | Discovery, candidate evaluation, and training may exceed later savings. |
| Interpretation and retrieval | A compact abstraction may require more context or create more ambiguous choices. |
| Execution and recovery | A short call can trigger expensive work, retries, or irreversible effects. |
| Assessment | Better apparent success can reflect weaker checks or more evaluator assistance. |
| Maintenance and attention | Dependency changes, migrations, invalidation, and operator intervention can dominate repeated use. |

These are proposed accounting categories, not a demand to make every operation wait for human approval. Existing authorized routines could continue within their established conditions. Consequential changes in assumptions, authority, effects, or cost would be the cases that require renewed attention. Preserving versions and past evidence would support historical interpretation while allowing legitimate replacement and revision.

Prospective value should include capability, reliability, and expense. An abstraction may be worthwhile if it enables an otherwise unreachable task despite increasing computation. Another may be worthwhile because it makes familiar work cheaper without broadening capability. Another may deserve retirement from active selection because its assumptions changed while remaining useful historical evidence. These outcomes should not be forced into one compression ranking.

## A concrete scenario and discriminating questions

Suppose a world repeatedly builds notification panels and learns reusable operations for rendering, loading, and updating unread state. A later task introduces optimistic updates, reconnect recovery, keyboard navigation, and a server that can return stale counts. Reusing the visual pattern can succeed while the complete interaction fails. The useful learned repertoire might include a method for checking consistency across local and remote state, alongside construction operations. A minimal successful panel and a reliable reconnect journey warrant different claims.

A strong simpler alternative is an authored component library plus searchable cases, a capable generator, and established evaluators. Learned abstractions should be compared with that alternative at comparable outcomes and total budgets. The benefit might come from better experience retrieval or evaluation rather than library invention. This comparison preserves the ambition of developmental capability while making the particular proposed mechanism accountable.

Three architectural research questions remain open:

1. Does an acquired abstraction improve future search or completed behavior on unfamiliar task families and changed conditions, beyond representing their existing solutions more compactly?
2. When a barrier recurs, can the system distinguish a missing operation from interpretation, state, search, or evaluation failure, and learn useful scope from partial work without promoting unsupported behavior?
3. Do gains survive acquisition, dependency changes, assessment, and attention costs when compared with authored libraries, case retrieval, and direct generation?

This note is a selected documentary inspection of three primary studies and one related publication record. It is not a systematic survey, a reproduction of reported results, a source-code audit, or evidence that ANIMA currently has these capabilities. All proposed transfers to TRACE, SST/STC, and expert worlds remain hypotheses for later user direction.
