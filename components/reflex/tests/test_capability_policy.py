import json
from pathlib import Path
import unittest

from reflex.host.policy.capability_engine import CapabilityPolicyEngine
from reflex.schemas import (
    ActionIdentity,
    ActionProposal,
    ActionType,
    CapabilityGrant,
    CapabilityPolicy,
    CapabilityScope,
    SafetyClass,
    TypedAction,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "schemas"


class TestCapabilityPolicy(unittest.TestCase):
    def setUp(self):
        self.default_policy = CapabilityPolicy.default_browser_policy()
        self.engine = CapabilityPolicyEngine(self.default_policy)

    def test_fail_closed_scope_denials(self):
        """Ensures actions requesting ungranted scopes are rejected immediately."""
        identity = ActionIdentity.create("sess_test", 1)
        action = TypedAction(action_type=ActionType.CLICK)
        proposal = ActionProposal(
            identity=identity,
            action=action,
            required_scopes={CapabilityScope.FS_WRITE, CapabilityScope.BROWSER_INTERACT},
        )

        result = self.engine.evaluate(proposal)
        self.assertFalse(result.allowed)
        self.assertEqual(result.violation_type, "SCOPE_NOT_GRANTED")
        self.assertIn(CapabilityScope.FS_WRITE, result.missing_scopes)

        allowed, reason = self.engine.evaluate_proposal(proposal)
        self.assertFalse(allowed)
        self.assertIn("Missing required capability scopes", reason)

    def test_granted_scope_approval(self):
        """Ensures actions requesting permitted scopes are authorized."""
        identity = ActionIdentity.create("sess_test", 1)
        action = TypedAction(action_type=ActionType.CLICK)
        proposal = ActionProposal(
            identity=identity,
            action=action,
            required_scopes={CapabilityScope.BROWSER_INTERACT},
        )

        result = self.engine.evaluate(proposal)
        self.assertTrue(result.allowed)
        self.assertEqual(result.reason, "Authorized")

    def test_grant_expiration_handling(self):
        """Validates temporary capability grants expire accurately based on timestamp."""
        grant = CapabilityGrant(
            scope=CapabilityScope.CLIPBOARD_READ,
            granted_at_ms=1000.0,
            expires_at_ms=2000.0,
        )
        policy = CapabilityPolicy(
            granted_scopes={CapabilityScope.BROWSER_INTERACT},
            grants=[grant],
        )
        engine = CapabilityPolicyEngine(policy)

        identity = ActionIdentity.create("sess_test", 1)
        action = TypedAction(action_type=ActionType.CLICK)
        proposal = ActionProposal(
            identity=identity,
            action=action,
            required_scopes={CapabilityScope.CLIPBOARD_READ},
        )

        # Before expiry (1500ms): Authorized
        res_before = engine.evaluate(proposal, current_time_ms=1500.0)
        self.assertTrue(res_before.allowed)

        # After expiry (2500ms): Rejected
        res_after = engine.evaluate(proposal, current_time_ms=2500.0)
        self.assertFalse(res_after.allowed)
        self.assertEqual(res_after.violation_type, "SCOPE_NOT_GRANTED")
        self.assertIn(CapabilityScope.CLIPBOARD_READ, res_after.missing_scopes)

    def test_domain_boundary_filtering(self):
        """Ensures target domains matching blacklist patterns or metadata IPs are blocked."""
        identity = ActionIdentity.create("sess_test", 1)

        # Exact match
        action_bank = TypedAction(
            action_type=ActionType.CLICK,
            metadata={"domain": "banking.example.com"},
        )
        prop_bank = ActionProposal(identity=identity, action=action_bank)
        res_bank = self.engine.evaluate(prop_bank)
        self.assertFalse(res_bank.allowed)
        self.assertEqual(res_bank.violation_type, "DOMAIN_DISALLOWED")

        # Wildcard match: *.internal
        action_internal = TypedAction(
            action_type=ActionType.CLICK,
            metadata={"url": "https://service.corp.internal/admin"},
        )
        prop_internal = ActionProposal(identity=identity, action=action_internal)
        res_internal = self.engine.evaluate(prop_internal)
        self.assertFalse(res_internal.allowed)
        self.assertEqual(res_internal.violation_type, "DOMAIN_DISALLOWED")

        # AWS metadata IP
        action_meta = TypedAction(
            action_type=ActionType.NAVIGATE,
            text_payload="http://169.254.169.254/latest/meta-data/",
        )
        prop_meta = ActionProposal(identity=identity, action=action_meta)
        res_meta = self.engine.evaluate(prop_meta)
        self.assertFalse(res_meta.allowed)
        self.assertEqual(res_meta.violation_type, "DOMAIN_DISALLOWED")

        # Allowed domain
        action_safe = TypedAction(
            action_type=ActionType.CLICK,
            metadata={"domain": "shop.example.com"},
        )
        prop_safe = ActionProposal(identity=identity, action=action_safe)
        res_safe = self.engine.evaluate(prop_safe)
        self.assertTrue(res_safe.allowed)

    def test_safety_class_human_confirmation_gating(self):
        """Ensures DESTRUCTIVE and AMBIGUOUS actions require signed confirmation."""
        identity = ActionIdentity.create("sess_test", 1)

        # Destructive action without confirmation: BLOCKED
        action_destr = TypedAction(
            action_type=ActionType.CLICK,
            safety_class=SafetyClass.DESTRUCTIVE,
        )
        prop_destr = ActionProposal(identity=identity, action=action_destr)
        res_destr = self.engine.evaluate(prop_destr)
        self.assertFalse(res_destr.allowed)
        self.assertTrue(res_destr.requires_human_confirmation)
        self.assertEqual(res_destr.violation_type, "HUMAN_CONFIRMATION_REQUIRED")

        # Destructive action WITH human confirmation: AUTHORIZED
        action_destr_confirmed = TypedAction(
            action_type=ActionType.CLICK,
            safety_class=SafetyClass.DESTRUCTIVE,
            metadata={"human_confirmed": True},
        )
        prop_destr_confirmed = ActionProposal(identity=identity, action=action_destr_confirmed)
        res_destr_confirmed = self.engine.evaluate(prop_destr_confirmed)
        self.assertTrue(res_destr_confirmed.allowed)

        # Ambiguous action with confirmation token: AUTHORIZED
        action_ambig_token = TypedAction(
            action_type=ActionType.KEY_PRESS,
            safety_class=SafetyClass.AMBIGUOUS,
            metadata={"confirmation_token": "usr_token_98765"},
        )
        prop_ambig_token = ActionProposal(identity=identity, action=action_ambig_token)
        res_ambig_token = self.engine.evaluate(prop_ambig_token)
        self.assertTrue(res_ambig_token.allowed)

    def test_session_action_rate_limiting(self):
        """Ensures session execution halts once maximum permitted actions ceiling is reached."""
        policy = CapabilityPolicy(
            granted_scopes={CapabilityScope.BROWSER_INTERACT},
            max_actions_per_session=10,
        )
        engine = CapabilityPolicyEngine(policy)
        identity = ActionIdentity.create("sess_test", 10)
        action = TypedAction(action_type=ActionType.CLICK)
        proposal = ActionProposal(identity=identity, action=action)

        # 9 actions: Allowed
        res_9 = engine.evaluate(proposal, session_action_count=9)
        self.assertTrue(res_9.allowed)

        # 10 actions: Rejected
        res_10 = engine.evaluate(proposal, session_action_count=10)
        self.assertFalse(res_10.allowed)
        self.assertEqual(res_10.violation_type, "SESSION_LIMIT_EXCEEDED")

    def test_infer_required_scopes(self):
        """Validates automatic capability scope deduction for actions."""
        click_act = TypedAction(action_type=ActionType.CLICK)
        self.assertEqual(
            self.engine.infer_required_scopes(click_act),
            {CapabilityScope.BROWSER_INTERACT},
        )

        nav_act = TypedAction(action_type=ActionType.NAVIGATE)
        self.assertEqual(
            self.engine.infer_required_scopes(nav_act),
            {CapabilityScope.BROWSER_NAVIGATE},
        )

        wait_act = TypedAction(action_type=ActionType.WAIT)
        self.assertEqual(self.engine.infer_required_scopes(wait_act), set())

        os_click_act = TypedAction(action_type=ActionType.CLICK, metadata={"os_native": True})
        self.assertEqual(
            self.engine.infer_required_scopes(os_click_act),
            {CapabilityScope.OS_INPUT_INJECT},
        )

    def test_evaluating_invalid_proposal_fixture(self):
        """Evaluates fixture with missing scopes; asserts rejection."""
        path = FIXTURES_DIR / "invalid_action_proposal_missing_scopes.json"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        proposal = ActionProposal.from_dict(data)

        res = self.engine.evaluate(proposal)
        self.assertFalse(res.allowed)
        self.assertEqual(res.violation_type, "SCOPE_NOT_GRANTED")

    def test_evaluating_destructive_proposal_fixture(self):
        """Evaluates fixture with unconfirmed destructive action; asserts confirmation requirement."""
        path = FIXTURES_DIR / "destructive_action_proposal.json"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        proposal = ActionProposal.from_dict(data)

        res = self.engine.evaluate(proposal)
        self.assertFalse(res.allowed)
        self.assertTrue(res.requires_human_confirmation)
        self.assertEqual(res.violation_type, "HUMAN_CONFIRMATION_REQUIRED")


if __name__ == "__main__":
    unittest.main()
