# Authentication Gateway Service

## Domain Invariants
Must enforce token expiration on every API request.
Account balance must never drop below zero.

## Persistence & Storage
SQLite session tables with WAL mode.
Content-addressed token hashing.

## Communication Protocols
PEP 544 AuthGatewayProtocol interface.
HTTP JSON-RPC endpoint handlers.

## Boundary & Security
PII redaction enabled.
Isolated worktree execution boundaries.

## Failure Resilience
Retry with exponential backoff on network failures.
