# Boundary contracts

This directory holds small, versioned export contracts when an owner and consumer need them. A contract records the capability, input/output and state semantics, failure/revision behavior, compatibility and migration expectations, dependencies, and evidence envelope. Keep a contract tied to a specific owner and version.

No universal API or shared ontology is adopted here. The future substrate may support context-dependent or learned relationships, but changes to those relationships need observable semantics, ownership, state/lifecycle rules, and evidence. Until a real contract has an owner and consumer, keep it in the relevant programme or project record rather than creating an empty schema.
