# Security Policy

## Supported Versions

We actively provide security updates and bug fixes for the following versions of STC:

| Version | Supported          |
| :------ | :----------------- |
| 0.1.x   | :white_check_mark: |
| < 0.1.0 | :x:                |

---

## Security Architecture & Philosophy

STC is built upon a **fail-closed, defense-in-depth confinement model** to prevent unintended system modification, data tampering, or unauthorized code execution:

1. **Cellular Worktree Confinement:**
   - Autonomous workers run strictly within isolated, ephemeral Git worktrees (`worktrees/stc-{task_id}`).
   - Worktree leases enforce TTL expiration and automatic quarantine transitions upon unexpected errors.
   - Pre- and post-dispatch repository snapshots detect confinement breaches and rogue filesystem modifications.

2. **Cryptographic Notary & Tamper-Evident Receipts:**
   - Every execution run produces an immutable `receipt.json` signed using canonical JSON SHA-256 HMAC digest.
   - Any tampering with gate results, exit codes, task IDs, or commit hashes invalidates verification immediately.

3. **Blind Adversarial Judiciary:**
   - Candidate diffs are probed by the independent `JudiciaryAuditor` for hardcoded credentials, secret keys, MagicMock gaming, and silent fallbacks (`except: pass`) before merge authorization.

4. **Sovereign Authorization Gate:**
   - STC explicitly forbids autonomous workers or orchestrators from pushing or merging to `main`.
   - The Human Sovereign retains sole cryptographic and execution merge authority (`stc promote`).

---

## Reporting a Vulnerability

If you discover a security vulnerability or confinement flaw in STC, please report it privately rather than opening a public issue.

### How to Report
Please email the security maintainer directly at:
**`anshulraj48@gmail.com`**

Include:
- Type of vulnerability (e.g., worktree confinement breach, receipt signature collision, path traversal, secret leak)
- Step-by-step instructions or proof of concept to reproduce the issue
- Affected subsystem and environment (OS, Python version, Git version)

### Response Timeline
- **Initial Acknowledgement:** Within 48 hours of receipt.
- **Vulnerability Assessment & Triage:** Within 5 business days.
- **Remediation & Patch Release:** Coordinated disclosure timeline aligned with severity.
