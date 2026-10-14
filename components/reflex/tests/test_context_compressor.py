"""Unit and integration tests for Context Compressor."""

from __future__ import annotations

import json
import unittest

from reflex.cognition.system2.context_compressor import ContextCompressor
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.memory import TransitionTuple


class TestContextCompressor(unittest.TestCase):
    """Test suite for factual timeline compression and token reduction."""

    def setUp(self) -> None:
        self.compressor = ContextCompressor(max_recent_detailed_steps=20)

    def _generate_synthetic_transitions(self, count: int) -> list[TransitionTuple]:
        """Generates realistic multi-step transition sequence."""
        transitions: list[TransitionTuple] = []
        action_types = [
            (ActionType.NAVIGATE, "https://example.com/checkout", None, OutcomeClass.NAVIGATION),
            (ActionType.TYPE, "john_doe@example.com", "Email Input", OutcomeClass.SUCCESS),
            (ActionType.CLICK, None, "Continue to Shipping", OutcomeClass.SUCCESS),
            (ActionType.CLICK, None, "Standard Shipping", OutcomeClass.SUCCESS),
            (ActionType.TYPE, "123 Main St", "Address Input", OutcomeClass.SUCCESS),
            (ActionType.SCROLL, None, None, OutcomeClass.SUCCESS),
            (ActionType.CLICK, None, "Payment Method", OutcomeClass.MODAL_APPEARED),
            (ActionType.CLICK, None, "Dismiss Modal", OutcomeClass.SUCCESS),
            (ActionType.TYPE, "4111222233334444", "Credit Card", OutcomeClass.SUCCESS),
            (ActionType.CLICK, None, "Place Order", OutcomeClass.SUCCESS),
        ]

        for i in range(count):
            act_type, payload, target_lbl, outcome = action_types[i % len(action_types)]
            action = TypedAction(
                action_type=act_type,
                target_node_id=f"node_{i}",
                target_label=target_lbl or f"Target {i}",
                coords=NormalizedCoords(x=0.5, y=0.5),
                text_payload=payload,
                safety_class=SafetyClass.REVERSIBLE,
                metadata={"step": i, "simulated_dom_tree_payload": "x" * 200},
            )
            delta = StateDelta(
                added_nodes=[f"added_{i}_{j}" for j in range(3)],
                removed_nodes=[f"removed_{i}_{j}" for j in range(2)],
                modified_nodes=[f"mod_{i}_{j}" for j in range(4)],
                pixel_change_ratio=0.15,
                changed_bounding_boxes=[(10, 10, 100, 100)],
                outcome_class=outcome,
            )
            transition = TransitionTuple(
                transition_id=f"trans_{i:04d}",
                episode_id="ep_test_001",
                step_index=i,
                timestamp_ms=1000.0 + (i * 500.0),
                ui_state_hash=f"state_hash_before_{i}",
                goal_text="Complete checkout process",
                goal_embedding=[0.05 * (j % 10) for j in range(384)],
                visual_embedding=[0.02 * (j % 10) for j in range(512)],
                action=action,
                next_ui_state_hash=f"state_hash_after_{i}",
                delta=delta,
                duration_ms=450.0,
                surprise_score=0.08,
                provenance={"source": "system2_test", "dom_snapshot_length": 5000},
            )
            transitions.append(transition)

        return transitions

    def test_factual_transition_extraction(self) -> None:
        """Tests that individual action-outcome facts are accurately formatted."""
        action = TypedAction(
            action_type=ActionType.TYPE,
            target_node_id="email-field",
            target_label="Email Address",
            text_payload="user@test.com",
        )
        delta = StateDelta(
            modified_nodes=["email-field"],
            pixel_change_ratio=0.04,
            outcome_class=OutcomeClass.SUCCESS,
        )
        t = TransitionTuple(
            transition_id="t1",
            episode_id="e1",
            step_index=0,
            timestamp_ms=1000.0,
            ui_state_hash="h1",
            goal_text="Enter email",
            goal_embedding=[],
            visual_embedding=None,
            action=action,
            next_ui_state_hash="h2",
            delta=delta,
            duration_ms=100.0,
            surprise_score=0.0,
        )

        fact = self.compressor.extract_fact(t)
        self.assertIn("[Step 0]", fact)
        self.assertIn("TYPE 'user@test.com' into [Email Address]", fact)
        self.assertIn("SUCCESS", fact)
        self.assertIn("~1 modified", fact)

    def test_20_step_compression_efficiency_ge_80_percent(self) -> None:
        """Tests that 20-step history compression achieves >= 80% token reduction."""
        transitions = self._generate_synthetic_transitions(20)
        compressed = self.compressor.compress_history(transitions)
        stats = self.compressor.compute_compression_stats(transitions, compressed)

        self.assertGreaterEqual(
            stats["reduction_percentage"],
            80.0,
            f"Expected >= 80% token reduction, got {stats['reduction_percentage']}%",
        )
        # Verify facts are present
        self.assertIn("Step 0", compressed)
        self.assertIn("Step 19", compressed)
        self.assertIn("NAVIGATE", compressed)
        self.assertIn("MODAL_APPEARED", compressed)

    def test_50_step_long_horizon_compression_and_windowing(self) -> None:
        """Tests that 50-step long horizon compresses with macro-summary for older steps."""
        compressor = ContextCompressor(max_recent_detailed_steps=15)
        transitions = self._generate_synthetic_transitions(50)

        compressed = compressor.compress_history(
            transitions,
            initial_state_summary="Checkout Initial",
            current_state_summary="Order Review",
        )
        stats = compressor.compute_compression_stats(transitions, compressed)

        self.assertGreaterEqual(stats["reduction_percentage"], 85.0)
        self.assertIn("s_0: Checkout Initial", compressed)
        self.assertIn("s_t (current): Order Review", compressed)
        self.assertIn("[Steps 0-34: 35 historical steps executed successfully]", compressed)
        self.assertIn("Step 49", compressed)

    def test_dict_representation_compatibility(self) -> None:
        """Tests that compressor seamlessly handles dictionary representations."""
        dict_transitions = [
            {
                "step_index": 0,
                "action": {
                    "action_type": "click",
                    "target_label": "Sign In",
                    "target_node_id": "btn-signin",
                },
                "delta": {
                    "outcome_class": "modal",
                    "added_nodes": ["modal-auth"],
                    "pixel_change_ratio": 0.40,
                },
            },
            {
                "step_index": 1,
                "action": {
                    "action_type": "type",
                    "target_label": "Username",
                    "text_payload": "alice",
                },
                "delta": {
                    "outcome_class": "success",
                    "modified_nodes": ["input-user"],
                    "pixel_change_ratio": 0.05,
                },
            },
        ]

        compressed = self.compressor.compress_history(dict_transitions)
        self.assertIn("CLICK [Sign In]", compressed)
        self.assertIn("MODAL_APPEARED", compressed)
        self.assertIn("TYPE 'alice' into [Username]", compressed)


if __name__ == "__main__":
    unittest.main()
