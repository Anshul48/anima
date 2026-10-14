# Learned construction languages and cheap decision policies

Architecture proposal, 2026-10-05. This note develops input 4A, connects it to the earlier schema discussion and STC/SST/TRACE, and separates the useful hypothesis from unverified claims in the supplied model commentary. It selects no model, API, assurance profile or product integration.

## The useful idea in 4A

The important possibility is that a construction system can learn a repertoire of meaningful operations and increasingly solve tasks by choosing, composing and adjusting those operations. A more capable generative model can supply missing abstractions, diagnose inadequate formulations and construct new operations. Cheaper policies can handle familiar choices when the state representation and available actions are adequate.

This could make progress toward domain expertise rather than only reduce the cost of routing model calls. A domain expert has useful concepts, reusable actions, ways of recognizing applicable actions, and feedback about when those actions fail. The repertoire and the policy for using it should develop together.

An ordinary component catalogue provides a starting vocabulary. A learned construction language adds relationships, applicability conditions, task effects, failure patterns and reusable compositions. A frontend world might eventually recognize a need for an accessible selection flow and compose appropriate interaction, rendering, persistence and validation operations. It should also recognize when none of its existing compositions fits.

The hypothesis is not that a larger model must perform every abstract decision. Allocation should depend on what a computation can resolve. A deterministic tool, a specialist procedure or a cheaper model may be adequate at any level. A capable model becomes particularly valuable when the existing representation or operation set cannot express a useful next move.

