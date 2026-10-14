from __future__ import annotations
from dataclasses import dataclass, field
import fnmatch
import time
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

from reflex.schemas.actions import ActionType, SafetyClass, TypedAction
from reflex.schemas.identity import ActionProposal
from reflex.schemas.policy import CapabilityGrant, CapabilityPolicy, CapabilityScope


@dataclass(frozen=True)
class PolicyEvaluationResult:
    """Detailed evaluation result from CapabilityPolicyEngine."""
    allowed: bool
    reason: str
    requires_human_confirmation: bool = False
    missing_scopes: Set[CapabilityScope] = field(default_factory=set)
    violation_type: Optional[str] = None

    def __bool__(self) -> bool:
        return self.allowed


class CapabilityPolicyEngine:
    """Host-local capability policy evaluator enforcing fail-closed security rules."""

    def __init__(self, policy: Optional[CapabilityPolicy] = None, clock: Optional[Any] = None):
        self.policy = policy if policy is not None else CapabilityPolicy.default_browser_policy()
        self.clock = clock

    def evaluate_proposal(
        self,
        proposal: ActionProposal,
        session_action_count: int = 0,
        current_time_ms: Optional[float] = None,
    ) -> tuple[bool, str]:
        """Evaluates an action proposal and returns (allowed, reason) tuple."""
        result = self.evaluate(
            proposal=proposal,
            session_action_count=session_action_count,
            current_time_ms=current_time_ms,
        )
        return result.allowed, result.reason

    def evaluate(
        self,
        proposal: ActionProposal,
        session_action_count: int = 0,
        current_time_ms: Optional[float] = None,
    ) -> PolicyEvaluationResult:
        """Performs comprehensive multi-stage policy authorization on an action proposal."""
        if current_time_ms is None:
            if self.clock is not None and hasattr(self.clock, "now_ms"):
                current_time_ms = self.clock.now_ms()
            else:
                current_time_ms = time.time() * 1000.0

        # 1. Check Session Rate Limit
        if session_action_count >= self.policy.max_actions_per_session:
            return PolicyEvaluationResult(
                allowed=False,
                reason=f"Session action limit reached: {session_action_count} >= {self.policy.max_actions_per_session}",
                violation_type="SESSION_LIMIT_EXCEEDED",
            )

        # 2. Check Domain Blacklist / Boundary Filter
        target_domain = self._extract_target_domain(proposal)
        if target_domain and self.is_domain_disallowed(target_domain):
            return PolicyEvaluationResult(
                allowed=False,
                reason=f"Target domain '{target_domain}' is blacklisted by policy",
                violation_type="DOMAIN_DISALLOWED",
            )

        # 3. Check Capability Scopes (Fail-Closed)
        required_scopes = (
            set(proposal.required_scopes)
            if proposal.required_scopes
            else self.infer_required_scopes(proposal.action)
        )

        effective_granted_scopes = set(self.policy.granted_scopes)
        for grant in self.policy.grants:
            if grant.is_valid(current_time_ms):
                effective_granted_scopes.add(grant.scope)

        missing_scopes = required_scopes - effective_granted_scopes
        if missing_scopes:
            formatted_missing = sorted([s.value if isinstance(s, CapabilityScope) else str(s) for s in missing_scopes])
            return PolicyEvaluationResult(
                allowed=False,
                reason=f"Missing required capability scopes: {formatted_missing}",
                missing_scopes=missing_scopes,
                violation_type="SCOPE_NOT_GRANTED",
            )

        # 4. Check Safety Classification & Human Confirmation Gates
        action_safety = proposal.action.safety_class
        if action_safety in self.policy.require_human_confirmation_for:
            is_confirmed = self.check_human_confirmation(proposal)
            if not is_confirmed:
                action_name = (
                    proposal.action.action_type.value
                    if isinstance(proposal.action.action_type, ActionType)
                    else str(proposal.action.action_type)
                )
                safety_name = (
                    action_safety.value
                    if isinstance(action_safety, SafetyClass)
                    else str(action_safety)
                )
                return PolicyEvaluationResult(
                    allowed=False,
                    reason=f"Action {action_name} classified as {safety_name}; requires human confirmation",
                    requires_human_confirmation=True,
                    violation_type="HUMAN_CONFIRMATION_REQUIRED",
                )

        return PolicyEvaluationResult(
            allowed=True,
            reason="Authorized",
        )

    def is_domain_disallowed(self, domain_or_url: str) -> bool:
        """Determines if a domain or URL is prohibited by policy."""
        domain = self._normalize_domain(domain_or_url)
        if not domain:
            return False

        for disallowed in self.policy.disallowed_domains:
            norm_disallowed = self._normalize_domain(disallowed)
            if norm_disallowed == domain:
                return True
            # Wildcard matching (e.g. *.internal matches sub.internal or internal)
            if disallowed.startswith("*."):
                suffix = disallowed[2:].lower()
                if domain.endswith("." + suffix) or domain == suffix:
                    return True
            if fnmatch.fnmatch(domain, disallowed.lower()):
                return True

        return False

    def check_human_confirmation(self, proposal: ActionProposal) -> bool:
        """Verifies if explicit human confirmation has been granted for this proposal."""
        # Check action metadata
        if proposal.action.metadata.get("human_confirmed") is True:
            return True
        if bool(proposal.action.metadata.get("confirmation_token")):
            return True
        # Check proposal metadata
        if proposal.metadata.get("human_confirmed") is True:
            return True
        if bool(proposal.metadata.get("confirmation_token")):
            return True
        return False

    def infer_required_scopes(self, action: TypedAction) -> Set[CapabilityScope]:
        """Infers the minimal required capability scopes for an action."""
        # Explicit scope override in metadata
        if "required_scope" in action.metadata:
            raw = action.metadata["required_scope"]
            if isinstance(raw, CapabilityScope):
                return {raw}
            if isinstance(raw, str) and raw in CapabilityScope._value2member_map_:
                return {CapabilityScope(raw)}

        if action.action_type in {
            ActionType.CLICK,
            ActionType.DOUBLE_CLICK,
            ActionType.RIGHT_CLICK,
            ActionType.HOVER,
            ActionType.SCROLL,
            ActionType.DRAG_AND_DROP,
            ActionType.TYPE,
            ActionType.KEY_PRESS,
        }:
            if action.metadata.get("os_native"):
                return {CapabilityScope.OS_INPUT_INJECT}
            return {CapabilityScope.BROWSER_INTERACT}

        if action.action_type == ActionType.NAVIGATE:
            return {CapabilityScope.BROWSER_NAVIGATE}

        if action.action_type in {ActionType.WAIT, ActionType.NOOP}:
            return set()

        return {CapabilityScope.BROWSER_INTERACT}

    def _extract_target_domain(self, proposal: ActionProposal) -> str:
        """Extracts candidate target domain from proposal or action metadata."""
        for candidate in [
            proposal.action.metadata.get("domain"),
            proposal.action.metadata.get("url"),
            proposal.metadata.get("domain"),
            proposal.metadata.get("url"),
        ]:
            if candidate and isinstance(candidate, str):
                return self._normalize_domain(candidate)

        if proposal.action.action_type == ActionType.NAVIGATE and proposal.action.text_payload:
            return self._normalize_domain(proposal.action.text_payload)

        return ""

    def _normalize_domain(self, domain_or_url: str) -> str:
        """Normalizes a domain or URL string to a clean lowercased hostname."""
        cleaned = domain_or_url.strip()
        if not cleaned:
            return ""

        if "://" in cleaned:
            parsed = urlparse(cleaned)
            hostname = parsed.hostname or ""
            return hostname.lower()

        # May contain path or port
        if "/" in cleaned:
            cleaned = cleaned.split("/")[0]
        if ":" in cleaned and not cleaned.startswith("*"):
            cleaned = cleaned.split(":")[0]

        return cleaned.lower()
