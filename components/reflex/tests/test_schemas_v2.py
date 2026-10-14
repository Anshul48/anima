from dataclasses import FrozenInstanceError
import json
import os
from pathlib import Path
import unittest

from reflex.ports.action import ActionReceipt, ActionStatus
from reflex.ports.context import ContextRequest, ContextSnapshot
from reflex.schemas import (
    ActionIdentity,
    ActionProposal,
    ActionType,
    BoundingBox,
    CanonicalUIGraph,
    CapabilityGrant,
    CapabilityPolicy,
    CapabilityScope,
    CropPacket,
    FallbackLevel,
    ModalitySource,
    MotorSkill,
    NodeRole,
    NormalizedCoords,
    OutcomeClass,
    SafetyClass,
    StateDelta,
    SurpriseMetric,
    TransitionTuple,
    UIStateNode,
    TypedAction,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "schemas"


class TestSchemasV2(unittest.TestCase):
    def test_immutability_frozen_dataclasses(self):
        """Validates that core domain contracts are immutable frozen dataclasses."""
        identity = ActionIdentity.create("sess_1", 1, nonce="n1", created_at_ms=1000.0)
        with self.assertRaises(FrozenInstanceError):
            identity.session_id = "sess_2"  # type: ignore

        coords = NormalizedCoords(0.5, 0.5)
        with self.assertRaises(FrozenInstanceError):
            coords.x = 0.9  # type: ignore

        action = TypedAction(action_type=ActionType.CLICK)
        with self.assertRaises(FrozenInstanceError):
            action.action_type = ActionType.TYPE  # type: ignore

        proposal = ActionProposal(identity=identity, action=action)
        with self.assertRaises(FrozenInstanceError):
            proposal.reasoning_summary = "new reasoning"  # type: ignore

        box = BoundingBox(0, 0, 100, 100)
        with self.assertRaises(FrozenInstanceError):
            box.x1 = 10  # type: ignore

        node = UIStateNode(node_id="n1", role=NodeRole.BUTTON, bounds=box)
        with self.assertRaises(FrozenInstanceError):
            node.label = "changed"  # type: ignore

        graph = CanonicalUIGraph(timestamp_ms=1000.0, nodes={"n1": node})
        with self.assertRaises(FrozenInstanceError):
            graph.url = "http://bad.com"  # type: ignore

        delta = StateDelta(added_nodes=["n1"])
        with self.assertRaises(FrozenInstanceError):
            delta.pixel_change_ratio = 0.5  # type: ignore

        grant = CapabilityGrant(scope=CapabilityScope.BROWSER_READ)
        with self.assertRaises(FrozenInstanceError):
            grant.expires_at_ms = 9999.0  # type: ignore

        policy = CapabilityPolicy(granted_scopes={CapabilityScope.BROWSER_READ})
        with self.assertRaises(FrozenInstanceError):
            policy.max_actions_per_session = 10  # type: ignore

        receipt = ActionReceipt(
            lease_id="l1",
            action_id="a1",
            adapter_name="cdp",
            dispatch_timestamp_ms=100.0,
            duration_ms=10.0,
        )
        with self.assertRaises(FrozenInstanceError):
            receipt.status = ActionStatus.FAILED  # type: ignore

        snapshot = ContextSnapshot(snapshot_id="s1", provider="entorhinal", contract_revision="vNext", issued_at="0", expires_at="1", granted_purpose="ASSISTED", granted_scopes=[], facts=[])
        with self.assertRaises(FrozenInstanceError):
            snapshot.confidence = 0.2  # type: ignore

        req = ContextRequest(request_id="test", consumer_identity="test", purpose="ASSISTED", scopes=[], deadline_ms=100, freshness_ms=100, budget_tokens=10)
        with self.assertRaises(FrozenInstanceError):
            req.query = "q2"  # type: ignore

    def test_action_identity_create_and_collision_resistance(self):
        """Ensures ActionIdentity generates unique SHA-256 idempotency keys."""
        seen_keys = set()
        seen_ids = set()

        for step in range(100):
            ident = ActionIdentity.create("sess_test", step)
            self.assertNotIn(ident.idempotency_key, seen_keys)
            self.assertNotIn(ident.action_id, seen_ids)
            seen_keys.add(ident.idempotency_key)
            seen_ids.add(ident.action_id)
            self.assertTrue(ident.action_id.startswith("act_"))
            self.assertEqual(ident.step_index, step)
            self.assertEqual(ident.session_id, "sess_test")

        # Deterministic check with fixed nonce and timestamp
        id1 = ActionIdentity.create("sess_fixed", 5, nonce="static_nonce", created_at_ms=1755430000000.0)
        id2 = ActionIdentity.create("sess_fixed", 5, nonce="static_nonce", created_at_ms=1755430000000.0)
        self.assertEqual(id1.idempotency_key, id2.idempotency_key)
        self.assertEqual(id1.action_id, id2.action_id)
        self.assertEqual(id1, id2)

    def test_bounding_box_geometry(self):
        box = BoundingBox(x1=100, y1=200, x2=300, y2=450)
        self.assertEqual(box.width, 200)
        self.assertEqual(box.height, 250)
        self.assertEqual(box.center, (200, 325))

    def test_context_snapshot_staleness(self):
        # STALE logic was moved to ContextResult/ContextResultStatus in vNext
        pass

    def test_capability_grant_expiry(self):
        grant = CapabilityGrant(
            scope=CapabilityScope.BROWSER_READ,
            granted_at_ms=1000.0,
            expires_at_ms=2000.0,
        )
        self.assertTrue(grant.is_valid(1500.0))
        self.assertFalse(grant.is_expired(1500.0))
        self.assertTrue(grant.is_expired(2001.0))
        self.assertFalse(grant.is_valid(2001.0))

        # Grant without expiry never expires
        infinite_grant = CapabilityGrant(scope=CapabilityScope.BROWSER_INTERACT)
        self.assertTrue(infinite_grant.is_valid(999999999999.0))
        self.assertFalse(infinite_grant.is_expired(999999999999.0))

    def test_fixture_json_roundtrip_action_identity(self):
        path = FIXTURES_DIR / "valid_action_identity.json"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        identity = ActionIdentity.from_dict(data)
        self.assertEqual(identity.action_id, "act_8f7b2c9d1e3a4567")
        self.assertEqual(identity.session_id, "sess_20260817_test")
        self.assertEqual(identity.step_index, 1)

        serialized = identity.to_dict()
        self.assertEqual(serialized, data)

    def test_fixture_json_roundtrip_action_proposal(self):
        path = FIXTURES_DIR / "valid_action_proposal.json"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        proposal = ActionProposal.from_dict(data)
        self.assertEqual(proposal.action.action_type, ActionType.CLICK)
        self.assertIn(CapabilityScope.BROWSER_INTERACT, proposal.required_scopes)
        self.assertIsNotNone(proposal.expected_delta)
        self.assertEqual(proposal.expected_delta.outcome_class, OutcomeClass.SUCCESS)

        serialized = proposal.to_dict()
        self.assertEqual(serialized, data)

    def test_fixture_json_roundtrip_action_receipt(self):
        path = FIXTURES_DIR / "valid_action_receipt.json"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        receipt = ActionReceipt.from_dict(data)
        self.assertEqual(receipt.lease_id, "lease_7a8b9c0d1e2f3456")
        self.assertEqual(receipt.status, ActionStatus.DISPATCHED)
        self.assertEqual(receipt.duration_ms, 23.4)

        serialized = receipt.to_dict()
        self.assertEqual(serialized, data)

    def test_fixture_json_roundtrip_capability_policy(self):
        path = FIXTURES_DIR / "valid_capability_policy.json"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        policy = CapabilityPolicy.from_dict(data)
        self.assertIn(CapabilityScope.BROWSER_INTERACT, policy.granted_scopes)
        self.assertIn("banking.example.com", policy.disallowed_domains)
        self.assertEqual(len(policy.grants), 1)
        self.assertEqual(policy.grants[0].scope, CapabilityScope.CLIPBOARD_READ)

        serialized = policy.to_dict()
        self.assertEqual(serialized, data)

    def test_fixture_json_roundtrip_canonical_ui_graph(self):
        path = FIXTURES_DIR / "valid_canonical_ui_graph.json"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        graph = CanonicalUIGraph.from_dict(data)
        self.assertEqual(graph.active_window_title, "Shopping Cart")
        self.assertEqual(len(graph.nodes), 2)
        self.assertIn("btn_1", graph.nodes)
        self.assertEqual(graph.nodes["btn_1"].role, NodeRole.BUTTON)

        serialized = graph.to_dict()
        self.assertEqual(serialized, data)

    def test_fixture_json_roundtrip_state_delta(self):
        path = FIXTURES_DIR / "valid_state_delta.json"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        delta = StateDelta.from_dict(data)
        self.assertEqual(delta.outcome_class, OutcomeClass.SUCCESS)
        self.assertEqual(delta.pixel_change_ratio, 0.12)
        self.assertEqual(delta.added_nodes, ["order_success_card"])

        serialized = delta.to_dict()
        self.assertEqual(serialized, data)

    def test_fixture_json_roundtrip_transition_tuple(self):
        path = FIXTURES_DIR / "valid_transition_tuple.json"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        tup = TransitionTuple.from_dict(data)
        self.assertEqual(tup.transition_id, "tr_1234567890abcdef")
        self.assertEqual(tup.surprise_score, 0.02)
        self.assertEqual(tup.action.action_type, ActionType.CLICK)

        serialized = tup.to_dict()
        self.assertEqual(serialized, data)

    def test_fixture_json_roundtrip_motor_skill(self):
        path = FIXTURES_DIR / "valid_motor_skill.json"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        skill = MotorSkill.from_dict(data)
        self.assertEqual(skill.skill_id, "skill_checkout_submit_v1")
        self.assertEqual(skill.confidence, 0.98)
        self.assertEqual(len(skill.action_sequence), 1)

        serialized = skill.to_dict()
        self.assertEqual(serialized, data)

    def test_fixture_json_roundtrip_crop_packet(self):
        path = FIXTURES_DIR / "valid_crop_packet.json"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        crop = CropPacket.from_dict(data)
        self.assertEqual(crop.bounding_box, (100, 200, 300, 250))
        self.assertEqual(crop.element_role, "button")

        serialized = crop.to_dict()
        self.assertEqual(serialized, data)

    def test_fixture_json_roundtrip_context_snapshot(self):
        pass


if __name__ == "__main__":
    unittest.main()
