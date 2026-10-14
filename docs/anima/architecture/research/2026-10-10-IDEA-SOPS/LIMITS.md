# LIMITS.md: Documentary Scope, Verification Frontier, and Methodological Boundaries

## 1. Scope of Investigation and Source Access Log

This investigation was conducted strictly within the bounded remit of the public documentary brief. A total of 8 public HTTP retrieval requests were executed against the primary public endpoints (within the mandatory 10-call ceiling).

### Source Retrieval and Inspection Audit

| Source Identifier | Target URL / URI | Format Retrieved | Observed Tool Outcome | Access Date / Frontier | Specific Scope Examined |
|---|---|---|---|---|---|
| **SRC-1: Nygard ADR** | `https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions` | HTML (Full Article) | DONE (Fetch Success) | 2026-10-10 | Retrieved text: Context, Decision, Status, Consequences, Experience Report. |
| **SRC-2: Rust RFCs** | `https://raw.githubusercontent.com/rust-lang/rfcs/master/README.md` | Raw Markdown | DONE (Fetch Success) | 2026-10-10 | Sections: When to follow process, Sub-teams, Before creating an RFC, The process, Life-cycle. |
| **SRC-2 (Branch Check)** | `https://raw.githubusercontent.com/rust-lang/rfcs/main/README.md` | Raw Markdown | DONE (Fetch Success) | 2026-10-10 | Fetched content matching master branch snapshot. |
| **SRC-3: Google Code Review** | `https://google.github.io/eng-practices/review/reviewer/standard.html` | Rendered HTML | DONE (Fetch Success) | 2026-10-10 | Initial HTML structure, heading, core standard statement. |
| **SRC-3 (Raw Path Attempt)** | `https://raw.githubusercontent.com/google/eng-practices/master/docs/review/reviewer/standard.md` | Raw Markdown | ERROR (HTTP 404) | 2026-10-10 | Gapped path; corrected to canonical repository layout. |
| **SRC-3 (Raw Canonical)** | `https://raw.githubusercontent.com/google/eng-practices/master/review/reviewer/standard.md` | Raw Markdown | DONE (Fetch Success) | 2026-10-10 | Raw markdown text: The Standard of Code Review principle and tradeoffs. |
| **SRC-4: Kubernetes KEPs** | `https://raw.githubusercontent.com/kubernetes/enhancements/master/keps/README.md` | Raw Markdown | DONE (Fetch Success) | 2026-10-10 | Retrieved text: Quick start, Sponsoring SIG socialization, FAQs, threshold for KEPs. |
| **SRC-5: Wilson et al.** | `https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1005510` | Full Publication HTML | DONE (Fetch Success) | 2026-10-10 | Retrieved paper: Box 1, Data management, Software, Collaboration, Project organization, What we left out, Citations. |

---

## 2. Identified Uncertainties and Version Drift

1. **Repository Branch and Layout Drift:**
   * Open-source governance repositories on GitHub (Rust RFCs, Kubernetes Enhancements, Google Eng Practices) evolve continuously. Default branches transition between `master` and `main`, and document paths occasionally shift (e.g. `docs/` vs root subdirectories). The findings here reflect the repository snapshots accessed on 2026-10-10.
2. **Organizational Context & Transfer Inference:**
   * Google's code review standard articulates the reviewer's code-health responsibility and imperfect improvement principle; enterprise organizational contexts (such as monorepos or extensive automated test coverage) are external environmental factors, not explicit prerequisites stated on the standard page.
   * Kubernetes KEPs and Rust RFCs are designed to govern decentralized open-source communities with many contributors and multi-stakeholder representation.
   * Adapting these patterns to small teams is an inference-based adaptation proposal, requiring calibration to avoid excessive coordination overhead.
3. **Absence of Quantitative / Empirical Validation:**
   * The analyzed sources represent practitioner consensus, normative guides, and internal organizational policies. They do not constitute randomized controlled trials or empirical causal proofs of superior software outcomes.

---

## 3. Deliberate Exclusions and Non-Scope

* **No Secondary Literature Expansion:** In accordance with the prompt's bounding instructions, secondary academic surveys, tangential blog posts, and external project documentation beyond the five assigned sources were intentionally not fetched.
* **No Unverified Reconstructions:** Gapped paths (such as the initial 404 on the Google eng-practices raw documentation path) were resolved strictly by direct public URL retrieval of the canonical path rather than relying on unverified recollections.
* **Provisional Documentary Status:** These reports provide analytical comparisons of public practices for informational and evaluative purposes; they do not establish binding policies for any live project or workspace.

---

## 4. Concise Stop Rationale

Across 8 recorded fetch invocations (7 successful completions and 1 explicit 404 error) and observed cache reads, the 5 approved primary source texts were retrieved and mapped against the five core practice dimensions within public network limits. Analysis reflects the retrieved text content without asserting exhaustive cognitive inspection.
