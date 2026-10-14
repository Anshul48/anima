# Entorhinal-to-Reflex Transport Threat Model

## 1. Security Boundary Statement
The local transport between Entorhinal (Provider) and Reflex (Consumer) is an untrusted security boundary. It must not be treated as a trusted convenience simply because it operates over local IPC/loopback.

## 2. Threat Vectors and Attack Surface
- **Local Attack Surface**: A malicious local process impersonating Entorhinal or intercepting Reflex traffic.
- **Expected Peer Identity**: The transport must authenticate the peer's process identity or bind to a strictly permission-controlled local socket/pipe.
- **Downgrade/Replay**: Attackers sending stale/revoked context or forcing v1 fallback.
- **Over-disclosure**: Entorhinal granting capabilities beyond requested scopes.

## 3. Transport Decision
- **Mechanism**: Local Domain Socket (Unix/Linux/macOS) or Named Pipe (Windows) with explicit DACL/permissions.
- **Authentication**: Mutual verification of Process ID and User SID. No implicit trust.
- **Fallback**: Loopback TCP is prohibited unless bound strictly to an authenticated TLS context (too heavy for local IPC, hence Named Pipes/Domain Sockets preferred).

## 4. Limits and Quotas
- **Max Request Size**: 4 KB
- **Max Response Size**: 256 KB (Oversize results in OVERSIZE status)
- **Timeouts**: 500ms max blocking on IPC.
- **Concurrency**: Max 10 concurrent requests per consumer.

## 5. Exploitation Impact
- **Malicious Process**: Cannot shape execution due to Prohibited Content rules (no executable instructions).
- **Stale Response**: Rejected by `expires_at` checks (STALE).
- **Downgrade**: Prevented by strict removal of v1 endpoints and version enforcement.
