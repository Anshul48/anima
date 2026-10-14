"""Prompt templates for State Space Tree asymmetric dialectic exploration and synthesis."""

from __future__ import annotations

from sst.core.models import AuDHDContextCapsule, DomainMode, SSTNode


def render_diverge_prompt(
    goal: str,
    capsule: AuDHDContextCapsule,
    domain: DomainMode,
    branch_count: int = 3,
    prior_attempts: list[str] | None = None,
) -> str:
    """Renders the prompt for the high-entropy divergent explorer (DIVERGE / Qwen @ temp >= 1.2)."""
    prior_block = ""
    if prior_attempts:
        prior_block = (
            "\n### PREVIOUS ATTEMPTS, PRUNED BRANCHES & LEARNED NEGATIVE RULES (AVOID REPEATING THESE):\n"
            + "\n".join(f"- {attempt}" for attempt in prior_attempts)
            + "\n"
        )

    invariants_block = "\n".join(f"- {inv}" for inv in capsule.invariants) if capsule.invariants else "- None"
    files_block = "\n".join(
        f"### File: {path}\n```\n{content}\n```" for path, content in capsule.relevant_files.items()
    )

    if domain == DomainMode.AUTOBUILD:
        return f"""# SYSTEM INSTRUCTION: HIGH-ENTROPY EXPLORATION (ADHD EXPLORER)

You are an unconstrained, highly creative senior systems architect and algorithm designer.
Your mission is to generate {branch_count} RADICALLY DIFFERENT, high-novelty architectural strategies to achieve the target goal.

## CORE GOAL
{goal}

## SYSTEM INVARIANTS
{invariants_block}

## ACTION SPACE CONSTRAINTS
{capsule.action_space_boundary}
{prior_block}
## CONTEXT REPOSITORY FILES
{files_block}

## GENERATION RULES:
1. Do NOT generate standard, average, or boring boilerplate if a novel or more optimal data structure/algorithm exists.
2. Formulate {branch_count} structurally distinct branches (e.g. Branch A: Lock-free ring buffer / extreme throughput; Branch B: Event-driven actor model / extreme isolation; Branch C: Cache-coherent zero-copy layout).
3. Output each branch with an explicit rationale and complete functional code / patch.

Output valid JSON matching this schema:
{{
  "branches": [
    {{
      "branch_index": 0,
      "strategy_title": "<Short distinct strategy name>",
      "hypothesis_or_rationale": "<Why this approach solves the problem in a novel or optimal way>",
      "proposed_changes": "<Complete implementation code or diff>"
    }}
  ]
}}
"""
    else:  # AUTORESEARCH
        return f"""# SYSTEM INSTRUCTION: HIGH-ENTROPY RESEARCH EXPLORATION (ADHD EXPLORER)

You are a bold, creative AI/ML scientific researcher exploring frontier hypotheses.
Your mission is to generate {branch_count} RADICALLY DIFFERENT, novel, testable research hypotheses to solve the empirical research goal.

## RESEARCH GOAL
{goal}

## DOMAIN INVARIANTS & BASELINES
{invariants_block}
{prior_block}
## PRIOR INSIGHTS & LITERATURE CONTEXT
{chr(10).join(f"- {item}" for item in capsule.literature_or_prior_insights) if capsule.literature_or_prior_insights else "- None"}

## GENERATION RULES:
1. Avoid mundane parameter sweeps. Propose structurally novel algorithmic mechanisms, loss formulations, or architectures.
2. Ensure each hypothesis is empirically falsifiable and testable with a Python script against the baseline.
3. Output valid JSON matching this schema:
{{
  "branches": [
    {{
      "branch_index": 0,
      "strategy_title": "<Hypothesis title>",
      "hypothesis_or_rationale": "<Theoretical justification from first principles>",
      "proposed_changes": "<Executable python experiment code modifying the baseline>"
    }}
  ]
}}
"""


# Backward compatibility alias
render_adhd_explorer_prompt = render_diverge_prompt


def render_refine_prompt(
    parent_goal: str,
    mutation_title: str,
    mutation_content: str,
    capsule: AuDHDContextCapsule,
    domain: DomainMode,
) -> str:
    """Renders the prompt for the low-entropy exploiter (REFINE / DeepSeek @ temp 0.0-0.1)."""
    invariants_block = "\n".join(f"- {inv}" for inv in capsule.invariants) if capsule.invariants else "- None"
    files_block = "\n".join(
        f"### File: {path}\n```\n{content}\n```" for path, content in capsule.relevant_files.items()
    )

    if domain == DomainMode.AUTOBUILD:
        return f"""# SYSTEM INSTRUCTION: MONOTROPIC FIRST-PRINCIPLES EXPLOITATION (ASD EXPLOITER)

You are a rigorous, zero-tolerance software engineer, type theorist, and compiler validator.
You have been handed a creative, raw architectural mutation. Your job is to extract its core algorithmic truth, eliminate all syntax errors, hallucinations, and type mismatches, and refactor it so it compiles flawlessly and passes all unit tests.

## TARGET GOAL
{parent_goal}

## RAW CREATIVE MUTATION TO REFINE
Strategy: {mutation_title}
Raw Draft:
```
{mutation_content}
```

## UNBENDABLE INVARIANTS & INTERFACES
{invariants_block}

## CONTEXT FILES
{files_block}

## YOUR MANDATE:
1. Strip away all sloppy hallucinations, missing imports, and broken type definitions.
2. Strictly align with all system invariants and interface contracts.
3. Produce clean, complete, production-grade code that will run in an isolated test sandbox without errors.

Output valid JSON matching this schema:
{{
  "refined_title": "<Precise descriptive title>",
  "refactoring_notes": "<List of fixes and invariants enforced>",
  "executable_content": "<Complete verified code ready for sandbox execution>"
}}
"""
    else:  # AUTORESEARCH
        return f"""# SYSTEM INSTRUCTION: RIGOROUS EXPERIMENT SCIENTIST (ASD EXPLOITER)

You are an exacting experimental scientist and statistician.
You have been handed a novel research hypothesis. Your job is to transform this raw concept into a rigorous, leak-free, reproducible Python experiment script.

## TARGET RESEARCH GOAL
{parent_goal}

## RAW HYPOTHESIS DRAFT
Strategy: {mutation_title}
Draft:
```
{mutation_content}
```

## EXPERIMENTAL INVARIANTS & SANITY RULES:
1. Zero Data Leakage: Training, validation, and test splits must remain strictly segregated.
2. Seed Control: Fixed deterministic seeds with multi-fold cross-validation.
3. Resource Limits: Bounded execution time, memory usage, and compute loops.
4. Metric Emission: Output structured JSON metrics (accuracy, loss, p-value, effect size) to stdout.

Output valid JSON matching this schema:
{{
  "refined_title": "<Precise hypothesis & experiment title>",
  "refactoring_notes": "<Sanity controls added>",
  "executable_content": "<Complete reproducible python experiment script>"
}}
"""


