# Vector 6 — Developing construction repertoires

Architecture discussion, 2026-10-06. This is the full sixth-vector treatment in the current round. It builds on [creative coverage](VECTOR-05-CREATIVE-COVERAGE.md), [developmental change](VECTOR-01-DEVELOPMENTAL-CHANGE.md), [expert individuality](VECTOR-03-EXPERT-INDIVIDUALITY.md) and the earlier [construction-language note](CONSTRUCTION-LANGUAGES.md). Recommendations remain proposals while the user reads the round. No model, API, language, assurance profile or implementation is selected here.

**My current bet:** develop the representations, executable operations and policies for using them together. Repeated work should change what the system can construct and how readily it can construct it. Cheaper selection can exploit that growing competence where the available state and operations support a useful choice.

The user's 4A proposal begins with abstract planning by a capable model, followed by more structured choices over modules, elements, styles and kinds of work. It explicitly recognizes that Jev does not generate the missing construction itself. Frontend is an example of a field with many recurring structures after broad intent is understood.

That is a promising entry point. The deeper research target is a construction language that develops through use: familiar actions become easier, important conditions become expressible, missing actions can be invented, and useful compositions can become capabilities.

The construction environment can start from existing tools and authored procedures. Its success depends on useful realized work and later transfer, rather than how much of the workflow has been described as learned.

## What is inherited when construction gets easier?

There are several different things to reuse.

A component is material for construction. A template provides a recurring arrangement. An operation changes something. A procedure organizes several operations. A policy chooses what to do as observations arrive. A domain representation makes relevant distinctions available to those choices.

All can be useful. They carry different kinds of competence.

A library of buttons, forms and panels helps instantiate familiar interfaces. A procedure for establishing a selection-and-confirmation interaction also needs to account for state, timing, failure, accessibility and the meaning of confirmation.

A workflow for researching an unknown mechanism includes observations and competing explanations. A physical skill depends on an actual body, calibration and operating conditions. Their reusable content cannot be reduced to the same list of visual components.

The common idea is a repertoire: available ways to construct, investigate or transform something, together with enough meaning to use them appropriately.

The repertoire may contain deterministic tools, parameterized code, interactive policies, model-mediated procedures, simulations or capabilities supplied by another world. It need not be one uniform instruction set.

The user wants discoveries to become inheritable computational primitives. That ambition includes making previously difficult work routine. A primitive can preserve a useful operation without preserving the entire conversation that discovered it, provided the retained representation carries what subsequent use and revision actually need.

Some capabilities remain complex or jointly maintained. Development should not force every useful method into a small stateless function.

## From a description to a conditional capability

An operation description says what an action is meant to accomplish. An executable capability also needs a way to produce and assess its effects in a particular world.

| Concern | What the construction environment needs to distinguish |
|---|---|
| Purpose | The contribution expected from the operation and the task it serves |
| Binding | The parameters, artifacts, participants and resources used by this invocation |
| Applicability | Relevant conditions, what is known about them and consequential uncertainty |
| Execution | The actual procedure or participant responsible for carrying out the operation |
| Effects | Requested changes, reported completion and observed consequences |
| Recovery | Incomplete work, partial effects and how continuation or compensation is handled |
| Reuse | Supported conditions, dependencies, versions and evidence from earlier invocations |

These concerns need not become mandatory fields in every record. A simple tool may already express most of them through its existing interface. An uncertain physical skill may need a much richer account.

A function type such as “slot to receipt” can describe inputs and outputs without establishing that the slot still exists, that it was reserved, or that the receipt corresponds to the user's latest intent.

Likewise, “insert calendar” and “establish a working booking flow” are different operations. The second encompasses behavior and conditions that the first does not provide.

Some effects are precisely checkable. Others are conditional expectations assessed through observation. A learned policy can remain useful without having a complete formal specification of its environment.

The architecture should preserve that distinction. A probabilistic expectation should not acquire the status of a guaranteed postcondition because it occupies the same record position.

The first substantive design question is therefore what a caller needs to know, observe and retain to use a capability responsibly. The answer belongs partly to the relevant domain and partly to the relationship between caller and provider.

