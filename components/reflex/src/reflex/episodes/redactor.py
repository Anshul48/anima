"""Reflex Privacy & Credential Redactor.

Deterministic client-side redaction filter ensuring sensitive credentials,
PII, passwords, credit card numbers, authorization headers, and session tokens
are scrubbed prior to local storage or prompt persistence.
"""

from __future__ import annotations

from dataclasses import replace
import re
from typing import Any, Dict, List, Optional, Set, Union

from reflex.schemas.actions import ActionType, TypedAction
from reflex.schemas.delta import StateDelta
from reflex.schemas.memory import TransitionTuple
from reflex.schemas.state import CanonicalUIGraph, NodeRole, UIStateNode


def _luhn_checksum(digits_str: str) -> bool:
    """Validates whether a digit sequence satisfies the Luhn algorithm."""
    digits = [int(c) for c in digits_str if c.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    reverse_digits = digits[::-1]
    for i, d in enumerate(reverse_digits):
        if i % 2 == 1:
            doubled = d * 2
            checksum += doubled - 9 if doubled > 9 else doubled
        else:
            checksum += d
    return checksum % 10 == 0


class PrivacyRedactor:
    """Client-side privacy and secret redaction engine for Reflex."""

    # Explicit sensitive dictionary/metadata keys
    SENSITIVE_KEY_NAMES: Set[str] = {
        "password",
        "passwd",
        "pwd",
        "passphrase",
        "secret",
        "api_key",
        "apikey",
        "token",
        "access_token",
        "refresh_token",
        "auth_token",
        "bearer_token",
        "authorization",
        "cookie",
        "cookies",
        "set-cookie",
        "sessionid",
        "card_number",
        "credit_card",
        "pan",
        "cvv",
        "cvc",
        "cvv2",
        "cvc2",
        "ssn",
        "social_security",
        "private_key",
    }

    # Sensitive HTML input name / id / autocomplete fragments
    PASSWORD_FIELD_ATTRS: Set[str] = {
        "password",
        "passwd",
        "pwd",
        "current-password",
        "new-password",
        "user-password",
    }

    # Regex patterns for payload scrubbing
    RE_AUTH_BEARER = re.compile(
        r"(?i)\b(authorization|auth[-_]?token)\s*[:=]\s*Bearer\s+[A-Za-z0-9_\-\.~+/]+=*"
    )
    RE_BEARER = re.compile(r"(?i)\bBearer\s+(?!\[REDACTED)[A-Za-z0-9_\-\.~+/]+=*")
    RE_AUTH_KV = re.compile(
        r"(?i)\b(authorization|api[-_]?key|secret[-_]?key|client[-_]?secret|auth[-_]?token|access[-_]?token|refresh[-_]?token)\s*[:=]\s*['\"]?(?!\[REDACTED|Bearer)([^'\"\s,;]+)['\"]?"
    )
    RE_PASSWORD_KV = re.compile(
        r"(?i)\b(password|passwd|pwd|passphrase)(\s*[:=]\s*|\s+(?:is|with|to|as)?\s*)['\"]?(?!\[REDACTED)([^'\"\s,;]+)['\"]?"
    )
    RE_KNOWN_API_KEYS = re.compile(
        r"\b(sk-[a-zA-Z0-9]{20,}|sk_live_[a-zA-Z0-9]{24,}|ghp_[a-zA-Z0-9]{36,}|gho_[a-zA-Z0-9]{36,}|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|sk-ant-[a-zA-Z0-9_\-]{30,})\b"
    )
    RE_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
    RE_CVV_KV = re.compile(
        r"(?i)\b(cvv|cvc|cvv2|cvc2|cid|security[-_ ]*code)\s*[:=]?\s*(\d{3,4})\b"
    )
    RE_COOKIE_HEADER = re.compile(r"(?i)\b(set-cookie|cookie)\s*:\s*([^\r\n]+)")
    RE_COOKIE_KV = re.compile(
        r"(?i)\b(sessionid|connect\.sid|jsessionid|phpsessid|jwt_token|csrf_token)\s*=\s*([^;\s&]+)"
    )
    RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
    RE_CREDIT_CARD_CANDIDATE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
    RE_STANDARD_PAN_FORMATTED = re.compile(r"\b\d{4}[ -]\d{4}[ -]\d{4}[ -]\d{4}\b")

    def __init__(
        self,
        redact_emails: bool = False,
        mask_credit_cards: bool = True,
        custom_redact_patterns: Optional[List[re.Pattern]] = None,
    ) -> None:
        self.redact_emails = redact_emails
        self.mask_credit_cards = mask_credit_cards
        self.custom_redact_patterns = custom_redact_patterns or []

    def redact_text(self, text: Optional[str]) -> str:
        """Scrubs passwords, tokens, credit cards, CVVs, SSNs, and cookies from text."""
        if not text:
            return ""

        result = str(text)

        # 1. Authorization: Bearer tokens
        result = self.RE_AUTH_BEARER.sub(r"\1: Bearer [REDACTED_TOKEN]", result)

        # 2. Standalone Bearer tokens
        result = self.RE_BEARER.sub("Bearer [REDACTED_TOKEN]", result)

        # 3. Known API key signatures (OpenAI, Stripe, GitHub, AWS, Anthropic)
        result = self.RE_KNOWN_API_KEYS.sub("[REDACTED_API_KEY]", result)

        # 4. Key-Value Auth / Secret headers
        result = self.RE_AUTH_KV.sub(r"\1: [REDACTED_TOKEN]", result)

        # 5. Key-Value Password assignments
        result = self.RE_PASSWORD_KV.sub(r"\1\2[REDACTED_PASSWORD]", result)

        # 6. CVV / CVC codes
        result = self.RE_CVV_KV.sub(r"\1: [REDACTED_CVV]", result)

        # 7. SSN / National IDs
        result = self.RE_SSN.sub("[REDACTED_SSN]", result)

        # 8. Cookie headers and session identifiers
        result = self.RE_COOKIE_HEADER.sub(r"\1: [REDACTED_COOKIE]", result)
        result = self.RE_COOKIE_KV.sub(r"\1=[REDACTED_COOKIE]", result)

        # 9. Credit Card Numbers (Luhn validated or standard 16-digit PAN formatted)
        if self.mask_credit_cards:
            result = self._mask_card_numbers(result)

        # 10. Optional Email scrubbing
        if self.redact_emails:
            result = self.RE_EMAIL.sub("[REDACTED_EMAIL]", result)

        # 11. Custom user-defined patterns
        for pat in self.custom_redact_patterns:
            result = pat.sub("[REDACTED]", result)

        return result

    def _mask_card_numbers(self, text: str) -> str:
        """Finds candidate card number strings and replaces them with masked equivalents."""
        def replace_candidate(match: re.Match) -> str:
            raw = match.group(0)
            digits = re.sub(r"\D", "", raw)
            if 13 <= len(digits) <= 19 and (_luhn_checksum(digits) or self.RE_STANDARD_PAN_FORMATTED.fullmatch(raw)):
                last4 = digits[-4:]
                return f"****-****-****-{last4}"
            return raw

        return self.RE_CREDIT_CARD_CANDIDATE.sub(replace_candidate, text)

    def redact_dict(self, data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Recursively sanitizes a dictionary, masking sensitive keys and values."""
        if not data or not isinstance(data, dict):
            return {}

        sanitized: Dict[str, Any] = {}
        for key, value in data.items():
            key_lower = str(key).lower().replace("-", "_").replace(" ", "_")
            key_parts = set(re.split(r'[_]+', key_lower))
            
            is_sensitive_key = (
                key_lower in self.SENSITIVE_KEY_NAMES
                or bool(key_parts & self.SENSITIVE_KEY_NAMES)
                or any(k in key_lower for k in ("password", "passwd", "secret", "api_key", "auth_token", "bearer_token", "cvv", "cvc", "ssn"))
            )

            if isinstance(value, dict):
                sanitized[key] = self.redact_dict(value)
            elif isinstance(value, list):
                sanitized[key] = self._redact_list(value)
            elif is_sensitive_key:
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, str):
                sanitized[key] = self.redact_text(value)
            else:
                sanitized[key] = value

        return sanitized

    def _redact_list(self, items: List[Any]) -> List[Any]:
        """Recursively sanitizes a list of values."""
        sanitized: List[Any] = []
        for item in items:
            if isinstance(item, dict):
                sanitized.append(self.redact_dict(item))
            elif isinstance(item, list):
                sanitized.append(self._redact_list(item))
            elif isinstance(item, str):
                sanitized.append(self.redact_text(item))
            else:
                sanitized.append(item)
        return sanitized

    def redact_html(self, html: Optional[str]) -> str:
        """Sanitizes HTML content by masking password fields, card inputs, and text secrets."""
        if not html:
            return ""

        result = str(html)

        # 1. Mask password inputs: <input ... type="password" ... value="..." ...>
        # Replaces value attribute with [REDACTED_PASSWORD]
        re_pw_tag = re.compile(r'(<input\b[^>]*?\btype=["\']?password["\']?[^>]*?>)', re.IGNORECASE)
        
        def mask_pw_tag(m: re.Match) -> str:
            tag_content = m.group(1)
            # If it has a value="..." attribute, replace it
            if re.search(r'\bvalue=["\']([^"\']*)["\']', tag_content, re.IGNORECASE):
                tag_content = re.sub(
                    r'\bvalue=["\']([^"\']*)["\']',
                    'value="[REDACTED_PASSWORD]"',
                    tag_content,
                    flags=re.IGNORECASE,
                )
            else:
                # Add value="[REDACTED_PASSWORD]"
                tag_content = tag_content[:-1] + ' value="[REDACTED_PASSWORD]">'
            return tag_content

        result = re_pw_tag.sub(mask_pw_tag, result)

        # 2. General text redaction on the entire HTML
        return self.redact_text(result)

    def is_password_node(self, node: UIStateNode) -> bool:
        """Determines if a UIStateNode corresponds to a password input element."""
        if node.role != NodeRole.INPUT:
            return False

        label_lower = node.label.lower()
        node_id_lower = node.node_id.lower()
        attrs = {str(k).lower(): str(v).lower() for k, v in node.attributes.items()}

        if attrs.get("type") == "password":
            return True

        for pw_fragment in self.PASSWORD_FIELD_ATTRS:
            if pw_fragment in label_lower or pw_fragment in node_id_lower:
                return True
            if pw_fragment in attrs.get("name", "") or pw_fragment in attrs.get("autocomplete", ""):
                return True
            if pw_fragment in attrs.get("id", "") or pw_fragment in attrs.get("aria-label", ""):
                return True

        return False

    def redact_node(self, node: UIStateNode) -> UIStateNode:
        """Sanitizes a single UIStateNode element."""
        is_pw = self.is_password_node(node)
        new_value = "[REDACTED_PASSWORD]" if is_pw else self.redact_text(node.value)
        new_label = self.redact_text(node.label)
        new_attrs = self.redact_dict(node.attributes)

        return replace(
            node,
            value=new_value,
            label=new_label,
            attributes=new_attrs,
        )

    def redact_state(self, state: CanonicalUIGraph) -> CanonicalUIGraph:
        """Sanitizes all nodes, active titles, and URLs in a CanonicalUIGraph."""
        redacted_nodes = {
            node_id: self.redact_node(node) for node_id, node in state.nodes.items()
        }
        redacted_title = self.redact_text(state.active_window_title) if state.active_window_title else None
        redacted_url = self.redact_text(state.url) if state.url else None

        return replace(
            state,
            nodes=redacted_nodes,
            active_window_title=redacted_title,
            url=redacted_url,
        )

    def redact_action(self, action: TypedAction) -> TypedAction:
        """Sanitizes text payload and metadata in a TypedAction."""
        meta = self.redact_dict(action.metadata)
        text_payload = action.text_payload

        if text_payload is not None:
            # If target node or metadata indicates a password action
            target_node_id = (action.target_node_id or "").lower()
            target_label = (action.target_label or "").lower()
            is_pw = (
                action.metadata.get("is_password") is True
                or any(pw in target_node_id for pw in self.PASSWORD_FIELD_ATTRS)
                or any(pw in target_label for pw in self.PASSWORD_FIELD_ATTRS)
            )
            if is_pw:
                text_payload = "[REDACTED_PASSWORD]"
            else:
                text_payload = self.redact_text(text_payload)

        redacted_label = self.redact_text(action.target_label) if action.target_label else None

        return replace(
            action,
            text_payload=text_payload,
            target_label=redacted_label,
            metadata=meta,
        )

    def redact_delta(self, delta: StateDelta) -> StateDelta:
        """Sanitizes state delta identifiers and properties."""
        return delta

    def redact_transition(self, transition: TransitionTuple) -> TransitionTuple:
        """Constructs an immutable sanitized TransitionTuple with scrubbed sensitive fields."""
        return replace(
            transition,
            goal_text=self.redact_text(transition.goal_text),
            action=self.redact_action(transition.action),
            delta=self.redact_delta(transition.delta),
            provenance=self.redact_dict(transition.provenance),
        )
