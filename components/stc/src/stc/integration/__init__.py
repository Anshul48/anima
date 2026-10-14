"""STC integration membrane: projections between STC and SST (P01 defines).

LAYOUT (owned by P01; P02-P04 extend this package sequentially per D12)::

    stc/integration/
        __init__.py   -- this LAYOUT note + re-exported membrane API
        adapters.py   -- disposition tables + AdapterContext/Budgets +
                         task_bundle_to_packet / task_packet_to_bundle /
                         receipt_to_score / proposal_to_filetargets
        identity.py   -- content-based candidate identity (F3a-c) +
                         shared IntegrationError base
        memory.py     -- P02: FileBackedMemory (TraceMemoryProtocol over the
                         versioned memory/ corpus); imports only STC core,
                         protocols, and the corpus docs
        harness_worker.py -- P03: HarnessWorker (WorkerProtocol over CLI
                         harnesses) + harness_worker_fn factory +
                         quarantine-owning wrapper + SpendLedger; native
                         subprocess shapes + pinned prompt-kit mock path
        cli_gateway.py  -- P03: CLIModelGateway/CLIGatewayBackend (CLI-backed
                         model channel, D10/BT-04); wraps the worker core
        dialectic_runner.py -- P04: STCCustodyWrapper (composition-based
                         substrate custody) + DialecticRunner (search +
                         champion veto + synthesis receipts + loss ledger +
                         merge + mutmut-once + judiciary audit) +
                         NoChampionResult/ChampionResult schemas
        dossier.py    -- P05: dossier assembly (cli.py-lazy import; full + partial)

Import direction is one-way: ``adapters`` -> ``identity`` (the forward
projection wires ``snapshot_hash`` to ``candidate_identity``); ``identity``
imports nothing else from this package. Both modules import the frozen
STC schemas and the read-only SST contracts only. No runner, worker,
or CLI code lives here (P01 non-goals; P02 adds the file-backed
memory shim only; P03 adds the CLI-harness worker + CLI gateway
backend, which import orchestrator/dispatch, worktree/manager, and
the pinned prompt-kit tree only; P04 adds the dialectic runner,
which imports the SST controller/custody/store read-only plus the
P01 membrane, P02 memory, substrate runner, and judiciary).
"""

from stc.integration.adapters import (
    DEFERRED_SNIPPET_PREFIX,
    EVIDENCE_CAUSATION,
    EVIDENCE_EPOCH,
    EVIDENCE_INHIBITORS,
    EVIDENCE_SPEC,
    EVIDENCE_TARGET_LOSS,
    HARD_GATE_KEYS,
    KNOWN_OPS,
    REQUIRED_EVIDENCE_KEYS,
    TAG_BUNDLE,
    TAG_MEMBRANE,
    AdapterContext,
    Budgets,
    RunBindingError,
    UndisposedFieldError,
    proposal_to_filetargets,
    receipt_to_score,
    task_bundle_to_packet,
    task_packet_to_bundle,
)
from stc.integration.identity import (
    FORMULA_VERSION,
    UNTRACKED_SUFFIXES,
    IdentityError,
    IntegrationError,
    candidate_identity,
    compose_identity_map,
    digest_record,
    repo_identity_record,
)

__all__ = [
    "DEFERRED_SNIPPET_PREFIX",
    "EVIDENCE_CAUSATION",
    "EVIDENCE_EPOCH",
    "EVIDENCE_INHIBITORS",
    "EVIDENCE_SPEC",
    "EVIDENCE_TARGET_LOSS",
    "FORMULA_VERSION",
    "HARD_GATE_KEYS",
    "KNOWN_OPS",
    "REQUIRED_EVIDENCE_KEYS",
    "TAG_BUNDLE",
    "TAG_MEMBRANE",
    "UNTRACKED_SUFFIXES",
    "AdapterContext",
    "Budgets",
    "IdentityError",
    "IntegrationError",
    "RunBindingError",
    "UndisposedFieldError",
    "candidate_identity",
    "compose_identity_map",
    "digest_record",
    "proposal_to_filetargets",
    "receipt_to_score",
    "repo_identity_record",
    "task_bundle_to_packet",
    "task_packet_to_bundle",
]