## A repertoire and its policy change each other's problem

Consider a task, a current state representation and a set of available operations.

A selection policy chooses an operation or a short composition. Its quality depends on whether the representation exposes the relevant conditions and whether the repertoire contains a useful next move.

A larger policy cannot select an absent operation. A richer repertoire can still be difficult to search. A correct choice on inaccurate state can produce the wrong consequence.

This makes three developmental surfaces inseparable in the stronger research hypothesis:

- The representation determines which distinctions can guide work.
- The repertoire determines which actions and transformations can be attempted.
- The policy determines which attempts receive resources.

Execution feedback and assessment can revise any of them. A failed handoff can also reveal that the relationship between participants needs to change.

A new abstraction may make several tasks shorter to express and easier to solve. It can also introduce ambiguous alternatives, costly applicability checks or too many parameters.

Even if a general base language could express the same computation already, a useful primitive can make it accessible within an actual search and execution budget. Its benefit concerns practical accessibility as well as expressive possibility.

This is why the repertoire should develop with guidance for using it. Learning a tool without learning when it applies can increase rather than reduce future effort.

The guidance need not live in one model. It can reside in explicit rules, retrieved cases, an inexpensive policy, specialized models or learned relationships among worlds.

## Two meanings of cheap choice

Some choices are cheap because the work is already understood and the remaining alternatives are well represented. A deterministic rule, dependency analysis or small model may be sufficient.

Other choices appear cheap because the representation has omitted the difficult part. Selecting a component can be easy while establishing the intended interaction remains unresolved.

The user's large-model/small-selector arrangement can help when it identifies genuinely reusable decisions. It should not assume that every step after planning has low reasoning demand.

An abstract decision may have a simple answer supplied by a rule. A seemingly local edit may require substantial investigation of state and timing. Model size should follow what the computation can resolve.

“System 1” and “System 2” are useful shorthand in this discussion for different kinds of work. They do not establish exclusive abilities or biological identities for particular models.

The selector's input preparation is also part of the work. Someone must construct the menu, observe state, represent uncertainty and interpret the result. If a frontier model has to do that from scratch before every small choice, the apparent saving may mostly move expenditure upstream.

A recurring decision becomes more economical when the environment can prepare relevant state and execute the selected operation through reusable machinery. That is a stronger contribution than asking a cheaper model the same prose question.

## Typed choices need an adequate decision setting

A decision model can return a member of the supplied menu, a score or a yes/no-style result. A valid output type says that the answer fits the interface. It does not establish that the chosen action is appropriate.

The [choice-evidence note](VECTOR-06-CHOICE-EVIDENCE.md) examines Jev's official descriptions and primary studies relevant to representation and routing. Jev remains one possible interchangeable policy implementation. The supplied weaker-model claims about large savings, instantaneous checks and free verification are not treated as established results.

