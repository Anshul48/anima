"""Dialectic prompt templates for State Space Tree search."""

from .dialectic import (
    render_adhd_explorer_prompt,
    render_asd_exploiter_prompt,
    render_cortex_critic_prompt,
    render_cortex_synthesizer_prompt,
    render_critique_prompt,
    render_diverge_prompt,
    render_refine_prompt,
    render_synthesize_prompt,
)

__all__ = [
    "render_diverge_prompt",
    "render_refine_prompt",
    "render_critique_prompt",
    "render_synthesize_prompt",
    "render_adhd_explorer_prompt",
    "render_asd_exploiter_prompt",
    "render_cortex_critic_prompt",
    "render_cortex_synthesizer_prompt",
]
