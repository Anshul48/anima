# Vector 6 evidence note — Cheap choice over construction repertoires

Status: bounded primary-source inspection and proposed architecture, 2026-10-06. No dependency is selected, experiment launched, or construction capability accepted. Companion: [Vector 6 — Construction repertoires](VECTOR-06-CONSTRUCTION-REPERTOIRES.md).

The direct 4A intent is a larger reasoning participant using cheap tools to decompose work, followed by reasoning and structured selection within a field such as frontend. The user explicitly recognizes that Jev is not generative. It might choose elements or styles, identify modules needing work, and select among standard next states. The question is whether that arrangement can become expressive construction machinery and extend to other fields. The supplied savings, proof and latency assertions were accompanying model commentary, not user requirements. This note develops the distinctions in [CONSTRUCTION-LANGUAGES.md](CONSTRUCTION-LANGUAGES.md).

## Selected primary evidence

**1. TypeSafe documentation and launch report.** Inspected on 2026-10-06: current, unversioned Introduction, Choice and Confidence pages; selected technical-results and limitations passages in the founder's launch report dated 2026-09-15. No live API request established a served model revision.

Jev accepts state and typed questions, returning predefined choices, ordered scores or yes/no probabilities. Choice supports up to 255 options. Its confidence statistic normalizes the selected option's probability above the uniform baseline; it is computed from the returned distribution. Several questions can be evaluated separately against one supplied state in one request. These are documented interface properties, not evidence that answers are correct or jointly compatible. The launch workflow evaluation uses averaged probabilities from stronger models as its reference, rather than ground-truth classification or completed construction outcomes. Thus those rankings measure agreement under an engineered workflow. They do not establish menu adequacy, independent verification, or end-to-end building capability. [Introduction](https://docs.typesafe.ai/introduction), [Choice](https://docs.typesafe.ai/primitives/choice), [Confidence](https://docs.typesafe.ai/confidence), [launch report](https://typesafe.ai/blog/introducing-system-one-models-and-jev).

