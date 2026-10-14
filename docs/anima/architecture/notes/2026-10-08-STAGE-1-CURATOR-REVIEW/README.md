# Stage 1 curator output: independent coordinator review

> Public curation note: links to records excluded from this public release were converted to plaintext historical references; the original record identities are preserved inline.

2026-10-08. **Disposition: return for focused Stage 1 reconciliation. The completion claim is not yet supported.** The entry point and preservation work are useful; rebuilding the packet is unnecessary. This review neither accepts an architecture nor starts Stage 2.

The governing assignment is the [curator prompt](../2026-10-08-CONTEXT-INTEGRATION-PROMPT.md). Review evidence is in [verification.json](verification.json), with document identities and individual message checks. Reproduce the checks from Utilities with:

```powershell
python ANIMA\architecture\notes\2026-10-08-STAGE-1-CURATOR-REVIEW\verify_stage1.py
```

The verifier writes only its evidence file. The curator's preserved material, synthesis, indexes and handoff have not been modified by this review.

## What has been independently verified

| Check | Observed result | Limit |
|---|---|---|
| Four recorded session identities | All four declared byte/line prefixes and SHA-256 values match the available archives. | Hashing secondary histories does not establish that their complete contents were reviewed or preserved. |
| Primary user preservation | All 76 substantive visible user turns match character-for-character, with correct message IDs and timestamps. Nine environment-only records are correctly outside the substantive set. | This establishes the captured primary input, not unrecorded conversations or the paused Desktop review. |
| Primary assistant preservation | The main assistant file contains 122 messages: 89 exact matches and 33 differing only by leading/trailing whitespace. | There are 171 visible assistant messages in the captured archive. Of the other 49, four appear verbatim elsewhere in ANIMA and 45 have no complete exact-text match in the inspected ANIMA Markdown. Routine acknowledgements or genuine duplicates may be excluded with an honest disposition. |
| Structured records | Integration SOURCES/DECISIONS parse at 4/5 rows; existing context SOURCES/DECISIONS-AND-CORRECTIONS parse at 28/21 rows. | Parsing does not validate authority, completeness or the claims in those rows. |
| Current authored navigation | 203 local links across 17 control/navigation documents resolve; checked heading anchors resolve. | Historical links inside verbatim text are a separate issue. This was not a browser rendering test. |
| Developmental-worlds documents | All 29 current files, including evidence notes, dossiers and reviewed-draft versions, have review-time identity records in the evidence file. | This inventory is the coordinator's observation, not retrospective evidence of the curator's reading or per-document disposition. |
| Ecosystem directory | The old directory is absent and the six original provenance files remain present. | A post-deletion check cannot reconstruct hidden entries, reparse points or the original dependency preflight. |

No substantive primary user text loss was found. The issues below concern coverage accounting, retrieval, synthesis and authority in the handoff. Exact-string absence alone is not proof that an idea's meaning was lost.

## Required reconciliation

### R1 — Remove unsupported fixed architecture and governing constraints

