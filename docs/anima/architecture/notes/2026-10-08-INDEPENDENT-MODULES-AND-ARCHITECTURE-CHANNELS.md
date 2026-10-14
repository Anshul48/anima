# Independent modules, compact contracts and architecture channels

2026-10-08. The independent-development and release-integration direction comes from the user. The documentation layout and owner directive below are proposals for adopting that direction. This pass has not modified active source repositories, qualified releases or advanced consumer pins.

Read with the current [module delivery policy](../MODULE-DELIVERY.md) and [responsibility map](../RESPONSIBILITIES.md). The [project-owner directive](../templates/MODULE-ARCHITECTURE-DIRECTIVE.md) provides a complete assignment for each local architect.

## Integrate completed releases while their producers keep developing

The user reports that substrate, STC, SST and other projects have independent work in progress. ANIMA should not turn their changing implementations into one unfinished dependency graph.

Finish each agreed, bounded release at its own home. Publish its observable contract, exact artifact identity and scoped qualification evidence. A consumer then deliberately adopts that release and checks the interaction through its actual caller. The producer can continue developing the next version while consumers use the previous one.

“Finished” refers to the chosen release scope, not the end of a project's ambitions. Waiting until every component is permanently complete would defeat parallel development. Conversely, an attractive current working tree is not a usable release merely because integration needs it.

The path is:

**Local architecture and development → completed bounded release → compact contract and evidence → deliberate consumer pin → actual integration checks.**

This is the practical form of the user's Kubernetes/PyTorch analogy: the consumer reasons from a useful abstraction boundary and opens the implementation when a concrete question demands it. The analogy is about reducing context load; it does not establish that any of our modules have those products' maturity.

## What makes the context load collapse

A consumer needs a short, sufficient account of:

- What capability it can invoke and under which conditions.
- Input/output semantics, relevant schemas, ordering, revision, failure and cancellation behavior.
- State custody, permitted effects and responsibilities retained by the producer or caller.
- Compatibility, resources, required dependencies and meaningful limits.
- Exact release identity and evidence for the claimed behavior.

The consumer should not need the producer's full design history or the reasoning behind every implementation choice. It still needs the assumptions that can affect composition. Hiding those assumptions compresses documentation by transferring uncertainty to the caller.

Keep the summary short by linking detail rather than imposing an arbitrary token ceiling. A compact front page with targeted deeper sections is preferable to either millions of implementation lines or a vague list of API names.

Old evidence remains scoped to its tested artifact and workload. The dated source catalogue locates projects; it does not announce their current readiness. A reusable integration packet must distinguish a contract proposal, an owner-designated candidate, a completed standalone release and qualification in a particular consumer.

## Agree contracts early; adopt implementations when ready

Independent work still needs early boundary discussion. Macro architects can publish consumer requirements and inspect owners' contract candidates while implementation proceeds. This prevents finishing incompatible components and only discovering the mismatch at integration.

For an unresolved interaction, record the caller's needed behavior, the producer's proposed promise, ownership and the open disagreement. Do not promote a draft to a supported capability or prescribe hidden changes in another team's backlog.

Local architects own module design and maintain their contracts. Integration architects own the agreed composition and its consumer evidence. ANIMA records cross-project implications and links to the source of truth. An existing programme retains its governing authority.

A request for a new capability is a scoped proposal to the owner. A ready release is a stable artifact. Adoption is a separate consumer decision. A subsequent upgrade repeats compatibility, state-migration and actual-caller checks, preserving previous run identities.

No integration pass should copy mutable sources into ANIMA, depend on unpinned HEAD, start a second builder on an active write set, or treat source paths as releases.

## Architecture discussions belong with the project

Use the same roles for records across projects, allowing owners to map them onto existing folders:

| Record | Purpose and authority |
|---|---|
| Architecture entry | Current local design, responsibilities, accepted baseline and reading routes. |
| Discussion notes | Attributable questions, arguments, alternatives and exploratory proposals. Inclusion is not acceptance. |
| Decisions | Choices accepted by the responsible authority within its scope, with reasons, consequences and supersession history. |
| Future ideas | Unaccepted possibilities, use cases, evidence questions, prerequisites and triggers for reconsideration. |
| Integration contract | Observable promises or clearly labeled proposals for consumers; links to versioned details and release evidence. |
| Release record | Exact artifact identity, scope, exclusions, qualification, limits and supported upgrade behavior. |

The recommended starting home is docs/architecture/, with links to existing ADRs, contracts or release records where those already live. Do not relocate established records or generate a second canonical architecture.

For a project without an equivalent structure, start with:

    docs/architecture/
      README.md                  current design and reading routes
      DISCUSSIONS.md             dated notes or links to substantive essays
      DECISIONS.md               accepted/proposed choices and histories
      FUTURE-IDEAS.md             possibilities, evidence questions and triggers
      INTEGRATION-CONTRACT.md     consumer summary and routes to details

These are roles, not a mandate to create empty files. Split discussion notes or decisions into directories when actual content warrants it. Reuse existing release, specification and evidence locations. The core design itself may already be elsewhere; the entry page should point to it.

## Route ideas without making everything macro architecture

Keep raw user wording, authorship, source location, status and reasons. One idea may have several relevant homes.

- A local implementation or domain hypothesis stays with its project.
- A cross-project issue gets a local source record and an ANIMA link describing the implication.
- A change to world hosting, responsibilities or a common boundary is a macro proposal.
- A distant possibility remains exploratory until a concrete trigger makes it relevant.

Future ideas are not execution directives. Accepted choices are not immutable: revision preserves the previous choice and explains what changed. A later assistant should be able to tell whether a note is an ambition, a proposed mechanism, a verified fact, an accepted decision or a release promise.

The intake standard should be shared in meaning rather than forcing every domain into the same schema. For example, a physical specimen's calibration uncertainty and an SST search contract's evaluator responsibility need different detail.

## Do not freeze development by freezing artifacts

A pinned software release identifies what machinery the run uses. It does not prohibit runtime learning, evolving relationship state or organizational development permitted by that machinery.

Separate software/schema upgrades from learned state changes and from changes to authority or responsibility. Some adaptations are already legal operations under a stable contract; others require a new contract or release. The architecture must say which is which.

As stronger assimilation or composite formation becomes real, the owners can deliberately change responsibility, custody and release boundaries. Today's independent repositories are a delivery arrangement, not a permanent ontology.

## Adopt the standard through the owners

The accompanying directive is ready to give to each project architect. It asks the owner to map and organize its own records, publish a compact integration surface and route future ideas while preserving active execution.

Do not launch those sessions or edit their repositories from this macro prompt-preparation pass. The two current assignments remain curation followed by a proposed macro architecture. Their outputs can recommend local adoption and identify required contracts without commandeering current projects.