# Backward compatibility alias
render_asd_exploiter_prompt = render_refine_prompt


def render_critique_prompt(
    goal: str,
    capsule: AuDHDContextCapsule,
    surviving_candidates: list[SSTNode],
    domain: DomainMode,
) -> str:
    """Renders the prompt for the Frontier Model (GLM-5 / Gemini / Claude) Value Critic."""
    candidates_block = ""
    for c in surviving_candidates:
        candidates_block += f"\n--- CANDIDATE NODE [{c.node_id}]: {c.title} ---\n"
        candidates_block += f"Role: {c.role.value}\n"
        if c.deterministic_result:
            candidates_block += f"Sandbox Tests: Passed ({c.deterministic_result.tests_passed} passed, duration: {c.deterministic_result.duration_seconds:.2f}s)\n"
        candidates_block += f"Content Preview:\n```\n{c.content[:1500]}\n```\n"

    return f"""# SYSTEM INSTRUCTION: STATE SPACE TREE VALUE CRITIC & SYNTHESIZER

You are the Executive Prefrontal Cortex of an autonomous intelligent system.
Your role is to act as the Value Network in an MCTS State Space Tree. You evaluate surviving candidates that have already passed deterministic sandbox testing.

## OVERALL OBJECTIVE
{goal}

## SYSTEM INVARIANTS & GOALS
{chr(10).join(f"- {inv}" for inv in capsule.invariants) if capsule.invariants else "- None"}

## SURVIVING CANDIDATES (PASSED DETERMINISTIC TESTING)
{candidates_block}

## EVALUATION MANDATE:
1. Score each candidate from 0.0 to 1.0 based on architectural elegance, long-term maintainability, security, and objective alignment.
2. Determine if one candidate is clearly superior ("APPROVE"), should be discarded ("PRUNE"), or if two clashing candidates contain complementary insights that should be merged ("SYNTHESIZE").
3. If an irreversible breaking change or major security trade-off is detected, mark as "ESCALATE_HUMAN".

Output valid JSON matching this schema:
{{
  "evaluations": [
    {{
      "node_id": "<ID of the node>",
      "verdict": "APPROVE" | "PRUNE" | "SYNTHESIZE" | "ESCALATE_HUMAN",
      "value_score": <float between 0.0 and 1.0>,
      "architectural_fit": <float between 0.0 and 1.0>,
      "critique": "<Detailed technical reasoning>",
      "synthesis_hints": ["<Optional points for synthesis>"],
      "human_escalation_reason": "<Optional explanation if ESCALATE_HUMAN>"
    }}
  ],
  "best_node_id": "<ID of top candidate>",
  "synthesis_opportunity": "<Description of synthesis if applicable, else empty>"
}}
"""


# Backward compatibility alias
render_cortex_critic_prompt = render_critique_prompt


def render_synthesize_prompt(
    goal: str,
    capsule: AuDHDContextCapsule,
    node_a: SSTNode,
    node_b: SSTNode,
    synthesis_guidance: str,
) -> str:
    """Renders the prompt for colimit synthesis of two clashing but complementary branches."""
    return f"""# SYSTEM INSTRUCTION: DIALECTIC COLIMIT SYNTHESIZER

You are synthesizing two divergent, high-performing branches from the State Space Tree.
Both branches passed deterministic sandbox testing and offer distinct architectural breakthroughs.

## OBJECTIVE
{goal}

## SYNTHESIS GUIDANCE
{synthesis_guidance}

## BRANCH A ({node_a.title}):
```
{node_a.content}
```

## BRANCH B ({node_b.title}):
```
{node_b.content}
```

## INVARIANTS
{chr(10).join(f"- {inv}" for inv in capsule.invariants) if capsule.invariants else "- None"}

## MANDATE:
Produce a unified, superior implementation that blends the speed/simplicity of Branch A with the robustness/modularity of Branch B into a single, cohesive artifact.

Output valid JSON matching this schema:
{{
  "synthesized_title": "<Title of the unified solution>",
  "synthesis_rationale": "<How the two perspectives were resolved>",
  "executable_content": "<Complete synthesized code or experiment script>"
}}
"""


# Backward compatibility alias
render_cortex_synthesizer_prompt = render_synthesize_prompt