The [handoff](../../../context/integrations/2026-10-08/ARCHITECTURE-HANDOFF.md#2-governed-baselines-vs-architect-freedoms) labels component boundaries **“Fixed Baseline (Do Not Overturn)”**. Its evidence-gap table further says TL must be treated as **“document-scoped atoms with overlay graph indexes.”** The latter is a specific architecture choice without a supporting decision or owning contract in that handoff.

The [independent-modules source](../2026-10-08-INDEPENDENT-MODULES-AND-ARCHITECTURE-CHANNELS.md#do-not-freeze-development-by-freezing-artifacts) explicitly distinguishes the current delivery arrangement from a permanent ontology. Existing decision D-010 (historical record `../../../context/DECISIONS-AND-CORRECTIONS.jsonl`, excluded from this public release) also preserves later ownership changes and composite formation. The separate architect assignment requires confirmation of curator “fixed” labels against actual authority; the curator cannot create that authority.

Retain current owning-project responsibilities with their scope and evidence. Separate user direction, current contracts, assistant proposals and unselected options. Remove the unsupported TL prescription or label and source it as a proposal. Correct `DEC-2026-10-08-04`'s invented `SYSTEM-SANCTIONED` authority using the attributable namespace decision already present in D-013. Keep previous entries and add explicit corrections rather than silently replacing history.

### R2 — Carry the latest SOP responsibility faithfully into the handoff

User ordinal 4242, physical line 4243, asks for **entire SOPs** informed by existing practice and cheaper research. User ordinal 4273, physical line 4274, asks for prompts addressed to the appropriate sessions without making the user adapt project templates. Both are in the preserved user file (historical record `../../../context/integrations/2026-10-08/preserved/USER-SUBSTANTIVE-TURNS.md`, excluded from this public release). The assistant clarification at ordinal 4278 is preserved in independent modules and directives (historical record `../../../context/integrations/2026-10-08/preserved/INDEPENDENT-MODULES-AND-DIRECTIVES.md`, excluded from this public release).

The handoff currently reduces this to finalizing a shared template and specifying coordinator compliance tracking. Preserve the next architect's responsibility for a complete shared SOP suite, complete recipient-specific handoffs, and an addressed issuance package. Routine distribution uses an established coordinator/channel where available; the user need not compose or adapt the handoffs. Curation records this responsibility; it does not perform Stage 2 authoring or establish adoption by project owners.

Include the [research assignment](../2026-10-08-SOP-RESEARCH-PROMPT.md), [source seeds](../2026-10-08-SOP-SOURCE-SEEDS.md), expected research handoff and their actual prepared/available status. Their existence is not completed research or accepted procedure.

### R3 — Reconcile source-to-output coverage instead of claiming complete extraction

[COVERAGE-AND-REVIEW](../../../context/integrations/2026-10-08/COVERAGE-AND-REVIEW.md) and SOURCE-MAP (historical record `../../../context/integrations/2026-10-08/preserved/SOURCE-MAP.md`, excluded from this public release) claim 171 substantive assistant responses extracted. The actual main preserved file has 122. The evidence file lists every remaining message by ordinal, physical line, ID and timestamp, including the four exact routes already found elsewhere.

Review each absent message for substance. Two examples needing explicit treatment are ordinal 1017, which raises the cost of the allocation chooser, and ordinal 1345, which separates containment, ownership, access and function. Neither complete wording was found elsewhere in inspected ANIMA Markdown. Both may develop arguments found in longer replies, but similarity alone is not an attributable deduplication disposition.

Provide a small machine-readable disposition map: preserved location, exact-source document route, genuine duplicate with occurrence locators, or excluded category and reason. Routine acknowledgements need not be forced into the substantive layer. Do not use a character-length cutoff as a substitute for this review. Explain the 33 whitespace-normalized assistant excerpts and retain or restore meaningful formatting.

The integration source register contains only four session rows. Reuse the existing register where its coverage remains valid, but add current identity, version/status, exact-source route and disposition for distinct document contributions: the 29-file developmental packet, the four new documentary inputs, and explicitly linked substrate/owner documents. Distinguish original dossiers, preliminary drafts, reviewed revisions and owner-published promises. A catalogue path or hash alone is not an export contract.

### R4 — Make the synthesis attributable and preserve the wider canvas

The [new synthesis](../../../context/integrations/2026-10-08/SYNTHESIS.md) has no Markdown source links for its material claims. It presents several proposed mechanisms as imperatives and current project states as facts without their evidence frontiers. Its treatment of the eighteen-vector round is largely a namespace label; its mechanisms mostly summarize the later eight-vector round.

Build a connected synthesis with claim-level routes into exact preserved passages and existing owning records. Reuse the [idea map](../../../context/IDEA-MAP.md), source excerpts (historical record `../../../context/SOURCE-EXCERPTS.md`, excluded from this public release) and full essays. Connect the two rounds without merging their numbering. Preserve competing interpretations, changed qualifiers and unresolved choices.

In particular retain participant co-adaptation, changes to procedures/state/responsibility, worlds hosting worlds, assimilation, composites, fusion/fission, inheritance of developmental machinery, and the distinction between source location and runtime containment. These are part of the supplied ambition; they are not demonstrated capability or selected implementation. Recover other distinct arguments through the actual source map rather than substituting generic “mechanism/evidence” bullets.

The [index](../../../context/integrations/2026-10-08/INDEX.md) should route to precise arguments, not only entire preservation files. Add scoped/authored/status-bearing entries where needed and direct routes for the earlier eighteen vectors, schema + specific schema + delta, adaptation versus inheritance, the physical construction ambition and evidence/retention limits. Keep prior-model claims attributed rather than verifying them by confident paraphrase.

### R5 — Repair frontier metadata and state actual documentary readiness

The frozen primary input is **4,296 physical lines / 30,006,999 bytes**, SHA-256:

```text
9b3d813b1bb852b00dd7fb4659d248766d5d344480084372a45993bb875b1f69
```

Its final record is **ordinal 4295 / physical line 4296 at 2026-10-08T13:38:21.168Z**. The register and audit incorrectly give `13:37:08.709Z`. The user-file header already contains the correct time. Do not extend this frontier merely because the live archive has subsequently grown.

All 198 checked preservation headings label a zero-based ordinal as a “Physical Line”; the source IDs and per-message timestamps match. Adopt one explicit convention, preferably physical line = ordinal + 1, and reconcile current coverage/decision locators. Existing older source records already use that distinction.

All 76 user occurrences remain in the user file, so the duplicate map's claim of retaining only the first occurrence is inaccurate. Repeated `go 4`–`go 8` strings in the two vector rounds are different contextual instructions. Preserve both event identities and round membership; do not collapse their meaning into one command.

Add a direct coverage link and concise captured/outside-capture statement to [START-HERE](../../../START-HERE.md). Put the source frontier, exact handoff document set, proposal/evidence status and consequential gap assessment in the handoff itself. Keep the B1/B2 review paused. Distinguish historical audit limits from today's observed coverage without deleting the older audit.

The current `architecture/contracts/` and `catalogue/pins/` contain only their README files. Describe them as record homes; do not imply that qualified global contracts or consumer pins have been published. Owner-local contracts may exist, but name and identify those actually used. Replace premature “complete” / “ready to launch” claims with the reviewed Stage 1 disposition until reconciliation is checked.

### R6 — Complete or qualify the cleanup evidence

The cleanup report records the six redirect filenames/sizes and says deletion occurred. It does not show the actual hidden-entry/reparse-point checks, active-consumer disposition or old-path reading map required by the conditional cleanup assignment. The retained provenance contains original drafts, not byte-identical copies of the later redirect stubs.

A bounded current path-reference search in ANIMA, the named active programme and substrate/docs found only cleanup/policy mentions; it does not establish a workspace-wide pre-deletion check. Request existing curator preflight evidence if retained, record verified observations separately from reported actions, and explicitly map the six historical paths to their preserved originals. Preserve the archived original wording and explain its relative-link limits. If preflight evidence cannot be recovered, say so; do not fabricate a retrospective successful check. No further deletion or source reorganization is requested.

### R7 — Repair preservation wrappers without changing source wording

Two user excerpts and two assistant excerpts contain bare triple-backtick lines inside triple-backtick preservation wrappers. That allows the inner source fence to close the outer wrapper in Markdown. Use longer enclosing fences selected from the source's longest fence run, or another lossless presentation. Keep the payload, source coordinates and prior identity verifiable. This is a reading/formatting issue, not evidence of missing user characters.

## Scope and review limits

The review used the assignment, produced control documents, current structured registers, the captured primary visible messages, scoped owning/documentary records, inventories, and representative source arguments. It checked all primary user excerpt text and all excerpt payloads in the main assistant file. It did not deeply reread all 29 developmental files, exhaust secondary conversations, verify every historical biological/product claim, inspect active implementations, run project tests or reopen the paused B1/B2 archive investigation.

The finding that Stage 1 needs reconciliation follows directly from the observed count/metadata contradictions and handoff/source mismatches. Missing future research is not itself a prerequisite for completing this curation. Remaining gaps should block only the specific design decisions they actually affect.

## Ready-to-paste continuation for the existing curator

> Continue Stage 1 only, under ANIMA/architecture/notes/2026-10-08-CONTEXT-INTEGRATION-PROMPT.md. Read ANIMA/architecture/notes/2026-10-08-STAGE-1-CURATOR-REVIEW/README.md and verification.json. Treat them as review findings, not new architectural authority. Reconcile R1–R7 against the exact sources. Preserve verified user wording and prior histories; do not rebuild or overwrite the preserved corpus. Account for all primary assistant omissions with exact routes or honest dispositions, add the document coverage/identity map, link the synthesis's material claims, retain the broader developmental ambition and latest complete-SOP/addressed-handoff duty, and correct unsupported fixed/accepted labels. Fix frontier/physical-line/duplicate accounting and preservation wrappers. Make START-HERE and ARCHITECTURE-HANDOFF state the exact captured scope and remaining gaps. Recover or qualify ecosystem preflight evidence without further deletion. Update current ANIMA navigation/readiness records and link this independent review. Perform a separate source-to-output and output-to-source checking pass, report actual verification and remaining limits, then return the corrected Stage 1 packet for coordinator review. Do not execute Stage 2, author its architecture, issue directives to projects, launch workers, inspect mutable implementations or reopen the paused Desktop review.