**2. Sun, Xu, Shi and Yang, _Type-Safe Is Not Error-Free_.** Inspected [arXiv:2609.26758v2](https://arxiv.org/html/2609.26758v2), revised 2026-09-23: abstract, type-safety definition, reassignment methods, main results and limitations. Appendices, datasets and model code were not independently audited.

The study keeps questions, states, option names and definitions fixed while changing which name is attached to each definition. Its central binary evaluation contains 1,200 English workflow decisions; additional tests use other splits. Jev and two open-weight typed models show name sensitivity, especially where familiar polar names conflict with explicit definitions. Outputs remain type-valid while definition-level choices and score rankings deteriorate. Neutral or random names behave better in the tested binary conditions. This isolates an interface failure beyond parsing; it does not estimate ordinary construction error rates. Jev was a nondeterministic, closed API at one point in time and may change. The proposed training mitigation was not evaluated. [Primary revision](https://arxiv.org/html/2609.26758v2).

**3. Ong and colleagues, _RouteLLM: Learning to Route LLMs with Preference Data_.** Inspected [arXiv:2406.18665v4](https://arxiv.org/html/2406.18665v4), revised 2025-02-23: abstract; selected formulation, training and classifier methods; benchmark, model-transfer, cost and overhead results; concluding limitations. Code and appendices were not independently audited.

RouteLLM learns request-level routing between stronger and weaker generative models using preference data and augmentation. Four router approaches are evaluated on MT Bench, MMLU and GSM8K, initially routing between GPT-4 and Mixtral. Arena-only training performs poorly on some out-of-distribution benchmarks; relevant augmentation improves results. Some routers transfer to other model pairs without retraining. This supports learned allocation under specified query distributions, rather than a universal model ranking. Benchmark answers and judge scores do not establish construction effects, operation applicability or menu completeness. Historical cost estimates and separately profiled routing overhead remain specific to the paper's setup. Its results do not supply a current Jev saving or a frontend reliability guarantee. [Primary revision](https://arxiv.org/html/2406.18665v4).

## Proposed decision boundaries

The useful unit is a choice whose interpretation and downstream effect can be assessed. A menu-valid output supplies only membership in the declared set. Even perfect selection cannot choose an absent operation, recover omitted state, or make an incorrectly described operation fulfill the task.

Four failures should remain distinguishable:

- **Menu inadequacy:** no offered action can achieve a necessary effect, or the offered abstraction makes a useful sequence inaccessible.
- **State inadequacy:** the selector lacks a relevant condition, observes stale state, or receives a mistaken task interpretation.
- **Meaning inadequacy:** names, parameters, schema versions or applicability descriptions do not reliably communicate the intended operation.
- **Selection error:** with adequate information, meanings and options, the policy chooses an inappropriate alternative.

Execution and assessment can fail after an appropriate choice. Those failures should not be relabelled as classification errors. Conversely, an operation succeeding once does not establish that its applicability rule is correct. Keeping these distinctions makes a local repair informative: add an observation, revise an operation, change a representation, improve the policy, or repair execution as the evidence warrants.

Menu completeness is always relative to a bounded demand and a useful level of action. A list need not contain every final design if it contains expressive operations and a way to construct missing ones. Composition nevertheless creates dependencies that individual option descriptions can omit. A learned macro earns its place by enabling useful effects or reducing repeated effort, alongside adequate applicability and failure knowledge.

## Escape and dependable checking

An explicit escape can mean obtaining missing evidence, investigating applicability, revising the task decomposition or developing a new operation. A `none of the above` label alone does not establish that the policy will recognize an inadequate menu. Low-confidence fallback also misses confidently wrong choices. Escape behavior and missed escapes need their own assessment, including cases with plausible but insufficient options.

A stronger reasoning participant can diagnose representation or repertoire gaps; it need not receive every uncertain step. Nor does greater model capability automatically resolve missing observations. Rules, deterministic tools, authored procedures and specialist methods deserve the same opportunity to handle suitable work. Ordinary investigation proceeds under established delegation rather than requiring a human approval at each branch.

Learned screening and dependable checking serve different purposes. A model can flag a suspicious dependency, rank tests or predict whether a change violates a condition. An applicable static analysis, exact computation or runtime check can establish a narrower fact under its modeled semantics. Neither a classifier score nor a type-valid answer proves that fact. A checker also needs a faithful requirement: proving an encoded predicate does not establish that the predicate captures the desired behavior.

Repeated judgments are not independent evidence merely because they are separately requested. Shared observations, omitted conditions, learned priors or option meanings can correlate their errors. Selection and review based on the same faulty state can agree throughout. Actual effects and suitable independent evidence therefore matter more than the number of approving outputs.

## Serial work and total cost

Questions about one already available state may be batched. A decision depending on an action's uncertain resulting state may need refreshed evidence or a justified transition model. A known composition can execute several actions before observing their joint outcome; a compound policy can manage observations internally. Predicted and observed effects remain distinct. Parallel typed answers about the original state do not by themselves resolve those dependencies or ensure a coherent joint action. Speculative batching can save round trips while spending work on branches never used. Hierarchical menus reduce immediate cardinality but can exclude the right operation through an early routing mistake.

The relevant accounting includes observation and state preparation, menu construction, inference, networking, execution, checks, retries, repairs, fallback, repertoire acquisition and maintenance. Cheap decisions can become costly through repeated calls or downstream errors. Latency should include serial dependencies and actual deployment conditions. No edge-runtime measurement, zero-cost verification claim, or numerical saving is established here. Current pricing was not assessed; publication-time estimates are not forecasts for this architecture.

## A concrete repertoire hypothesis

Consider a hypothetical notification panel. A larger model supplies a plan and authored operations for displaying a badge, opening a panel and marking items read. A cheap selector can choose among them. Those choices may all be type-valid while the repertoire lacks a way to preserve unread state correctly when updates arrive during interaction.

The constructive escape would inspect the observed event sequence, revise the state representation, and develop a suitable interaction operation with explicit update semantics. A reasoning participant or another appropriate method can help construct it. Rendering, keyboard behavior and state consequences need relevant evidence; ranking the resulting code against another model's opinion is a different assessment.

Later selection could exploit that new operation cheaply. Inheritance should preserve its conditions and versioned meaning. If a new product has different update behavior, the successor should be able to adapt the operation or its selection conditions. This is repertoire and policy development, beyond replacing a costly call with a small classifier. It is a hypothetical path, not evidence that frontend or another field is already a closed world.

## Capability-first comparisons

A proposed comparison should include capable generative work with tools and reuse, authored operations with ordinary selection rules, and learned selection over the same repertoire. An expanding repertoire adds a separate claim. Give alternatives comparable observations, tools, learning opportunities and complete budgets; do not handicap the baseline by denying reusable procedures.

Include familiar tasks, missing operations, missing state, meaning-preserving interface variations, misleading confident choices and changed requirements. Measure useful completed behavior, consequential omissions, appropriate escape, unnecessary fallback, repairs and human attention. Report fixed-budget capability and the resources needed for an assessed outcome where feasible. Study later reuse rather than only retrospective compression, charging discovery and maintenance costs.

Cross-field extension should ask which operations and applicability knowledge transfer, what must be reconstructed, and whether changed evidence requirements overwhelm cheaper selection. Different fields can require different evaluators and action repertoires. No universal next-state taxonomy or permanently privileged model class is selected.

## Inspection and authority limits

Official documentation and two primary research revisions were accessible. No model APIs were called, results reproduced, pricing assessed, or private corpus accessed. Workspace context was the construction note and direct user intent supplied by the root architect. The companion essay owns the architectural synthesis; these findings confer no implementation or acceptance authority.
