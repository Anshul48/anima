"""Evaluation, Benchmarking, Privacy Stress, and Chaos verification suite for Entorhinal.

Provides:
- EvalRunner: Core evaluation harness executing Track 1 and Track 2 benchmarks.
- EvaluationReport: Structured verification report contract.
- PrivacyStressTester: 500+ vector adversarial credential & PII penetration tester.
- ChaosHarness: Fault injection suite (bit-flips, sigkill, corrupt JSON, cold replay).
- IndependenceAuditor: Static and runtime independence auditor.
"""

from entorhinal.evals.chaos import ChaosHarness
from entorhinal.evals.independence_audit import IndependenceAuditor, IndependenceReport
from entorhinal.evals.privacy_stress import PrivacyStressTester
from entorhinal.evals.runner import EvalRunner, EvaluationReport

__all__ = [
    "ChaosHarness",
    "EvalRunner",
    "EvaluationReport",
    "IndependenceAuditor",
    "IndependenceReport",
    "PrivacyStressTester",
]
