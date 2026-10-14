# Independent module delivery and deliberate integration

Status: current user direction and delivery policy for ANIMA. A module can deliver a usable, bounded release while explicitly deferring integrations. A release is not permission to stop before its own agreed requirements are met.

## Ownership and release scope

- Keep TL, TRACE, STC, SST, and other useful projects independently buildable and owned while that enables parallel progress.
- Finish each release against its agreed in-scope requirements. Describe the qualified capability and evidence envelope; do not imply the entire long-term vision is complete.
- Record exclusions and future obligations in the release record. For example, an initial TRACE release may omit SST integration if that integration is explicitly deferred. The exclusion does not erase a later integration obligation or the active programme’s separate acceptance requirements.
- Independent ownership now does not prohibit later integration, changed ownership, or composite formation. Record the deliberate transfer or composition, its owners, responsibilities, state/lifecycle changes, and evidence.

## Freeze identity

A release record must identify:

1. Module ID and release/candidate label; exact source repository and commit, plus an identity for uncommitted content if any. Use a content-addressed snapshot/package when the source is not a repository. Do not invent a version, commit, or hash.
2. Dependency, configuration, runtime, and build identity needed to reproduce or interpret the candidate.
3. Export contract and schema versions; observable capabilities; inputs/outputs; semantics; failure, cancellation, revision, and compatibility behavior.
4. Requirements delivered, explicit exclusions, future obligations, qualification results, evidence envelope, known limits/failures, and owner disposition.

A mutable working directory is not a frozen release. The current catalogue records source paths and selected implementation families; it does not claim frozen artifacts. Unselected releases and pins remain explicitly unresolved.

## Consumer pins and upgrades

- A consumer pins the exact release identity it selected, including relevant dependencies/configuration and interface/schema versions.
- A module update becomes a staged candidate. The consumer inspects compatibility, required state/schema migration, and evidence, then runs proportionate checks through its actual caller before deliberately advancing the pin.
- Do not auto-track `latest`, silently replace a running module, or migrate existing runs by implication. Existing runs retain their starting pins unless a recorded migration is performed.
- Record rollback only where a rollback path is actually supported and checked.
- A module’s standalone release and its integration into a particular world or consumer are separate claims. An import proves availability; an actual caller check supports the claimed interaction.

## Minimal contracts and future adaptation

Agree small, versioned export contracts early enough for independent builders to work: observable capability, inputs/outputs, semantics, failure/revision behavior, state/schema compatibility, dependencies, and evidence. These are bounded release boundaries, not a universal ontology or a promise that all future interaction is fixed. Richer context-dependent relationships, adaptation, assimilation, negotiation, and composite formation remain open substrate work and require concrete mechanisms and evidence.

## Initial status

`ANIMA/catalogue/MODULES.json` identifies source families and current status. No new ANIMA release hash, consumer pin, or integrated runtime is selected by this organization assignment. In particular, preserve the TL source family, TRACE landing, STC/SST ownership, and the broad substrate as separate identities. See the release/pin registers for explicit unresolved selections.
