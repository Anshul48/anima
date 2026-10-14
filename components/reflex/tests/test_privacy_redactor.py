"""Unit tests for PrivacyRedactor.

SYNTHETIC PROVENANCE: all secret-like strings in this file are synthetic
redaction-test vectors (patterned fakes, placeholder markers), never real
credentials.

Tests client-side scrubbing of passwords, credit cards, CVVs, bearer tokens,
API keys, session cookies, SSNs, and sensitive dictionary metadata.
"""

from __future__ import annotations

import unittest

from reflex.episodes.redactor import PrivacyRedactor, _luhn_checksum
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.memory import TransitionTuple
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode


class TestPrivacyRedactor(unittest.TestCase):
    """Test suite for client-side credential and PII redaction."""

    def setUp(self) -> None:
        self.redactor = PrivacyRedactor(redact_emails=True, mask_credit_cards=True)

    # =========================================================================
    # 1. Password Redaction Tests
    # =========================================================================

    def test_redact_password_key_value_in_text(self) -> None:
        """Asserts password key-value assignments in raw text are redacted."""
        samples = [
            ("password=SuperSecretPassword123!", "password: [REDACTED_PASSWORD]"),
            ("passwd: 'My$ecr3tP@ss'", "passwd: [REDACTED_PASSWORD]"),
            ("pwd=\"hunter2\"", "pwd: [REDACTED_PASSWORD]"),
            ("passphrase = correct-horse-battery-staple", "passphrase: [REDACTED_PASSWORD]"),
        ]
        for original, expected in samples:
            with self.subTest(original=original):
                sanitized = self.redactor.redact_text(original)
                self.assertNotIn("SuperSecretPassword123!", sanitized)
                self.assertNotIn("My$ecr3tP@ss", sanitized)
                self.assertNotIn("hunter2", sanitized)
                self.assertIn("[REDACTED_PASSWORD]", sanitized)

    def test_redact_password_html_input_elements(self) -> None:
        """Asserts <input type='password' value='...'> values in HTML snippets are redacted."""
        html_input = (
            '<form><label>Password</label>'
            '<input type="password" name="user_password" id="pwd_field" value="Secret12345">'
            '<button type="submit">Log In</button></form>'
        )
        sanitized = self.redactor.redact_html(html_input)
        self.assertNotIn("Secret12345", sanitized)
        self.assertIn('value="[REDACTED_PASSWORD]"', sanitized)
        self.assertIn('<button type="submit">Log In</button>', sanitized)

    def test_redact_password_ui_state_node(self) -> None:
        """Asserts UIStateNode for password inputs is sanitized."""
        node = UIStateNode(
            node_id="inp_password",
            role=NodeRole.INPUT,
            bounds=BoundingBox(10, 10, 100, 30),
            label="Enter your password",
            value="P@ssw0rd2026",
            attributes={"type": "password", "name": "password_input"},
        )
        redacted_node = self.redactor.redact_node(node)
        self.assertEqual(redacted_node.value, "[REDACTED_PASSWORD]")
        self.assertEqual(redacted_node.label, "Enter your password")

    def test_redact_password_typed_action(self) -> None:
        """Asserts TypedAction typing into a password field has text_payload scrubbed."""
        action = TypedAction(
            action_type=ActionType.TYPE,
            target_node_id="inp_user_password",
            target_label="Password",
            text_payload="MyTopSecretPassword",
            safety_class=SafetyClass.REVERSIBLE,
            metadata={"is_password": True},
        )
        redacted_action = self.redactor.redact_action(action)
        self.assertEqual(redacted_action.text_payload, "[REDACTED_PASSWORD]")

    # =========================================================================
    # 2. Credit Card & CVV Redaction Tests
    # =========================================================================

    def test_luhn_checksum_helper(self) -> None:
        """Validates Luhn algorithm implementation on test card numbers."""
        # Valid test card (Visa)
        self.assertTrue(_luhn_checksum("4532015112830366"))
        self.assertTrue(_luhn_checksum("4532-0151-1283-0366"))
        # Invalid test card (wrong parity)
        self.assertFalse(_luhn_checksum("4532015112830367"))
        # Too short / too long
        self.assertFalse(_luhn_checksum("12345"))
        self.assertFalse(_luhn_checksum("1234567890123456789012345"))

    def test_redact_credit_card_numbers(self) -> None:
        """Asserts 16-digit credit card numbers are masked with ****-****-****-LAST4."""
        card_text = "Please charge my Visa card 4532 0151 1283 0366 for the order."
        sanitized = self.redactor.redact_text(card_text)
        self.assertNotIn("4532 0151 1283 0366", sanitized)
        self.assertIn("****-****-****-0366", sanitized)

    def test_redact_cvv_codes(self) -> None:
        """Asserts CVV/CVC security codes are scrubbed."""
        samples = [
            ("cvv: 849", "cvv: [REDACTED_CVV]"),
            ("CVC = 123", "CVC: [REDACTED_CVV]"),
            ("security code: 4321", "security code: [REDACTED_CVV]"),
        ]
        for original, _ in samples:
            with self.subTest(original=original):
                sanitized = self.redactor.redact_text(original)
                self.assertNotIn("849", sanitized)
                self.assertNotIn("123", sanitized)
                self.assertNotIn("4321", sanitized)
                self.assertIn("[REDACTED_CVV]", sanitized)

    # =========================================================================
    # 3. Bearer Tokens, API Keys, and Auth Headers
    # =========================================================================

    def test_redact_bearer_token(self) -> None:
        """Asserts Bearer authorization tokens are scrubbed."""
        header = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-IDcSemACt8x4iTpc8yKEJfZrEQbf-r"
        sanitized = self.redactor.redact_text(header)
        self.assertNotIn("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", sanitized)
        self.assertIn("Bearer [REDACTED_TOKEN]", sanitized)

    def test_redact_api_keys(self) -> None:
        """Asserts known vendor API keys (OpenAI, Stripe, GitHub, AWS, Anthropic) are masked."""
        keys = [
            "sk-live12345678901234567890abcdef",
            "ghp_1234567890abcdefghijklmnopqrstuvwxyz",
            "AKIAIOSFODNN7EXAMPLE",
            "sk-ant-api03-1234567890abcdefghijklmnopqrstuv",
        ]
        for key in keys:
            with self.subTest(key=key):
                text = f"Using API key: {key} for authentication."
                sanitized = self.redactor.redact_text(text)
                self.assertNotIn(key, sanitized)
                self.assertIn("[REDACTED_API_KEY]", sanitized)

    # =========================================================================
    # 4. SSN, Cookies, and Emails
    # =========================================================================

    def test_redact_ssn(self) -> None:
        """Asserts Social Security Numbers are redacted."""
        text = "SSN is 000-12-3456 in application."
        sanitized = self.redactor.redact_text(text)
        self.assertNotIn("000-12-3456", sanitized)
        self.assertIn("[REDACTED_SSN]", sanitized)

    def test_redact_session_cookies(self) -> None:
        """Asserts session cookies and cookie headers are redacted."""
        headers = "Set-Cookie: sessionid=9876543210abcdef; HttpOnly; Secure"
        sanitized = self.redactor.redact_text(headers)
        self.assertNotIn("9876543210abcdef", sanitized)
        self.assertIn("Set-Cookie: [REDACTED_COOKIE]", sanitized)

    def test_redact_emails_when_enabled(self) -> None:
        """Asserts email addresses are masked when redact_emails is True."""
        text = "Contact user at admin@example.com for access."
        sanitized = self.redactor.redact_text(text)
        self.assertNotIn("admin@example.com", sanitized)
        self.assertIn("[REDACTED_EMAIL]", sanitized)

    # =========================================================================
    # 5. Metadata & Dictionary Redaction Tests
    # =========================================================================

    def test_redact_nested_dictionary(self) -> None:
        """Asserts nested dictionary keys and string values are sanitized."""
        payload = {
            "session_id": "sess_101",
            "user": {
                "name": "Alice",
                "password": "ClearTextPassword!",
                "api_key": "sk-live12345678901234567890abcdef",
            },
            "tokens": ["Bearer token123456789", "public_id_abc"],
            "metadata": {
                "auth_header": "Authorization: Bearer secrettoken123",
                "non_sensitive": "normal_data",
            },
        }
        sanitized = self.redactor.redact_dict(payload)

        self.assertEqual(sanitized["session_id"], "sess_101")
        self.assertEqual(sanitized["user"]["name"], "Alice")
        self.assertEqual(sanitized["user"]["password"], "[REDACTED]")
        self.assertEqual(sanitized["user"]["api_key"], "[REDACTED]")
        self.assertIn("Bearer [REDACTED_TOKEN]", sanitized["tokens"][0])
        self.assertEqual(sanitized["tokens"][1], "public_id_abc")
        self.assertEqual(sanitized["metadata"]["non_sensitive"], "normal_data")

    # =========================================================================
    # 6. Full TransitionTuple Redaction Test
    # =========================================================================

    def test_redact_transition_tuple(self) -> None:
        """Asserts entire TransitionTuple is safely sanitized before persistence."""
        transition = TransitionTuple(
            transition_id="trans_sensitive_01",
            episode_id="ep_001",
            step_index=0,
            timestamp_ms=1000.0,
            ui_state_hash="hash_origin_123",
            goal_text="Fill password with SuperSecret123! and submit",
            goal_embedding=[0.1, 0.2, 0.3],
            visual_embedding=None,
            action=TypedAction(
                action_type=ActionType.TYPE,
                target_node_id="inp_pass",
                target_label="password",
                text_payload="SuperSecret123!",
                safety_class=SafetyClass.REVERSIBLE,
                metadata={"secret_token": "token_abc123"},
            ),
            next_ui_state_hash="hash_next_456",
            delta=StateDelta(added_nodes=["dashboard_view"], outcome_class=OutcomeClass.SUCCESS),
            duration_ms=50.0,
            surprise_score=0.0,
            provenance={"user_id": "usr_99", "auth_token": "Bearer myauthtoken"},
        )

        redacted_tx = self.redactor.redact_transition(transition)

        # Transition metadata and structural linkage preserved
        self.assertEqual(redacted_tx.transition_id, "trans_sensitive_01")
        self.assertEqual(redacted_tx.ui_state_hash, "hash_origin_123")
        self.assertEqual(redacted_tx.next_ui_state_hash, "hash_next_456")
        self.assertEqual(redacted_tx.goal_embedding, [0.1, 0.2, 0.3])

        # Goal text sanitized
        self.assertNotIn("SuperSecret123!", redacted_tx.goal_text)

        # Action payload and metadata sanitized
        self.assertEqual(redacted_tx.action.text_payload, "[REDACTED_PASSWORD]")
        self.assertEqual(redacted_tx.action.metadata["secret_token"], "[REDACTED]")

        # Provenance sanitized
        self.assertEqual(redacted_tx.provenance["auth_token"], "[REDACTED]")
        self.assertEqual(redacted_tx.provenance["user_id"], "usr_99")


if __name__ == "__main__":
    unittest.main()
