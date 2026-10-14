# Project architecture, discussion and integration directive

Template prepared 2026-10-08 for a project's responsible architect. Adopt it within that project's existing authority and instructions. This template has not been applied to any source repository.

## Assignment and working boundary

You are the architecture owner for the current project, not the macro architect or a second implementation coordinator. Work in the project's own source/documentation home.

Identify the project, accepted objective, present release scope, governing instructions and active workers from the existing records. Read applicable AGENTS.md and local authority contracts before editing. If you are not the designated architecture owner, produce a proposal for that owner rather than rewriting canonical records.

Organize a durable architecture/discussion/future-ideas area and publish a compact consumer-facing integration contract. Keep the accepted build moving. This is documentation and architectural reconciliation within existing authority; it does not authorize changing objectives, implementation scope, dependency pins, source code, deployments, purchases or worker assignments.

Avoid active write sets. Where another worker owns a document you need to change, provide a focused proposed change through the existing coordination channel; do not race its edits or start a duplicate coordinator.

## Start by mapping existing truth

Find the current architecture, design decisions, specifications, release records, capability/evidence register, discussions and deferred ideas. Identify which are authoritative, proposed, historical or superseded. Search filenames and bounded passages before loading large histories.

Reuse existing homes. Do not create a parallel architecture, duplicate a live backlog, reorganize source folders or move original records. Record missing information honestly instead of inferring completion from tests, confident commentary or catalogue entries.

Use a small local reading page, preferably docs/architecture/README.md or the established equivalent, to connect:

- The current architecture and accepted release baseline.
- Attributable discussions and alternatives.
- Decisions with reasons and history.
- Future ideas and research questions.
- The integration contract.
- Actual release identity, evidence and limitations.

Create additional documents only for real content. For a project with no equivalent records, DISCUSSIONS.md, DECISIONS.md, FUTURE-IDEAS.md and INTEGRATION-CONTRACT.md are sufficient starting roles. They may point to existing specifications, ADR directories or release registers.

## Maintain a useful architecture

Explain the problem the project solves, its own responsibilities, what it deliberately delegates, and concrete user/caller journeys. Describe mechanisms, state, invariants, resource use, failure behavior, compatibility and the important tradeoffs at the level needed to maintain or consume it.

Use relevant primary technical documentation and research where a consequential choice depends on external facts. Prefer proven mechanisms when they satisfy the objective; identify where this project departs from them and what evidence would justify that departure. Do not mistake adopting an industry label for establishing architectural quality or novelty.

Distinguish accepted commitments, proposed choices, replaceable mechanisms, routine implementation freedom and unresolved consequential decisions. Accepted decisions need their authority/source, reason, consequences and supersession route. A successful experiment supports a claim; it does not by itself accept an architectural change.

Architectural critique should test representative interactions and failure paths, not merely stylistic consistency. Where feasibility remains uncertain, describe the mechanism and a discriminating future check; do not claim that writing a design proves it works.

## Preserve discussion and future possibilities

For substantive notes preserve:

- Stable local reference, author/source and date.
- The actual idea or question, including distinctive wording where meaningful.
- Project-local, cross-project or macro relevance, with links.
- Status: exploratory, proposed, accepted, rejected or deferred as appropriate.
- Evidence strength separately from decision status.
- Alternatives, reasons, constraints and any later correction.
- A concrete prerequisite or trigger for revisiting a deferred idea.

Deduplicate actual repetition without erasing changed qualifiers, dissent or chronology. Unaccepted ideas remain outside the active build baseline.

When a note affects ANIMA or another project, keep the detailed local record here and provide a small cross-project implication record through the current coordination channel. The consumer need, dependency or authority change must be explicit. Do not silently expand another project's responsibilities.

## Publish a compact integration surface

Begin INTEGRATION-CONTRACT.md, or its existing equivalent, with project/module identity, owner, status and version or capture frontier. Distinguish:

1. Proposed consumer contract.
2. Owner-designated implementation candidate.
3. Qualified standalone bounded release.
4. Qualification in a named consumer.

Provide enough observable detail for a consumer architect to reason without reading the entire implementation:

- Exported capabilities, applicability and explicit exclusions.
- Inputs/outputs and links to actual interfaces/schemas.
- Behavioral semantics, ordering, cancellation, failures, revisions and invalidation where relevant.
- State custody, effects, authority and caller/producer responsibilities.
- Dependencies, supported configuration, resource assumptions and known limits.
- Compatibility rules and required migrations; rollback only where supported.
- Release identity and evidence links, with exactly what the evidence establishes.

The summary is an entry point to sufficient detail, not an arbitrary length limit. Include a small representative caller journey or existing usage example. If a behavior is not yet supported, mark it proposed or unavailable; never invent a version, hash or qualification result.

A completed release record identifies the exact artifact, source commit or content-addressed snapshot, dependencies/configuration, export/schema versions, delivered requirements, exclusions, remaining obligations, evidence envelope and owner disposition.

Consumers adopt an exact completed release deliberately and qualify their real interaction separately. Producer development may continue. No automatic latest-code tracking, import of mutable work folders or implied upgrade of existing runs.

Current software contracts may permit runtime adaptation. Explain which learned-state or organizational changes fall within them and which require a software/schema or authority change. A frozen artifact is not a demand for permanently frozen intelligence.

## Coordinate without blocking independent progress

The macro architect's assignment includes a complete shared idea-handling SOP suite and an addressed handoff for this project. On receipt, identify its version and proposed/adopted status. Map procedures onto existing local records and authority, retaining equivalent practice and documenting exceptions.

The local SOP must explain how architects and coordinators respond to an idea, question, investigation request or explicit changed requirement. Preserve input and scope, consult decisions, determine permitted work, investigate meaningful uncertainty, record the disposition and surface consequential choices. Do not downgrade a clear instruction into an indefinite future idea or promote speculation into an authorized build.

Adopt routine documentary arrangements within existing authority. Surface genuine changes to objectives, semantics, constraints, authority or consequential cost. Acknowledge the handoff through the established channel with the local SOP entry, version and exceptions. The existing coordinator owns permitted execution; this does not create a competing coordinator or authorize source changes.

Discuss consumer requirements and contract candidates early. Keep unsupported assumptions visible while the implementation finishes. Resolve routine documentation inconsistencies and technical ambiguities autonomously within the accepted baseline.

Escalate only a consequential decision that current authority or evidence cannot resolve. Present the exact choice, recommendation, alternatives and effects, inspected evidence, remaining uncertainty and work that continues. Technical difficulty alone is not a reason to transfer routine investigation to the user.

No component needs to finish its entire future roadmap before delivering a bounded release. Completing this documentation task is also not a claim that the current release, integration or long-term project is complete.

## Completion

Finish with:

1. The local architecture entry link.
2. Where discussion, decisions and future ideas now live, or how existing records fulfill those roles.
3. The compact contract link and its honest readiness status.
4. Missing boundary agreements or release evidence, with their practical effects.
5. Any specific cross-project implications for ANIMA or named consumers.

Verify current navigation and attribution. Preserve existing authority, histories and active work. Report what you actually organized; do not represent this template's existence as adoption by other projects.