An inspected study demonstrates the distinction: reassociating option names with explicit definitions changed decisions even though outputs remained type-valid. Its constructed name conflicts do not estimate ordinary frontend error rates. [Sun et al., v2](https://arxiv.org/html/2609.26758v2)

Several failure modes deserve separate attention.

The menu may omit the required move. Its options may overlap or have misleading names. The current state may be stale. The task interpretation may omit a consequential requirement. The classifier can also make a wrong choice even when those inputs are adequate.

Adding an “investigate” or “none fits” option can provide an escape. The model must still recognize when to select it. An extra label is not a guarantee of coverage or calibrated abstention.

A concentrated choice distribution can coexist with a confidently wrong decision. Confidence can help allocate investigation when assessed for that use, but it is not independent evidence that the action will have the intended effect.

Jev's current documented Choice confidence is calculated from the selected option's probability relative to a uniform baseline. It summarizes the model's answer rather than checking its consequence. [TypeSafe confidence documentation](https://docs.typesafe.ai/confidence)

Robustness should include equivalent names, paraphrased descriptions, reordered options and irrelevant context. Those changes should not materially change the intended operation. If they do affect selection, that sensitivity belongs in the evidence rather than being dismissed because the output remained type-valid.

This is an interface between representation and action, not merely a model-ranking exercise.

## Familiar operations still need observation and execution

A selector can recommend a test, an edit or a capability invocation. It cannot make those consequences happen by returning the option name.

The executing participant needs the relevant artifacts, bindings and operational scope. Observations should be associated with the invocation and conditions that produced them.

A reported success can mean several things: a request was accepted, a tool finished, a candidate was produced, a check passed or the desired behavior was observed. Those meanings should remain distinct.

The separation matters during partial failure. A code edit might be complete while its integration remains broken. A request can time out after an external effect occurred. A physical action can change the specimen without yielding a trustworthy measurement.

Retrying the same label can repeat an effect or destroy the conditions needed to diagnose it. Appropriate continuation depends on actual state and the domain's recovery semantics.

The world's repertoire can include observation and recovery operations. They are part of competence, not overhead that disappears from its cost.

Routine invocation can proceed within standing delegation. The particular project or domain retains its governing constraints and authority. This essay does not introduce a human approval ceremony for every operation.

## Composition can create behavior no individual operation establishes

A sequence of individually useful operations can fail through their interaction.

Two edits may both change the same state. A layout change can interfere with focus behavior. A test can alter the condition it was meant to observe. An observation can become obsolete before a later action uses it.

In a simple deterministic discussion model, suppose operation \(a\) establishes condition \(Q_a\), and operation \(b\) requires \(P_b\). The implication

\[
Q_a \Rightarrow P_b
\]

is one useful composition question.

It is not a complete guarantee. The first operation may have conditional effects, the environment may change between them, and another participant may modify shared state. Unrepresented conditions remain outside the argument.

A construction system therefore needs ways to express timing, shared state, dependencies and uncertain applicability when those affect outcomes. Local checks can cover some of them. Other relationships need joint investigation.

Sometimes an additional coordinating operation is enough. Sometimes the two procedures must acquire shared state or become one conditional policy. Their useful boundary can change.

A composite can be more than a cached sequence. It can decide what to observe next, revise a branch and preserve an unfinished obligation while responding to new information.

That connects this vector to the substrate ambition. Useful cooperation can change actual representation, state custody and procedure, rather than only route a message between fixed components.

## A hypothetical frontend development episode

Consider a room-booking flow. The user wants keyboard access, changing availability, conflict recovery and clear confirmation. This is an illustrative construction task, not a report about an implemented product.

The initial repertoire contains forms, calendars, validation routines, selection controls and an authored submission procedure. It constructs a plausible interface.

A person selects one room, changes to another, and receives an earlier availability response afterward. That response replaces the availability associated with the newer selection. A separate optimistic confirmation also remains visible after a server conflict.

Adding another visual element does not resolve the behavior. The construction world needs to observe the sequence and investigate its state model.

Several candidate explanations remain possible: the wrong routine was selected, request identity is missing, confirmation semantics are wrong, the server contract changed, or the evaluator never examined concurrent responses.

The investigation identifies that the existing representation conflates selected intent, observed availability and acknowledged reservation. It proposes those as separate states, associates responses with the requests that produced them, and preserves the draft while handling a conflict.

The revised procedure also accounts for focus and announcements when recovery changes the interface. Its success concerns the actual journey under examined conditions.

This could become a conditional capability: establish a selection-and-confirmation interaction with asynchronous observations and conflict recovery. It would retain dependencies and limits.

For example, applicability might exclude offline commitments, collaborative editing or a service with different reservation semantics. Later tasks may justify specialization or a larger capability. The operation should not acquire those conditions by implication.

The learned contribution is not merely a code fragment. It is a state distinction, a construction procedure, evidence about its use and guidance for recognizing related demands.

A later inventory or configuration task might benefit from the same distinction between intent, observation and acknowledgement. That transfer still needs assessment in the new domain.

If the operation cannot be reused economically, retaining the lesson in ordinary text memory may be enough. A maintained executable abstraction should earn its place through useful future work or a justified capability gain.

## Failure should help identify what needs to develop

The construction loop should preserve several explanations instead of automatically blaming the selector.

| Diagnosis to investigate | A potentially discriminating intervention |
|---|---|
| A suitable operation existed but was not selected | Supply that operation while preserving the original task and state |
| Relevant state was missing or stale | Provide the missing observation and examine whether the choice changes |
| The repertoire lacked a useful move | Provide a suitable candidate operation and assess what it enables |
| The task was interpreted incorrectly | Recover the sourced requirement and compare consequences |
| The evaluator missed a relevant condition | Add an appropriate case or observation without silently changing the objective |
| Execution or a dependency failed | Examine the actual invocation, effects and environment |
| Participants interpreted the exchange differently | Compare meanings, bindings and observations at the relationship boundary |

These interventions diagnose mechanisms. Success after receiving a decisive missing input does not establish autonomous discovery of it.

Several causes can coexist. The booking example may require new state, a revised operation and a better evaluation case. A simple classifier retraining campaign would not address all three.

The system should retain unresolved causes when evidence cannot separate them. “Flake,” “bad model” or “incomplete menu” should not erase the observed failure.

Some failures expose an opportunity for an investigation operation. A procedure that reliably isolates stale observations can itself become reusable.

The useful learning signal is richer than pass/fail. It can concern a prediction, an applicability condition, a representation, an effect, an evaluator or a handoff. The responsible owner determines which proposed revision is warranted.

Development need not wait for a failure. New requirements, narrow applicability evidence or a deliberately informative probe can justify examining a method before the current workflow breaks. The same distinction between investigation, realization and assessment applies.

## Acquisition can start from existing primitives

The user explicitly prefers starting with useful machinery and evolving it. Construction repertoires can begin with existing tools, authored procedures, domain conventions and working code.

Wrapping an existing capability can make it callable and observable. That does not automatically infer its semantics or assess its supported conditions.

Retrospective abstraction can identify repeated structure in successful programs or workflows. It can propose a parameterized operation or a reusable composition.

The earlier podcast's traversal example illustrates the attraction. Summing values, summing squares and counting positive values share traversal and accumulation. A suitable higher-level operation can make future tasks cheaper to formulate.

A more general aggregate operation also introduces choices about transformation, combination and initial state. Generality can increase search difficulty even while reducing description length.

The [library-evidence note](VECTOR-06-LIBRARY-EVIDENCE.md) examines primary systems that learn symbolic abstractions, compress program libraries or retain executable skills. Their observed capabilities have specific task and evaluation envelopes.

DreamCoder supplies a bounded precedent for co-development: its inspected 2020 manuscript learns symbolic abstractions and search guidance, with held-out task-solving evaluations. [Ellis et al., v1](https://arxiv.org/abs/2006.08381v1)

Stitch addresses a different endpoint: it learns abstractions that compress supplied programs, including already-written held-out programs. That acquisition result leaves prospective task solving to be assessed. [Bowers et al., POPL 2023](https://mlb2251.github.io/stitch.pdf)

The bootstrap problem remains important. A system that abstracts only complete solutions may lack the very primitive needed to solve the first demanding case.

Partial programs, repeated obstacles, failed hypotheses, external methods and deliberately informative tasks can provide material for prospective invention. A proposal formed from them still needs realization and assessment.

The stronger research target is acquiring an operation because it resolves an anticipated difficulty, then establishing its usefulness through later work. An appealing name and a plausible implementation are intermediate artifacts.

## An economical library can still be a poor reasoning language

Compression is evidence of shared structure. It is not sufficient evidence of improved construction.

An abstraction can shorten stored programs while making it harder to choose the right operation. Several nearly equivalent operators can multiply search paths. A tiny interface can conceal expensive reconstruction or uncertain preconditions.

Conversely, a comparatively bulky procedure can unlock a useful class of work. Its description length may increase while total task effort decreases.

A library's practical value therefore depends on tasks, guidance, execution and applicability. The most general abstraction is not automatically the most useful one.

Formal representations can help when their meanings and transformations are known. Equality saturation provides a specific precedent: egg retains equivalent expressions under supplied rewrites and extracts a represented term according to a cost function. Its conditional rewrites use analysis facts to determine applicability. I inspected the authors' v3 manuscript, including these mechanisms. [Willsey et al., POPL 2021; inspected manuscript v3](https://arxiv.org/pdf/2004.03082v3)

This is not a general mechanism for equating competing scientific explanations or merging unrelated workflows. A rewrite's equivalence depends on the modeled semantics and conditions. A chosen cost function also need not represent complete construction value.

The architectural inference is to keep alternatives and their meanings available where doing so improves the work. A domain can use formal rewriting, candidate procedures, model-guided generation or several representations. No universal internal language is selected here.

## Cheap guidance can itself be learned

Once the repertoire contains useful operations and the representation exposes relevant conditions, repeated experience can improve how they are selected.

Learning might change an explicit rule, retrieval policy, applicability model, router or model parameters where accessible. These are different mechanisms with different evidence needs.

A frozen generative model can use a revised external repertoire and state representation. That changes the system's effective construction ability without establishing internal model learning.

Training or adapting a model to a schema is a further hypothesis. It might make common meanings easier to recognize and reduce repeated explanation. It also brings data preparation, updating and drift costs.

A stable vocabulary can become familiar to a policy. A changed operation can make the policy's earlier guidance wrong. The repertoire and its selection machinery need enough version awareness to respond.

The selector can be cheaper because much of the useful computation has already been embodied in representations and operations. That is amortized competence, not evidence that arbitrary reasoning has become a sequence of easy categorical answers.

The outcome to assess is whether the guidance improves construction under comparable conditions. Routing more requests to a cheaper model is insufficient if repairs and omissions increase.

## Development changes more than the number of operators

Several transitions deserve support.

A new operation can introduce a missing method. Specialization can narrow its applicability and improve its reliability. Generalization can make a recurring structure usable across more tasks.

Two procedures can become a joint policy with shared state. A repeated relationship can acquire a translation or diagnostic routine. A mature capability can be compiled into a more economical implementation.

Retirement can remove an operation from ordinary selection while preserving consequential evidence about earlier use. Useful alternatives can remain available through bounded routes without all becoming active choices.

An operation family, its particular executable versions and its invocations should remain distinguishable. Earlier results refer to the meanings, dependencies and conditions under which they occurred.

A renamed label is not necessarily a semantic change. An unchanged label can hide one. Compatibility needs an account of meaning and actual consumer behavior, rather than only a matching signature.

Replacement also affects ongoing work. Some invocations should finish on their original version; others may support explicit continuation. An unresolved effect needs continuing custody if procedures are fused, split or retired.

These are lifecycle questions for the relevant world. They do not require one central operator registry or a universal migration ritual.

## Plastic interfaces still need dependable execution meaning

The user wants integration beyond permanently fixed APIs. That ambition is compatible with temporary dependable bindings.

A caller must know enough about the capability it is invoking to interpret its result. Participants can learn a richer exchange, revise the operation's boundaries or coordinate changes to representation and execution.

A stable minimal mechanism can identify participants, versions, invocation state and resources. Domain meaning can remain local and revisable.

For example, two experts may initially exchange a final model and a suggested controller. Later they may maintain a joint estimate, choose informative actions together and expose an investigation capability. The original report handoff becomes an internal interaction.

This is a change in shared machinery and responsibility, not simply an adapter wrapping the same exchange. Its benefits need evidence.

Evolution-friendly machinery should permit such revisions without making every new idea require a rewrite of unrelated worlds. Genuine semantic change may still require migration, revalidation or a new relationship.

A promise of limitless compatibility would hide that work. The useful design target is local change where possible and explicit coordinated change where necessary.

## What can move into a shared substrate?

A repeatedly useful operation can become a common primitive when its shared meaning is sufficiently understood.

The booking example suggests distinctions between intent, observation and acknowledged effect. Several domains may benefit from associating observations with their originating conditions and identifying obsolete information.

A physical experiment also needs those distinctions. Its execution semantics remain different: discarding an obsolete callback does not undo a physical intervention, and a command acknowledgement does not establish that an apparatus has settled.

The transferable mechanism might handle observation identity or maintain competing explanations. Physical meaning, calibration and operational authority remain with the physical world.

Similarly, a frontend layout operator does not transfer automatically to Blender or Unreal because each has visible objects. A shared construction idea may require domain-specific operations and assessment.

Shared primitives should reduce repeated work for actual callers. Their extraction can preserve domain-specific specializations and multiple internal representations.

A computation may eventually be implemented through a tool, runtime feature or specialized hardware. The [physical-construction vector](VECTOR-04-PHYSICAL-CONSTRUCTION.md) discusses that broader path. Adoption at a lower layer should retain enough semantics and evidence to revise it when conditions change.

The substantive ambition is cumulative construction capability. Repeatedly useful computation becomes easier to access while unfamiliar demands can still change the repertoire.

## The lifetime cost must include discovery

A useful operator can cost more to discover than it saves on the first task. That can be rational if later tasks benefit.

For an illustrative fixed task family, use one declared cost measure and comparable successful outcomes. A simple break-even condition is

\[
N(c_{\text{baseline}}-c_{\text{reuse}})
>
\Delta c_{\text{acquisition}}+
\Delta c_{\text{assessment}}+
\Delta c_{\text{maintenance}}.
\]

Here \(N\) is the number of relevant later uses. The per-use costs include preparation, selection, execution, checking and expected repair under the comparison's conditions. Each \(\Delta c\) is the reused arrangement's cost minus the baseline's corresponding cost outside those per-use amounts: acquisition, one-time assessment, or maintenance over the declared horizon. Acquisition includes unsuccessful discovery attempts and the baseline's expert authoring.

This is an accounting illustration, not an assumption that future uses are known or that all benefits fit one scalar.

Task differences, dependency changes, migrations and policy updates can alter the quantities. Some operators never reach break-even. An operation can also be worthwhile because it enables valuable work the baseline cannot accomplish, even without an efficiency gain.

Report quality, capability, expenditure, elapsed time and human attention where they matter. A reduction in generated tokens should not conceal increased engineering, evaluator or maintenance effort.

Authored tools also have acquisition costs. Learned tools should not be charged for development while the baseline's expert authoring is treated as free. Nor should discovery work disappear because it ran asynchronously.

The comparison is what the retained capability buys across a declared experience horizon.

## The simpler alternative is already powerful

A capable baseline can use authored tools, deterministic checks, persistent text procedures, failure records, source access and a strong generative model.

It should be able to inspect runtime behavior, invent a tool, revise its approach and use cheaper methods for familiar decisions. Depriving it of those capabilities would make the comparison artificial.

The learned repertoire earns a stronger claim when explicit retained structure makes later substantial work more achievable or less costly than that arrangement.

A fixed executable repertoire is another useful comparator. Adding cheap selection tests policy value. Allowing the repertoire to expand tests a different claim. Adding model adaptation or developing relationships tests further mechanisms.

A rich schema can also become overhead. Many one-use routines need little more than an attributable artifact and a scoped outcome record. Maintained status should follow useful reuse, consequence or an unresolved need.

Too many operations can make every choice harder. Consolidation, specialization and retirement are part of repertoire development.

The existing STC learning and construction direction provides useful entry points. This essay does not claim its current runtime already learns the proposed repertoire or require current delivery to wait for a universal substrate.

## What would make a capability comparison informative?

Use related tasks across time, with both familiar demands and changed requirements.

Some should fit the initial repertoire. Others should require a new state distinction, composition, investigation move or operation. Include misleading reusable procedures and routine tasks where direct construction may be cheaper.

Compare a capable generative/text-memory baseline, authored executable operations, cheap selection over a fixed repertoire and an expandable repertoire. Separate guidance learning from changes in the available operations and representations where feasible.

Changed names and reordered menus test representation robustness. Missing observations and inadequate options test recognition of limitations. Realistic interaction sequences test whether constructed behavior survives conditions that static rendering misses.

Record actual completed work, unfinished and failed tasks, recovery effort, applicability errors, integration behavior and relevant design quality. A passing local test is one kind of evidence, not completion of the whole journey.

Later tasks should test reuse on demands that were not supplied during abstraction discovery. Changes in domain conventions or dependencies can reveal whether inheritance preserved useful meaning or merely copied a successful artifact.

Charge repertoire acquisition, tooling, evaluation, retrieval, repairs, tuning, translation, migration and maintenance. Compare both resource-bounded outcomes and resources needed for a chosen outcome where feasible.

Diagnostic interventions can reveal which bottleneck mattered. Report them separately from end-to-end autonomous adaptation.

Neither a curated benchmark nor several attractive demonstrations establishes that the system can construct arbitrary products or dominate a field. They can establish narrower mechanisms worth developing further.

No experiment is launched here. These are discriminating questions for the STC architect, domain construction worlds and bounded foragers.

## What would be the deeper advance?

There is substantial prior art in libraries, program synthesis, learned skills, model routing and adaptive workflows. A selector attached to a component catalogue is unlikely to be the breakthrough the user is seeking.

Co-learning libraries and search guidance already appears in the inspected evidence. The proposed ANIMA extension concerns conditional capabilities across interacting worlds: an integration can develop new state, shared control, different boundaries or a new investigation method, then carry those changes into further work. Whether that broader organization can develop cumulatively remains an open hypothesis.

The stronger hypothesis is that experience changes the system's effective construction language and its ability to use that language. New distinctions, methods and forms of cooperation become available; later work gains from them.

Its first evidence could be modest and concrete: a previously difficult interaction becomes expressible, a recurring diagnostic becomes reliable, or a learned conditional method transfers to a changed demand.

Compounding requires more. The system should retain advantages after consolidation, discover further useful operations and avoid accumulating abstractions that consume more than they contribute.

This is compatible with human architecture guiding important choices. It does not require recursive self-improvement machinery before the first useful developmental result.

The test is whether continued interaction produces increasingly capable construction organization under an honest resource account. More stored procedures, more agents or more autonomous changes are insufficient by themselves.

## What I would carry into the next design stage

I propose five principles for later consideration.

1. **Reuse conditional capability.** Retain enough execution meaning, applicability, observations and recovery behavior for useful invocation and revision.
2. **Develop state, operations and guidance together.** Failure can expose an inadequate representation or repertoire as well as a wrong choice.
3. **Include investigation and repertoire escape.** Existing operations can be exploited while unfamiliar demands motivate new methods or formulations.
4. **Preserve semantics and custody through change.** Versions, dependencies, outcomes and ongoing effects remain intelligible as capabilities specialize, combine or retire.
5. **Judge cumulative construction value.** Assess substantial completed work and prospective reuse against capable alternatives, including acquisition and maintenance costs.

These proposals fit the [ANIMA responsibility map](../../RESPONSIBILITIES.md). STC is the first construction-world implementation; local worlds retain execution meaning and assessment. SST can supply bounded search over candidate methods without owning the domain verdict. TRACE can retain granted episodes, interpretations and conditional lessons; TL retains its attributable source responsibilities. The broad substrate accommodates cooperation, lifecycle and structural change.

The first commitment I would seek later is the joint development of conditional operations, usable representations and selection methods. The operator language, schema format, model mix, acquisition algorithm and runtime topology remain choices to investigate.

Vector 7 can then examine programme search: how construction alternatives relate to dependencies, shared resources and observed execution across a much larger body of work.

## Evidence and review scope

Two specialist agents prepared the separate library and choice notes. A third agent reviewed this essay, both complete notes, selected Vector 5 continuity passages and the current responsibility map. That review identified asymmetric acquisition accounting and an overly categorical requirement to observe between actions; both were corrected. The root architect also spot-checked selected primary passages in DreamCoder, Stitch, Voyager, the option-name study and current TypeSafe documentation, and inspected egg's v3 mechanisms. This is documentary analysis, not empirical replication or a systematic survey.

The notes identify inspected revisions and access limits. No API calls, experiments, model training, runtime changes, private-corpus access or implementation qualification occurred. The canonical context packet and project commitments remain unchanged. These proposals are ready for discussion; moving through the vector round does not adopt them.
