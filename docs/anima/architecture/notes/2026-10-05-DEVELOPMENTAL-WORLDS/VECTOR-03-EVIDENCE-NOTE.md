# Vector 3: evidence challenging persistent expert worlds

**Date/status:** 2026-10-06. Bounded architecture evidence note. Recommendations and comparisons are proposed. This note selects no runtime, protocol, model, integration, or build.

## The hypothesis and its stronger alternatives

A persistent expert world could preserve a distinctive history, interpretations, methods, commitments, and outcome learning. The capability hypothesis is that keeping these together, then cooperating across such worlds, produces an advantage over a simpler organization with equivalent resources.

A strong competing explanation is that apparent gains come from extra samples, better task decomposition, reusable procedures, broader evidence access, or additional verification. Those mechanisms can exist within an already hierarchical TRACE. Separate custody and responsibility may also have practical value even when benchmark accuracy is unchanged; that is a different claim to assess.

The three papers below challenge premature attribution to expert individuality. They do not refute the broader developmental ambition.

## Three primary studies

### 1. Coordination gains depend on the task

Kim and colleagues compare five coordination architectures across six agentic benchmarks. They control task prompts, tools and total iteration budgets; the paper also reports matched reasoning-token budgets. Coordination helps some decomposable tasks, while every tested team architecture degrades PlanCraft planning. This establishes task-dependent coordination benefits, rather than a general advantage from additional agents. Participants are principally model instances with role prompts; cumulative expert trajectories are not the intervention tested. The authors explicitly leave spontaneous specialization and self-organization open. Coding and terminal subsets are small, with wide per-cell uncertainty. Their fitted thresholds and verification results should not become universal architectural laws or evidence that a persistent TRACE expert is superior.

