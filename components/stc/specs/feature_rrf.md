# Reciprocal Rank Fusion (RRF) Service

## Domain Invariants
Fusion weights sum to 1.0.
Tied fusion ranks require deterministic resolution.
Reciprocal rank constant k defaults to 60.
Score values strictly non-negative.

## Persistence & Storage
SQLite FTS5 full-text index with WAL mode.
Flat vector arrays with cosine similarity metric.

## Communication Protocols
PEP 544 FusionEngine Protocol.
JSON-RPC batch query endpoint.

## Boundary & Security
Internal package memory boundary.
Isolated worktree execution boundaries.

## Failure Resilience
Zero division damping guard on empty rankings.
Timeout within 30 seconds on unbounded candidate streams.
