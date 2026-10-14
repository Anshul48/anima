"""Structured prompt definitions and templates for Entorhinal AI projections."""

from __future__ import annotations

INTENT_CLASSIFICATION_PROMPT = """You are the epistemic reasoning engine of Entorhinal, a local contextual intelligence system.
Analyze the following developer activity events (window focus, terminal commands, browser titles) and infer the primary macro-task intent.

Constraints:
- Output MUST be valid JSON matching the schema below.
- Do NOT fabricate facts not supported by evidence.
- State a calibrated confidence score between 0.05 and 0.95.

Input Evidence:
{evidence_summary}

JSON Schema:
{{
  "task_intent": "string (e.g. 'Refactoring API Client', 'Debugging Test Failure', 'Reading Documentation')",
  "confidence": 0.85,
  "key_entities": ["list", "of", "relevant", "files_or_symbols"],
  "reasoning_summary": "1-2 sentence rationale grounded strictly in provided evidence"
}}
"""

SESSION_SYNTHESIS_PROMPT = """You are Entorhinal's session synthesis compiler.
Summarize the active developer session across multiple timescales into a concise, actionable context snapshot.

Recent Focus State:
{focus_state}

Recent Commands & File Context:
{recent_context}

Output a single JSON object:
{{
  "summary": "Brief 1-3 sentence summary of current work in progress",
  "active_goal": "Inferred immediate goal",
  "confidence": 0.80,
  "suggested_topics": ["topic1", "topic2"]
}}
"""