**Exact source inspected:** Kim et al., [Towards a Science of Scaling Agent Systems, arXiv:2512.08296v3](https://arxiv.org/html/2512.08296v3), revised 8 April 2026. Read the abstract and selected full-text passages from system definition, experimental setup, main results, coordination/error analysis, robustness and limitations (§§3.1, 4.1–4.2, 4.4–4.5, 5). No full-paper or reproduction claim.

### 2. Multiple answers are a serious baseline for discussion

Choi and colleagues compare initial voting with additional debate among the same number of agents across seven benchmark datasets. Voting accounts for much of the measured gain; debate does not reliably add value. This is a same-agent-count comparison, not a fully matched total-token comparison: debate requires further calls. The martingale result depends on a specified Dirichlet-multinomial update model and conditions on agents' beliefs; it is not a theorem forbidding useful communication. An oracle intervention retains correct responses, but requires unavailable ground truth. The work supplies a strong simpler baseline and a warning about answer subversion. It does not test persistent expert histories, state custody or developmental cooperation.

**Exact source inspected:** Choi, Zhu and Li, [Debate or Vote: Which Yields Better Decisions in Multi-Agent Large Language Models?, arXiv:2508.17536v2](https://arxiv.org/html/2508.17536v2), revised 23 October 2025. Read the abstract and selected full-text methods/results, theoretical assumptions and oracle-intervention passages (§§2–5.1), plus the reported heterogeneous-setting results. Proof appendices and code were not independently audited.

### 3. Persistent competence need not require persistent individuality

Voyager accumulates executable skills, retrieves and composes them, and uses environment feedback in Minecraft without model fine-tuning. Its skill-library ablation and new-world tasks provide evidence that retained procedures improve later work. Giving the library to an AutoGPT baseline also helps, showing that some acquired capability can travel separately from the original agent. This is one acting agent supported by curriculum and verification calls, not a persistent expert society. The environment uses high-level control APIs; transfer covers a small Minecraft task set. Comparisons use prompting-iteration limits rather than complete lifetime compute accounting. Persistent skill reuse is supported here; independent individuality and separate interpretive histories are not isolated.

**Exact source inspected:** Wang et al., [Voyager: An Open-Ended Embodied Agent with Large Language Models, arXiv:2305.16291v2](https://arxiv.org/html/2305.16291v2). Read the abstract and selected skill-library/feedback methods, baseline definitions, transfer results, Table 2, ablations and limitations (§§2.2–2.3, 3.1–3.4, 4). The project's large PDF failed the browsing fetch size limit; the official arXiv HTML supplied these passages. Prompt appendices and implementation were not independently audited.

## What remains unsupported

**Interpretation:** None of these selected comparisons isolates a whole evolving expert world: separate interpretations, persistent methods, commitments, state/lifecycle responsibility, and learned cooperation developing together. Neither a favorable multi-agent result nor a successful skill library identifies when such a world deserves independence. Fusion, fission and preservation of useful differences remain research questions.

**Common-mode error is still a discrimination problem.** Different responses, names or model instances do not establish independent failure modes. The voting paper's favorable sampling result assumes that the correct option has the strongest initial belief; that premise cannot certify a shared misconception. Its count-based debate theorem also does not establish the behavior of evidence-seeking experts that acquire new information. For ANIMA, correlated wrong conclusions under shared model or source defects should be measured directly. This paragraph is an inference and proposed evaluation concern, not a claimed new experiment.

The persistence claim should also survive a shared-library alternative. A world can improve because it retains useful work, while its separate identity contributes little. Conversely, independence may protect unresolved interpretations or a rare method that a shared organization would discard. The present evidence set does not decide that tradeoff.

## Proposed discriminating comparisons

The following are research questions, not a campaign instruction or universal gate sequence.

1. **Separate persistence from extra calls.** Compare a capable hierarchical organization with shared experience and procedures; ephemeral role-based specialists; and specialists with persistent histories and methods. Give each arrangement access to the same raw experiences, tools and model pool. Permit different organization and context selection, since those are mechanisms under investigation. Account for total input/output tokens, tool use, external assistance, context reconstruction, memory maintenance and evaluation. A per-call saving or higher call count is not the outcome.

2. **Ask what the history contributes.** Compare retaining distinct histories with supplying a common procedure/evidence library. Vary persistent interpretation, method learning and model specialization separately where meaningful. On co-adapted arrangements, use coherent alternatives: abruptly removing a depended-on component can produce failure without identifying its original contribution. Charge learning costs across the task sequence, alongside later benefits.

3. **Test useful differences under pressure.** Use cases where a minority expert has an applicable counterexample, and cases where all participants receive the same misleading evidence. Assess conditional correctness, evidence coverage, preservation of valid dissent and recovery after independent feedback. Stylistic diversity and agreement are insufficient measures. The authoritative outcome check should not depend solely on the same consensus being evaluated.

4. **Test the organizational transitions themselves.** Compare a loose coalition, a shared-model arrangement and a deeper composite on a recurring problem. After conditions change, examine separation or expert extraction and reuse elsewhere. Observe actual state, lifecycle and responsibility consequences, retained failure conditions, reconstruction effort and whether a new workload benefits. Merely renaming a group or exporting a polished summary does not isolate these effects.

A real capability gain could be newly feasible tasks, better outcomes under equal total budgets, or retained advantages on unfamiliar conditions that survive the shared-library and extra-sampling alternatives. Individuality can also earn its place through reduced interference, clearer continuing responsibility or preservation of complementary methods. Those benefits require their own observations; they should not be relabeled as general intelligence.

## Scope and limits

The source summaries report the authors' experiments; no experiment, benchmark, model, tool path or physical system was reproduced here. The cited revisions and selected passages are the actual inspected source scope. Search results and secondary summaries were discovery aids only. No claim of a comprehensive literature survey or validation of persistent expert societies is made.

Current ANIMA boundaries were refreshed from [RESPONSIBILITIES.md](../../RESPONSIBILITIES.md), [OPERATIVE-BRIEF.md](../../../context/OPERATIVE-BRIEF.md) and the prior [expert-worlds dossier](EXPERT-WORLDS-AND-SEARCH.md). TL's source duties, TRACE's scoped interpretation responsibilities and domain evaluation ownership remain unchanged by this proposal. No memory-derived project fact is used.