There is relevant prior art. DreamCoder jointly learned symbolic abstractions and neural guidance for program search through a wake-sleep process, including replayed and imagined problems. It demonstrates useful repertoire development in specified programming domains. It does not establish that arbitrary software construction becomes reliable once a classifier selects operations. [DreamCoder primary paper](https://arxiv.org/abs/2006.08381)

## What must exist beneath selection

A proposed construction world needs several distinguishable objects:

| Object | Purpose | What can go wrong |
|---|---|---|
| Task interpretation | Establish desired behavior, context and unresolved intent | A clear-looking decomposition can encode the wrong requirement |
| State representation | Describe relevant current conditions | Missing interaction state makes otherwise sensible choices fail |
| Operation repertoire | Provide executable edits, compositions and investigation moves | A catalogue can be incomplete or overly rigid |
| Applicability model | Identify when an operation should be considered | Preconditions may be uncertain or stale |
| Selection policy | Choose the next action or useful batch | A valid option can still be inappropriate |
| Evaluation and feedback | Establish consequences and correct the process | An evaluator can reward appearance while missing actual behavior |
| Retained experience | Reuse successful procedures and attributable failures | Summaries may erase exceptions or preserve obsolete advice |

These are responsibilities, not seven mandatory services. Some may initially be implemented through ordinary tools, explicit rules and authored procedures. Learned mechanisms earn their place when they improve capability or total effort under realistic conditions.

An operation should have inspectable meaning: what it changes, the circumstances where it is useful, relevant dependencies, possible failures, and the evidence available for its effect. An operation that inserts a component differs from an operation that establishes a working interaction. Rendering a popover says little about keyboard behavior, state recovery, data consistency or whether a popover fits the user journey.

The repertoire should include investigation and reframing operations. If it contains only edits, a selector facing an unresolved requirement will keep selecting edits. Useful alternatives include inspecting runtime behavior, obtaining missing domain information, comparing interaction designs, running a targeted experiment, and returning to the task interpretation.

## Why frontend is a good experiment and an incomplete closed world

Frontend work contains many recurring structures: grids, forms, menus, panels, validation patterns, visual hierarchies and navigation flows. These give a construction system useful reusable material. Once product intent is reasonably settled, substantial work can become structured.

But a finite component catalogue does not make the entire task a finite menu problem. Composition introduces interactions among state, layout, accessibility, asynchronous data, device size, motion and user expectations. The next useful design may require a new operator or a different decomposition. A selector cannot choose an absent option, regardless of its accuracy over the options supplied.

A concrete example is a notification panel. Selecting a badge and a popover may be a good beginning. The design still needs to determine what counts as unread, how updates arrive, how focus moves, what happens after a failed network request, and whether the panel supports a user's real workflow. Some questions can be resolved mechanically; others need observation, generative design or clarification.

The attractive experiment is therefore a partially structured world with an explicit escape route. The system can exploit familiar operations while retaining the ability to discover missing ones. That is consistent with the user's interest in schemas that support compression without sterilizing the underlying material.

## The relationship to abstract schema + specific schema + delta

A general construction schema can express notions such as state, interaction, dependency, observation and intended effect. A domain schema can express frontend-specific conventions. A delta can retain the particular product's unusual behavior, exceptions and unresolved questions.

This organization is useful only if it reduces practical interpretation and construction effort. A short encoded description may be difficult to retrieve, disambiguate or execute. The cost of explaining the schema to a model can also exceed the tokens saved by using it.

There are several possible degrees of integration. Initially, the model can receive a small relevant schema and direct source evidence. Later, stable operations could be compiled into tools or reused through trained representations. Further research could adapt models to the repertoire. These are distinct experiments; the success of one does not establish the others.

Changes to schemas must preserve the meaning of retained experiences. If a selection operation's semantics change, an old success record may no longer describe the new operation. Representing versions, applicability and source evidence is part of the cost of inheritance. That cost should be measured rather than hidden by treating every recorded success as eternally reusable.

Diversity remains valuable. Several equivalent representations or construction methods can coexist when they reveal different affordances. A common exchange format need not force all worlds to think in one canonical internal language. The repertoire may standardize execution interfaces while preserving alternatives in interpretation and search.

## What Jev can actually contribute

Official descriptions present Jev as a text-input decision model returning typed choices, scores and yes/no-style outputs. It does not generate prose, hold a conversation, make tool calls or construct a multi-step plan on its own. The consumer supplies state and questions and executes the resulting policy. OpenRouter also explicitly distinguishes confidence concentration from correctness. [Official OpenRouter explanation](https://openrouter.ai/blog/insights/what-is-jev/)

Its small typed output can be useful for selecting a candidate operation, identifying a likely relevant component, ranking unresolved modules, or routing uncertain cases. It remains one interchangeable policy implementation. Building the state and action vocabulary is often the more consequential architectural work.

The advertised input pricing and free output do not establish the pasted 70–90% savings. The vendor describes latency as a range, not a universal sub-100ms guarantee. Calling a hosted model from an edge handler also does not mean its weights execute locally at that edge. These distinctions matter when estimating a complete system. [TypeSafe launch description](https://typesafe.ai/blog/introducing-system-one-models-and-jev)

There is already a relevant reported failure mode. A September 2026 preprint changes the assignment of option names to unchanged rubrics in Jev and related decision models. It reports decision degradation while all outputs remain type-correct. This is a scoped, unreproduced research report, not a universal failure claim. It makes option naming and representation robustness material evaluation questions. [Primary preprint on option-name sensitivity](https://arxiv.org/abs/2609.26758)

A selected option can be syntactically valid and semantically wrong. Describing the decision head as unable to hallucinate can obscure that difference.

## Cheap selection should complement dependable checks

Some of the pasted examples incorrectly elevate a classifier into a verifier. Conditional hook use, exact thresholds, dependency facts and syntax should use appropriate deterministic analysis where available. A learned model may identify suspicious cases or suggest an investigation. It cannot supply the same guarantee as a check whose semantics match the requirement.

Test selection is a similar case. A model can propose a relevant subset, but minimizing the subset can omit a regression. Selection should be compared with dependency-based methods, and the coverage obligations of a release remain the release owner's responsibility. A model's guess that a failure is a flake does not erase the failure or its evidence.

Visual adequacy presents another limitation: a text-only policy cannot directly inspect the rendered interface. It may use measured properties or a description produced by another observer. That observation path has its own omissions and cost. If a design task depends on visual judgment, the system needs actual visual evidence and a suitable evaluator.

Independent evaluation also does not require the most expensive possible ceremony at every step. Local checks can establish routine facts; realistic interaction tests establish broader behavior; independent review is valuable where consequential claims warrant it. The important distinction is what each check can establish.

## A plausible developmental loop

A proposed loop has two connected modes.

In exploitation, the world interprets the requirement, observes state, selects familiar operations, executes them, checks consequences and retains the result. In repertoire development, recurring obstacles or opportunities trigger alternative decompositions, new operations or new applicability rules. A capable generative participant can propose those changes; domain evidence determines which are useful.

Both modes may operate on several timescales. A local repair can happen quickly. A procedure becomes reusable after varied outcomes. A new representation or domain language may need broader comparisons. An abstract operation can also turn into a compiled implementation, while its interpretation and limits remain accessible.

The change process itself should remain replaceable. A world could use SST to explore new operations, STC to realize them, and TRACE to retain experiences and conditional lessons. This is a possible cooperation pattern, not a mandatory universal pipeline or evidence that current integrations are qualified.

There is a bootstrap problem: successful existing solutions provide material for abstraction, but an absent abstraction may prevent the first solution. The system should therefore learn from partial candidates and failures, not only compress completed code. Whether this produces useful prospective invention is a research question.

## Costs and capability measures

The relevant accounting includes task interpretation, state preparation, model inputs, tool execution, retries, evaluation, repertoire development, migration and later maintenance. A selector that costs little per call can still make the whole process more expensive if it needs many calls or causes extra repairs.

The principal outcome is useful completed work. For a frontend experiment that means correct interactions, an adequate design, integrated behavior and generalization to requirements the system did not merely memorize. Costs and user attention should be reported alongside that outcome, with failed and unfinished tasks visible.

A learned operator can be worth retaining even if it fails to compress stored code, provided it unlocks useful tasks or reduces future effort. Conversely, a compact library can worsen search by introducing too many ambiguous alternatives. Compression, selection efficiency and practical capability must be measured separately.

## Bounded research briefs

**Construction repertoire.** Under matched task and resource budgets, compare capable generative development, authored reusable operations, cheap selection over those operations, and a repertoire that can expand. Include requirements that the initial catalogue cannot satisfy. Measure completed behavior, design quality, repairs, total cost and operator attention. The result should tell us whether selection and repertoire learning improve capability rather than merely reduce one invoice category.

**State and option robustness.** Keep task meaning fixed while changing operation names, wording, order and irrelevant context. Include inadequate menus, contradictory requirements and missing state. Measure inappropriate confident actions and whether the world recognizes that further investigation is needed. This tests the interface between representation and policy.

**Prospective reuse.** Retain proposed abstractions from earlier tasks and assess them on held-out task families, including changed interaction conventions. Charge discovery and maintenance costs. Compare retrospective compression with policies that use failures and partial work to propose missing operations. The question is whether the system inherits useful construction ability.

These briefs can be handed to cheaper foraging agents or a focused STC architect. They are not prerequisites for every current product release. The macro decision is which kind of construction knowledge should be reusable across worlds; the local architect determines the smallest informative realization.

