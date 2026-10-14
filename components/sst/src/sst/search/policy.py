"""Search policies, resource budgets, and role routing for the SST engine."""

from __future__ import annotations

from pydantic import BaseModel, Field

from sst.gateway.contracts import RouteTarget


class BudgetTracker(BaseModel):
    """Tracks token consumption, estimated cost, and execution time during search."""

    tokens_consumed: int = 0
    estimated_cost_usd: float = 0.0
    elapsed_seconds: float = 0.0
    iterations_completed: int = 0

    def check_budget(self, policy: SearchPolicy) -> str | None:
        """Returns violation reason if any budget cap is exceeded, else None."""
        if policy.max_token_budget and self.tokens_consumed >= policy.max_token_budget:
            return f"Token budget exceeded ({self.tokens_consumed} >= {policy.max_token_budget})"
        if policy.max_cost_usd and self.estimated_cost_usd >= policy.max_cost_usd:
            return f"Cost budget exceeded (${self.estimated_cost_usd:.4f} >= ${policy.max_cost_usd:.4f})"
        if policy.max_time_seconds and self.elapsed_seconds >= policy.max_time_seconds:
            return f"Time budget exceeded ({self.elapsed_seconds:.1f}s >= {policy.max_time_seconds}s)"
        if self.iterations_completed >= policy.max_iterations:
            return f"Maximum iterations reached ({self.iterations_completed} >= {policy.max_iterations})"
        return None


class SearchPolicy(BaseModel):
    """Guiding parameters and resource constraints for State Space Tree search."""

    max_iterations: int = 10
    max_depth: int = 4
    branching_factor: int = 3
    max_token_budget: int | None = 500_000
    # None default: a USD cap is only meaningful with priced profiles. A set
    # cap with unpriced responses is rejected (UnpricedCostBudgetError),
    # never silently unenforced.
    max_cost_usd: float | None = None
    max_time_seconds: int = 600
    concurrency_limit: int = 4
    # Optional single-writer guard (default OFF for STC compatibility): when
    # True, run_search() acquires the tree's SQLite writer lease first and
    # raises LeaseAcquisitionError on contention. Per-run override via
    # run_search(acquire_lease=...).
    require_lease: bool = False
    temperature_diverge: float = 1.2
    temperature_refine: float = 0.1
    temperature_critique: float = 0.2
    temperature_synthesize: float = 0.3
    # Per-request completion cap override for all roles. None keeps the role
    # defaults (diverge/refine/synthesize 2048, critique 1024). Reasoning
    # models that spend tokens on chains-of-thought need a higher cap so the
    # visible content is not truncated away.
    response_max_tokens: int | None = None
    role_routes: dict[str, RouteTarget] = Field(default_factory=dict)
