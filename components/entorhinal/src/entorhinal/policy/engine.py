"""Deterministic Policy Engine for Entorhinal.

Enforces:
1. Pre-storage consent checking (app, domain, and source type gating).
2. Multi-pass deterministic credential masking and PII redaction.
3. Strict data classification tagging (PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED, PROHIBITED).
4. Consumer query scope authorization.
5. ContextSnapshot sanitization and token budget pruning.
6. Redacted tamper-evident audit event generation.

Fail-closed invariant: Any policy evaluation error defaults to permitted=False.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import fnmatch
import json
import re
from typing import Any, Dict, List, Optional, Pattern, Set, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from entorhinal.schemas.models import (
    ClassificationLevel,
    ContextRequest,
    ContextSnapshot,
    DerivedFact,
    Hypothesis,
    PolicyDecision,
    RawSignalEvent,
    SnapshotBudget,
    SourceType,
    fact_matches_scope,
    fact_tier_rank,
    generate_uuidv7,
)


# ==============================================================================
# Deterministic Redaction Regex Patterns
# ==============================================================================

# AWS Access Key IDs (AKIA, ASIA, ABIA, ACCA followed by 16 alphanumerics)
REGEX_AWS_KEY: Pattern[str] = re.compile(
    r"\b((?:AKIA|ASIA|ABIA|ACCA)[0-9A-Z]{16})\b"
)

# AWS Secret Access Keys in key-value context
REGEX_AWS_SECRET: Pattern[str] = re.compile(
    r"(?i)(?:aws_secret_access_key|aws_secret_key|aws_access_secret|secret_key)\s*[:=]\s*['\"]?([a-zA-Z0-9/+=]{40})['\"]?"
)

# GitHub Tokens (Classic PAT, OAuth, User-to-Server, Server-to-Server, Refresh, Fine-Grained)
REGEX_GITHUB_TOKEN: Pattern[str] = re.compile(
    r"\b((?:ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9]{20,40}|github_pat_[a-zA-Z0-9_]{22,255})\b"
)

# Slack API Tokens (xoxb, xoxp, xoxa, xoxr, xoxs)
REGEX_SLACK_TOKEN: Pattern[str] = re.compile(
    r"\b(xox[baprs]-[0-9a-zA-Z]{10,48}(?:-[0-9a-zA-Z]{10,48})*)\b"
)

# OpenAI API Keys
REGEX_OPENAI_KEY: Pattern[str] = re.compile(
    r"\b(sk-(?:proj-)?[a-zA-Z0-9_-]{20,100})\b"
)

# Stripe API Keys (secret, restricted, publishable live/test)
REGEX_STRIPE_KEY: Pattern[str] = re.compile(
    r"\b((?:sk|rk|pk)_(?:test|live)_[0-9a-zA-Z]{24,100})\b"
)

# JSON Web Tokens (JWT)
REGEX_JWT: Pattern[str] = re.compile(
    r"\b(eyJ[A-Za-z0-9-_=]+\.eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_.+/=]*)\b"
)

# Private Keys (RSA, EC, DSA, OPENSSH, PGP, generic)
REGEX_PRIVATE_KEY: Pattern[str] = re.compile(
    r"-----BEGIN (?:[A-Z0-9_-]+ )?PRIVATE KEY-----[\s\S]*?-----END (?:[A-Z0-9_-]+ )?PRIVATE KEY-----",
    re.MULTILINE
)

# Generic Bearer Tokens
REGEX_BEARER_TOKEN: Pattern[str] = re.compile(
    r"(?i)\bBearer\s+([a-zA-Z0-9_\-\.]{20,})\b"
)

# Sensitive Key-Value assignments in text/logs
REGEX_KV_CREDENTIAL: Pattern[str] = re.compile(
    r"(?i)\b(?:[a-zA-Z0-9_\-\.]*(?:password|passwd|pwd|api[-_]?key|secret[-_]?key|access[-_]?token|auth[-_]?token|client[-_]?secret|secret|token|credential))\s*[:=]\s*['\"]?([^'\"\s]{6,})['\"]?"
)

# US Social Security Numbers (SSN)
REGEX_SSN: Pattern[str] = re.compile(
    r"\b\d{3}-\d{2}-\d{4}\b"
)

# Credit Card Numbers (13 to 19 digits, with optional hyphens or spaces)
REGEX_CREDIT_CARD: Pattern[str] = re.compile(
    r"\b(?:\d{4}[ -]?){3}\d{4}\b|\b\d{13,19}\b"
)

# Email Addresses
REGEX_EMAIL: Pattern[str] = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

# Sensitive Dictionary Keys
SENSITIVE_KEY_NAMES: Set[str] = {
    "password", "passwd", "pwd", "secret", "client_secret", "api_key", "apikey",
    "access_token", "auth_token", "authorization", "auth", "bearer", "cookie",
    "set-cookie", "private_key", "privatekey", "ssh_key", "ssn", "credit_card",
    "card_number", "cvv", "cvc", "session_token", "sessionid", "proxy-authorization",
    "stripe_secret", "otp_field", "secret_container", "token_container", "credential"
}


def is_sensitive_key(key: str) -> bool:
    """Accurately detect sensitive dictionary key names without false positives on words like 'authors'."""
    k_lower = key.lower().strip().replace("-", "_")
    if k_lower in SENSITIVE_KEY_NAMES:
        return True
    tokens = set(k_lower.split("_"))
    sensitive_tokens = {
        "password", "passwd", "pwd", "secret", "apikey", "authorization",
        "ssn", "cvv", "cvc", "sessionid", "cookie", "token", "credential", "private"
    }
    if tokens & sensitive_tokens:
        return True
    if any(k_lower.startswith(prefix) or k_lower.endswith(prefix) for prefix in (
        "auth_token", "access_token", "refresh_token", "api_key", "private_key", "client_secret", "session_token", "secret_key"
    )):
        return True
    return False

# Default Process Blacklist (Hard Deny - Never persist password managers or keychains)
DEFAULT_APP_BLACKLIST: Set[str] = {
    "1password", "1password.exe", "1password 7", "1password 8",
    "keepass", "keepass.exe", "keepassxc", "keepassxc.exe",
    "bitwarden", "bitwarden.exe", "lastpass", "lastpass.exe",
    "dashlane", "dashlane.exe", "keychain access", "gnome-keyring",
    "kwallet", "authy", "yubikey authenticator"
}

# Default Domain Blacklist (Hard Deny - Sensitive auth and banking portals)
DEFAULT_DOMAIN_BLACKLIST: Set[str] = {
    "*banking*", "*login.microsoftonline.com*", "*accounts.google.com*",
    "*login.live.com*", "*auth0.com*", "*signin*", "*chase.com*",
    "*wellsfargo.com*", "*bankofamerica.com*", "*paypal.com/signin*"
}


# ==============================================================================
# Consent & Consumer Rule Definitions
# ==============================================================================

@dataclass
class ConsentRule:
    """User-configured consent grant or denial rule."""
    rule_id: str = field(default_factory=generate_uuidv7)
    source_type: Optional[SourceType] = None
    app_pattern: Optional[str] = None
    domain_pattern: Optional[str] = None
    allow: bool = True
    priority: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ConsumerPermission:
    """Authorized scopes for a specific downstream consumer."""
    consumer_id: str
    allowed_purposes: List[str]
    allowed_scopes: List[str]
    max_budget: int = 4096


# ==============================================================================
# Delivered-serialization budget counter (F4)
# ==============================================================================

#: Identified counters for budget accounting. Tiktoken o200k_base is primary
#: (qualified in .venv-linux); the deterministic regex counter is the
#: disclosed fallback when tiktoken is unavailable.
TOKENIZER_TIKTOKEN_O200K = "tiktoken/o200k_base"
TOKENIZER_REGEX_FALLBACK = "m2-regex-v1"
_TOKEN_RE = re.compile(r"\w+|[^\w\s]")
_tiktoken_encoding: Any = None
_tiktoken_unavailable = False


class BudgetExceededError(ValueError):
    """Raised when even the minimum envelope cannot fit the declared budget."""

    def __init__(
        self,
        message: str,
        *,
        budget_tokens: int,
        used_tokens: int,
        used_chars: int,
        tokenizer: str,
    ) -> None:
        super().__init__(message)
        self.budget_tokens = budget_tokens
        self.used_tokens = used_tokens
        self.used_chars = used_chars
        self.tokenizer = tokenizer


def warm_budget_counter() -> str:
    """Pre-load the identified token counter (one-time per process).

    Tiktoken's encoding load costs ~1s on first use; call this at startup
    (PolicyEngine construction does) so request-path counting stays fast.
    Returns the active tokenizer id.
    """
    global _tiktoken_encoding, _tiktoken_unavailable
    if _tiktoken_encoding is None and not _tiktoken_unavailable:
        try:
            import tiktoken  # type: ignore[import-not-found]

            _tiktoken_encoding = tiktoken.get_encoding("o200k_base")
            _tiktoken_encoding.encode("entorhinal warmup")
        except Exception:
            _tiktoken_unavailable = True
    return TOKENIZER_TIKTOKEN_O200K if _tiktoken_encoding is not None else TOKENIZER_REGEX_FALLBACK


def count_budget_tokens(text: str) -> Tuple[int, str]:
    """Count tokens in delivered text with the identified counter.

    Returns (count, tokenizer_id). Primary: tiktoken o200k_base.
    Fallback: deterministic ``\\w+`` words + single symbols (``m2-regex-v1``).
    """
    global _tiktoken_encoding, _tiktoken_unavailable
    if _tiktoken_encoding is None and not _tiktoken_unavailable:
        warm_budget_counter()
    if _tiktoken_encoding is not None:
        try:
            return len(_tiktoken_encoding.encode(text)), TOKENIZER_TIKTOKEN_O200K
        except Exception:
            _tiktoken_unavailable = True
    return len(_TOKEN_RE.findall(text)), TOKENIZER_REGEX_FALLBACK


def canonical_snapshot_json(snapshot: ContextSnapshot) -> str:
    """Canonical consumer serialization of a snapshot (what budgets count).

    Compact JSON with sorted keys over the JSON-mode model dump. Deterministic
    across processes; within framing bytes of the delivered HTTP body.
    """
    return json.dumps(
        snapshot.model_dump(mode="json", by_alias=True),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


#: Bound on retained per-item `pruned_*` manifest entries. Past the cap, the
#: oldest entries compact into one disclosed summary so the audit trail cannot
#: itself crowd content out of the budget. Mirrors the packet omission ledger.
PRUNE_MANIFEST_MAX_ENTRIES = 12
#: Floor the ledger yields to under token-budget pressure before content is
#: sacrificed (and before declaring the minimum envelope over budget).
PRUNE_MANIFEST_MIN_KEPT = 3


def compact_prune_manifest(entries: List[str], max_entries: int = PRUNE_MANIFEST_MAX_ENTRIES) -> List[str]:
    """Bound `pruned_*` manifest entries with a disclosed compacted summary.

    Non-prune entries (redaction paths, exclusion counts) pass through
    untouched. Prune entries beyond the cap fold into one summary entry that
    preserves per-family counts; the most recent prunes are retained longest.
    """
    kept: List[str] = [e for e in entries if not e.startswith("pruned_")]
    prunes: List[str] = [e for e in entries if e.startswith("pruned_")]
    if len(prunes) <= max_entries:
        return kept + prunes
    # Never re-compact an existing summary: unfold its counts first.
    unfolded: List[str] = []
    carried: Dict[str, int] = {}
    for entry in prunes:
        if entry.startswith("pruned_compacted:"):
            for chunk in entry.split(":", 1)[1].split(","):
                if "=" in chunk:
                    family, _, count = chunk.partition("=")
                    try:
                        carried[family] = carried.get(family, 0) + int(count)
                    except ValueError:
                        continue
        else:
            unfolded.append(entry)
    total_dropped = len(unfolded) - (max_entries - 1)
    retained = unfolded[-(max_entries - 1):] if max_entries > 1 else []
    families: Dict[str, int] = dict(carried)
    for entry in unfolded[:total_dropped]:
        family = entry.split(":", 1)[0]
        families[family] = families.get(family, 0) + 1
    summary = "pruned_compacted:" + ",".join(
        f"{family}={families[family]}" for family in sorted(families)
    )
    return kept + [summary] + retained


# ==============================================================================
# Policy Engine Implementation
# ==============================================================================

class PolicyEngine:
    """Comprehensive policy and redaction engine for Entorhinal."""

    def __init__(
        self,
        default_allow: bool = True,
        app_blacklist: Optional[Set[str]] = None,
        domain_blacklist: Optional[Set[str]] = None,
        redact_emails_in_private_context: bool = True,
    ) -> None:
        self.default_allow = default_allow
        self.app_blacklist = set(app_blacklist) if app_blacklist is not None else set(DEFAULT_APP_BLACKLIST)
        self.domain_blacklist = set(domain_blacklist) if domain_blacklist is not None else set(DEFAULT_DOMAIN_BLACKLIST)
        self.redact_emails_in_private_context = redact_emails_in_private_context

        self.consent_rules: List[ConsentRule] = []
        self.consumer_permissions: Dict[str, ConsumerPermission] = {}
        self.audit_log: List[Dict[str, Any]] = []

        # Configure default approved consumers (e.g. reflex planner)
        self._register_default_consumer_permissions()

        # Pre-load the budget counter once per process so the first
        # sanitized snapshot does not pay the encoding-load latency.
        try:
            warm_budget_counter()
        except Exception:
            pass

    def _register_default_consumer_permissions(self) -> None:
        """Register default approved consumers with EXPLICIT purposes/scopes.

        There is no implicit wildcard grant: a caller holding no explicit
        permission for a purpose/scope is denied. An explicit ``"*"`` grant
        remains honored when deliberately persisted (e.g. via AuthStore).
        """
        self.consumer_permissions["reflex.system2.planner"] = ConsumerPermission(
            consumer_id="reflex.system2.planner",
            allowed_purposes=[
                "Resolve active repository branch and target issue ID",
                "Resolve active repository branch and target issue ID for user command 'fix the login button bug'",
                "Context for task planning",
            ],
            allowed_scopes=[
                "scope:workspace.active_project",
                "scope:browser.recent_tabs",
                "scope:terminal.last_commands",
                "scope:workspace.*",
                "scope:browser.*",
                "scope:terminal.*",
                "scope:developer.*",
            ],
            max_budget=4096,
        )

    def register_consumer_permission(self, permission: ConsumerPermission) -> None:
        """Register (or replace) one consumer's explicit purpose/scope grant."""
        self.consumer_permissions[permission.consumer_id] = ConsumerPermission(
            consumer_id=permission.consumer_id,
            allowed_purposes=list(permission.allowed_purposes),
            allowed_scopes=list(permission.allowed_scopes),
            max_budget=permission.max_budget,
        )
        self._record_audit_event(
            "REGISTER_CONSUMER_PERMISSION", f"consumer_id={permission.consumer_id}"
        )

    def remove_consumer_permission(self, consumer_id: str) -> bool:
        """Remove one consumer's grant; afterwards the consumer is unknown."""
        if consumer_id not in self.consumer_permissions:
            return False
        del self.consumer_permissions[consumer_id]
        self._record_audit_event(
            "REMOVE_CONSUMER_PERMISSION", f"consumer_id={consumer_id}"
        )
        return True

    # --------------------------------------------------------------------------
    # Consent Management
    # --------------------------------------------------------------------------

    def add_consent_rule(
        self,
        allow: bool,
        source_type: Optional[SourceType] = None,
        app_pattern: Optional[str] = None,
        domain_pattern: Optional[str] = None,
        priority: int = 0,
    ) -> str:
        """Add an explicit user consent grant or deny rule."""
        rule = ConsentRule(
            source_type=source_type,
            app_pattern=app_pattern,
            domain_pattern=domain_pattern,
            allow=allow,
            priority=priority,
        )
        self.consent_rules.append(rule)
        # Sort rules descending by priority
        self.consent_rules.sort(key=lambda r: r.priority, reverse=True)
        self._record_audit_event("ADD_CONSENT_RULE", f"rule_id={rule.rule_id}, allow={allow}")
        return rule.rule_id

    def remove_consent_rule(self, rule_id: str) -> bool:
        """Remove a consent rule by ID."""
        initial_len = len(self.consent_rules)
        self.consent_rules = [r for r in self.consent_rules if r.rule_id != rule_id]
        removed = len(self.consent_rules) < initial_len
        if removed:
            self._record_audit_event("REMOVE_CONSENT_RULE", f"rule_id={rule_id}")
        return removed

    @staticmethod
    def _has_wildcards(pattern: str) -> bool:
        return "*" in pattern or "?" in pattern or "[" in pattern

    def is_blacklisted_app(self, app_identifier: str, window_title: Optional[str] = None) -> bool:
        """Check if an application or window matches the hard blacklists."""
        app_lower = app_identifier.lower().strip()
        for bl in self.app_blacklist:
            bl_lower = bl.lower().strip()
            # NOTE: fnmatch without wildcard chars is equality, which the
            # substring check already covers; skipping it is identical.
            if bl_lower in app_lower or (
                self._has_wildcards(bl_lower) and fnmatch.fnmatch(app_lower, bl_lower)
            ):
                return True

        if window_title:
            win_lower = window_title.lower()
            for bl in self.app_blacklist:
                bl_lower = bl.lower().strip()
                if bl_lower in win_lower:
                    return True

        return False

    def is_blacklisted_domain(self, target_uri: Optional[str]) -> bool:
        """Check if a target URI matches blacklisted sensitive domains."""
        if not target_uri:
            return False

        uri_lower = target_uri.lower().strip()
        try:
            parsed = urlparse(uri_lower)
            hostname = parsed.netloc or parsed.path
        except Exception:
            hostname = uri_lower

        for pattern in self.domain_blacklist:
            pat_lower = pattern.lower().strip()
            # NOTE: fnmatch runs only for real glob patterns; for plain text
            # equality/host-equality both imply the substring check below, so
            # skipping them is identical.
            if self._has_wildcards(pat_lower):
                if fnmatch.fnmatch(uri_lower, pat_lower) or fnmatch.fnmatch(hostname, pat_lower):
                    return True
            if "*" not in pat_lower and pat_lower in uri_lower:
                return True

        return False

    def is_consented(
        self,
        source_type: SourceType,
        app_identifier: str,
        target_uri: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Evaluate whether a signal has user consent.

        Returns (permitted, reason).
        """
        # 1. Check Incognito browsing flags
        if metadata:
            if metadata.get("is_incognito") is True:
                return False, "Incognito browsing session suppressed by policy"

        # 2. Check App Blacklist
        if self.is_blacklisted_app(app_identifier):
            return False, f"Application '{app_identifier}' is blacklisted"

        # 3. Check Domain Blacklist
        if target_uri and self.is_blacklisted_domain(target_uri):
            clean_u, _ = self.sanitize_uri(target_uri)
            return False, f"Domain/URI '{clean_u}' is blacklisted"

        # 4. Check explicit user consent rules in priority order
        app_clean = app_identifier.lower()
        uri_clean = (target_uri or "").lower()

        for rule in self.consent_rules:
            # Check source_type match
            if rule.source_type is not None and rule.source_type != source_type:
                continue

            # Check app pattern match
            if rule.app_pattern is not None:
                if not fnmatch.fnmatch(app_clean, rule.app_pattern.lower()):
                    continue

            # Check domain pattern match
            if rule.domain_pattern is not None:
                if not fnmatch.fnmatch(uri_clean, rule.domain_pattern.lower()):
                    continue

            # If all specified criteria matched, apply rule
            if not rule.allow:
                return False, f"Explicit user deny rule matched ({rule.rule_id})"
            return True, f"Explicit user allow rule matched ({rule.rule_id})"

        # 5. Default policy fallback
        if not self.default_allow:
            return False, "Default deny policy (no explicit allow rule matched)"

        return True, "Default allow policy"

    # --------------------------------------------------------------------------
    # Multi-Pass Redaction Engine
    # --------------------------------------------------------------------------

    def redact_text(self, text: str, is_private_context: bool = False) -> Tuple[str, List[str]]:
        """Run deterministic multi-pass regex redaction on a string.

        Returns (redacted_text, list_of_redacted_patterns).
        """
        if not text or not isinstance(text, str):
            return text, []

        redacted_items: List[str] = []
        result = text

        # 1. Private RSA/EC/SSH Keys
        if "-----BEGIN" in result and "KEY-----" in result:
            def _replace_pkey(m: re.Match) -> str:
                redacted_items.append("private_key_block")
                return "<REDACTED:PRIVATE_KEY>"
            result = REGEX_PRIVATE_KEY.sub(_replace_pkey, result)

        # 2. AWS Secret Access Keys in key-value format
        def _replace_aws_secret(m: re.Match) -> str:
            redacted_items.append("aws_secret_key")
            prefix = m.group(0)[:m.start(1) - m.start(0)]
            suffix = m.group(0)[m.end(1) - m.start(0):]
            return f"{prefix}<REDACTED:AWS_SECRET_KEY>{suffix}"
        result = REGEX_AWS_SECRET.sub(_replace_aws_secret, result)

        # 3. AWS Access Key IDs
        def _replace_aws_key(m: re.Match) -> str:
            redacted_items.append("aws_access_key")
            return "<REDACTED:AWS_KEY>"
        result = REGEX_AWS_KEY.sub(_replace_aws_key, result)

        # 4. GitHub Tokens
        def _replace_gh(m: re.Match) -> str:
            redacted_items.append("github_token")
            return "<REDACTED:GITHUB_TOKEN>"
        result = REGEX_GITHUB_TOKEN.sub(_replace_gh, result)

        # 5. Slack Tokens
        def _replace_slack(m: re.Match) -> str:
            redacted_items.append("slack_token")
            return "<REDACTED:SLACK_TOKEN>"
        result = REGEX_SLACK_TOKEN.sub(_replace_slack, result)

        # 6. OpenAI API Keys
        def _replace_openai(m: re.Match) -> str:
            redacted_items.append("openai_api_key")
            return "<REDACTED:OPENAI_API_KEY>"
        result = REGEX_OPENAI_KEY.sub(_replace_openai, result)

        # 7. Stripe API Keys
        def _replace_stripe(m: re.Match) -> str:
            redacted_items.append("stripe_api_key")
            return "<REDACTED:STRIPE_KEY>"
        result = REGEX_STRIPE_KEY.sub(_replace_stripe, result)

        # 8. JWT Tokens
        def _replace_jwt(m: re.Match) -> str:
            redacted_items.append("jwt_token")
            return "<REDACTED:JWT>"
        result = REGEX_JWT.sub(_replace_jwt, result)

        # 9. Generic Bearer Tokens
        def _replace_bearer(m: re.Match) -> str:
            redacted_items.append("bearer_token")
            return "Bearer <REDACTED:BEARER_TOKEN>"
        result = REGEX_BEARER_TOKEN.sub(_replace_bearer, result)

        # 10. Key-Value credential assignments
        def _replace_kv(m: re.Match) -> str:
            redacted_items.append("key_value_credential")
            prefix = m.group(0)[:m.start(1) - m.start(0)]
            suffix = m.group(0)[m.end(1) - m.start(0):]
            return f"{prefix}<REDACTED:CREDENTIAL>{suffix}"
        result = REGEX_KV_CREDENTIAL.sub(_replace_kv, result)

        # 11. US Social Security Numbers
        def _replace_ssn(m: re.Match) -> str:
            redacted_items.append("ssn")
            return "<REDACTED:SSN>"
        result = REGEX_SSN.sub(_replace_ssn, result)

        # 12. Credit Card Numbers
        def _replace_cc(m: re.Match) -> str:
            # Check length of digits
            digits_only = re.sub(r"\D", "", m.group(0))
            if 13 <= len(digits_only) <= 19:
                redacted_items.append("credit_card_number")
                return "<REDACTED:CREDIT_CARD>"
            return m.group(0)
        result = REGEX_CREDIT_CARD.sub(_replace_cc, result)

        # 13. Emails (if private context or requested)
        if is_private_context or self.redact_emails_in_private_context:
            def _replace_email(m: re.Match) -> str:
                # Do not redact if looks like standard system sender (e.g. noreply@github.com) in non-private
                email = m.group(0)
                if is_private_context:
                    redacted_items.append("email_address")
                    return "<REDACTED:EMAIL>"
                return email
            if is_private_context:
                result = REGEX_EMAIL.sub(_replace_email, result)

        return result, redacted_items

    def sanitize_uri(self, uri: Optional[str]) -> Tuple[Optional[str], List[str]]:
        """Sanitize credentials or query tokens from a URI."""
        if not uri:
            return uri, []

        redacted_items: List[str] = []
        try:
            parsed = urlparse(uri)
            # Check for basic auth in netloc: http://user:pass@host
            netloc = parsed.netloc
            if "@" in netloc:
                userinfo, host = netloc.split("@", 1)
                netloc = f"<REDACTED:CREDENTIAL>@{host}"
                redacted_items.append("uri_basic_auth")

            # Check query parameters
            query_params = parse_qsl(parsed.query, keep_blank_values=True)
            sanitized_params = []
            for k, v in query_params:
                k_lower = k.lower()
                if any(sk in k_lower for sk in ("token", "key", "auth", "secret", "password", "signature", "jwt")):
                    sanitized_params.append((k, "<REDACTED:CREDENTIAL>"))
                    redacted_items.append(f"query_param.{k}")
                else:
                    clean_v, v_redacted = self.redact_text(v)
                    if v_redacted:
                        redacted_items.extend([f"query_param.{k}:{r}" for r in v_redacted])
                    sanitized_params.append((k, clean_v))

            new_query = urlencode(sanitized_params)
            clean_uri = urlunparse((
                parsed.scheme,
                netloc,
                parsed.path,
                parsed.params,
                new_query,
                parsed.fragment,
            ))
            return clean_uri, redacted_items
        except Exception:
            clean_text, text_redacted = self.redact_text(uri)
            return clean_text, text_redacted

    def sanitize_payload(
        self,
        payload: Any,
        parent_path: str = "",
        is_private_context: bool = False,
    ) -> Tuple[Any, List[str]]:
        """Recursively sanitize structured dictionaries, lists, and primitives."""
        redacted_paths: List[str] = []

        if isinstance(payload, dict):
            clean_dict: Dict[str, Any] = {}
            for k, v in payload.items():
                current_path = f"{parent_path}.{k}" if parent_path else k

                # Check if dictionary key is a known sensitive credential container
                if is_sensitive_key(str(k)):
                    if isinstance(v, str):
                        clean_v, specific_redactions = self.redact_text(v, is_private_context=is_private_context)
                        if specific_redactions:
                            clean_dict[k] = clean_v
                            redacted_paths.append(current_path)
                            redacted_paths.extend([f"{current_path}:{r}" for r in specific_redactions])
                        else:
                            clean_dict[k] = "<REDACTED:CREDENTIAL>"
                            redacted_paths.append(current_path)
                    else:
                        clean_dict[k] = "<REDACTED:CREDENTIAL>"
                        redacted_paths.append(current_path)
                else:
                    child_val, child_redacted = self.sanitize_payload(
                        v,
                        parent_path=current_path,
                        is_private_context=is_private_context
                    )
                    clean_dict[k] = child_val
                    redacted_paths.extend(child_redacted)
            return clean_dict, redacted_paths

        elif isinstance(payload, list):
            clean_list: List[Any] = []
            for i, item in enumerate(payload):
                current_path = f"{parent_path}[{i}]"
                child_val, child_redacted = self.sanitize_payload(
                    item,
                    parent_path=current_path,
                    is_private_context=is_private_context
                )
                clean_list.append(child_val)
                redacted_paths.extend(child_redacted)
            return clean_list, redacted_paths

        elif isinstance(payload, str):
            clean_str, str_redacted = self.redact_text(payload, is_private_context=is_private_context)
            if str_redacted:
                redacted_paths.append(parent_path or "text")
            return clean_str, redacted_paths

        else:
            return payload, []

    # --------------------------------------------------------------------------
    # Classification Assignment
    # --------------------------------------------------------------------------

    def assign_classification(
        self,
        source_type: SourceType,
        app_identifier: str,
        target_uri: Optional[str],
        had_redactions: bool,
        is_permitted: bool,
    ) -> ClassificationLevel:
        """Determine data classification level based on source, target, and redactions."""
        if not is_permitted:
            return ClassificationLevel.PROHIBITED

        if had_redactions:
            return ClassificationLevel.RESTRICTED

        app_lower = app_identifier.lower()
        uri_lower = (target_uri or "").lower()

        # Public documentation / open repositories / package registries
        public_domains = (
            "github.com", "arxiv.org", "wikipedia.org", "python.org",
            "pypi.org", "docker.com", "docs.rs", "crates.io", "rust-lang.org",
            "stackoverflow.com", "developer.mozilla.org"
        )
        if any(dom in uri_lower for dom in public_domains):
            return ClassificationLevel.PUBLIC

        # Private / confidential channels
        confidential_apps = ("slack", "discord", "signal", "telegram", "mail", "outlook", "notes", "scratchpad")
        if any(app in app_lower for app in confidential_apps):
            return ClassificationLevel.CONFIDENTIAL

        if source_type in (SourceType.USER_INPUT, SourceType.CALENDAR):
            return ClassificationLevel.CONFIDENTIAL

        return ClassificationLevel.INTERNAL

    # --------------------------------------------------------------------------
    # Signal Evaluation Gate
    # --------------------------------------------------------------------------

    def evaluate_signal(self, signal: RawSignalEvent) -> PolicyDecision:
        """Evaluate consent grants, blacklists, and apply real-time PII redaction.

        Guarantees fail-closed behavior on unhandled exceptions.
        """
        audit_id = generate_uuidv7()
        violations: List[str] = []
        redacted_fields: List[str] = []

        try:
            # 1. Evaluate consent & blacklists
            permitted, reason = self.is_consented(
                source_type=signal.source_type,
                app_identifier=signal.app_identifier,
                target_uri=signal.target_uri,
                metadata=signal.metadata,
            )

            if not permitted:
                violations.append(reason or "Consent denied")
                clean_rej_uri = self.sanitize_uri(signal.target_uri)[0] if signal.target_uri else None
                self._record_audit_event(
                    "SIGNAL_REJECTED",
                    f"app={signal.app_identifier}, uri={clean_rej_uri}, reason={reason}",
                    permitted=False,
                )
                return PolicyDecision(
                    permitted=False,
                    classification=ClassificationLevel.PROHIBITED,
                    redacted_payload=None,
                    sanitized_window_title=None,
                    sanitized_target_uri=clean_rej_uri,
                    violations=violations,
                    redacted_fields=[],
                    audit_event_id=audit_id,
                )

            # 2. Sanitize window title & URI
            is_private = bool(
                signal.metadata.get("is_private")
                or "mail" in signal.app_identifier.lower()
                or "chat" in signal.app_identifier.lower()
            )

            clean_window_title = signal.window_title
            if signal.window_title:
                clean_window_title, title_redactions = self.redact_text(signal.window_title, is_private_context=is_private)
                if title_redactions:
                    redacted_fields.append("window_title")

            clean_target_uri = signal.target_uri
            if signal.target_uri:
                clean_target_uri, uri_redactions = self.sanitize_uri(signal.target_uri)
                if uri_redactions:
                    redacted_fields.append("target_uri")

            # 3. Recursively sanitize raw_payload
            clean_payload, payload_redactions = self.sanitize_payload(
                signal.raw_payload,
                parent_path="raw_payload",
                is_private_context=is_private
            )
            redacted_fields.extend(payload_redactions)

            # 4. Assign Classification
            had_redactions = len(redacted_fields) > 0
            classification = self.assign_classification(
                source_type=signal.source_type,
                app_identifier=signal.app_identifier,
                target_uri=clean_target_uri,
                had_redactions=had_redactions,
                is_permitted=True,
            )

            self._record_audit_event(
                "SIGNAL_PERMITTED",
                f"app={signal.app_identifier}, classification={classification.value}, redacted_count={len(redacted_fields)}",
                permitted=True,
            )

            return PolicyDecision(
                permitted=True,
                classification=classification,
                redacted_payload=clean_payload,
                sanitized_window_title=clean_window_title,
                sanitized_target_uri=clean_target_uri,
                violations=[],
                redacted_fields=redacted_fields,
                audit_event_id=audit_id,
            )

        except Exception as e:
            # Strict Fail-Closed invariant
            self._record_audit_event("POLICY_EXCEPTION_FAIL_CLOSED", str(e), permitted=False)
            return PolicyDecision(
                permitted=False,
                classification=ClassificationLevel.PROHIBITED,
                redacted_payload=None,
                violations=[f"Internal policy evaluation error: {str(e)}"],
                redacted_fields=[],
                audit_event_id=audit_id,
            )

    # --------------------------------------------------------------------------
    # Query Permission Gate
    # --------------------------------------------------------------------------

    def check_query_permission(self, request: ContextRequest) -> bool:
        """Verify if consumer and stated purpose are authorized for requested scopes."""
        if not request.consumer_id or not request.stated_purpose or not request.requested_scopes:
            return False

        perm = self.consumer_permissions.get(request.consumer_id)
        if not perm:
            self._record_audit_event("QUERY_DENIED", f"Unknown consumer_id: {request.consumer_id}", permitted=False)
            return False

        # Validate stated purpose matches allowed purposes
        purpose_allowed = any(
            fnmatch.fnmatch(request.stated_purpose, allowed)
            or allowed == "*"
            for allowed in perm.allowed_purposes
        )
        if not purpose_allowed:
            self._record_audit_event("QUERY_DENIED", f"Unauthorized purpose: {request.stated_purpose}", permitted=False)
            return False

        # Validate requested scopes
        for req_scope in request.requested_scopes:
            # Check for forbidden sensitive scopes
            if req_scope.startswith("scope:credentials") or req_scope.startswith("scope:passwords"):
                self._record_audit_event("QUERY_DENIED", f"Forbidden scope requested: {req_scope}", permitted=False)
                return False

            scope_allowed = any(
                req_scope == allowed
                or allowed == "*"
                or fnmatch.fnmatch(req_scope, allowed)
                for allowed in perm.allowed_scopes
            )
            if not scope_allowed:
                self._record_audit_event("QUERY_DENIED", f"Unauthorized scope requested: {req_scope}", permitted=False)
                return False

        self._record_audit_event("QUERY_AUTHORIZED", f"consumer={request.consumer_id}, scopes={request.requested_scopes}", permitted=True)
        return True

    # --------------------------------------------------------------------------
    # ContextSnapshot Sanitizer & Budget Pruning
    # --------------------------------------------------------------------------

    def sanitize_snapshot(
        self,
        snapshot: ContextSnapshot,
        request: ContextRequest,
    ) -> ContextSnapshot:
        """Apply exact scope minimization, verified budget pruning, and redaction.

        Scope filtering is exact default-deny (see
        ``schemas.models.fact_matches_scope``): a fact is disclosed only when
        one requested scope pattern matches its explicit tags. Budget
        enforcement counts the ACTUAL canonical serialization with the
        identified tokenizer and verifies the sealed snapshot fits; every
        prune is disclosed in the manifest and ``overflow`` is set. Raises
        :class:`BudgetExceededError` when even the minimum envelope (no facts,
        no hypotheses, compacted manifest) cannot fit the declared budget.
        """
        manifest: List[str] = list(snapshot.redaction_manifest)
        requested = list(request.requested_scopes or [])

        # 1. Exact scope filter + value sanitization
        scoped_facts: List[DerivedFact] = []
        excluded = 0
        for fact in snapshot.active_facts:
            if requested and not any(
                fact_matches_scope(fact.entity_uri, fact.scopes, pattern)
                for pattern in requested
            ):
                excluded += 1
                continue
            clean_val, val_redactions = self.sanitize_payload(fact.value, parent_path=fact.entity_uri)
            if val_redactions:
                manifest.extend(val_redactions)
                scoped_facts.append(
                    DerivedFact(
                        fact_id=fact.fact_id,
                        schema_version=fact.schema_version,
                        entity_uri=fact.entity_uri,
                        attribute=fact.attribute,
                        value=clean_val,
                        confidence=fact.confidence,
                        valid_from=fact.valid_from,
                        valid_to=fact.valid_to,
                        supporting_evidence_ids=fact.supporting_evidence_ids,
                        derived_by=fact.derived_by,
                        revision_id=fact.revision_id,
                        scopes=list(fact.scopes),
                    )
                )
            else:
                scoped_facts.append(fact)
        if excluded:
            manifest.append(f"excluded_out_of_scope_count:{excluded}")

        # 2. Sanitize hypotheses (redaction only; budgeting happens below)
        clean_hypotheses: List[Hypothesis] = []
        for h in snapshot.active_hypotheses:
            clean_intent, intent_redactions = self.redact_text(h.proposed_intent)
            if intent_redactions:
                manifest.extend(intent_redactions)
                clean_hypotheses.append(
                    Hypothesis(
                        hypothesis_id=h.hypothesis_id,
                        proposed_intent=clean_intent,
                        confidence_score=h.confidence_score,
                        candidate_evidence_ids=h.candidate_evidence_ids,
                        uncertainty_reasons=h.uncertainty_reasons,
                        expires_at=h.expires_at,
                        is_hypothesis=True,
                    )
                )
            else:
                clean_hypotheses.append(h)

        # 3. Tier-priority order (lower tier first; confidence then recency)
        def _fact_sort_key(f: DerivedFact) -> Tuple[int, float, float]:
            try:
                recency = f.valid_from.timestamp()
            except Exception:
                recency = 0.0
            return (fact_tier_rank(f.entity_uri, f.attribute, f.confidence), -f.confidence, -recency)

        packed_facts = sorted(scoped_facts, key=_fact_sort_key)
        packed_hypos = sorted(clean_hypotheses, key=lambda h: -h.confidence_score)
        budget = max(1, int(request.token_or_size_budget))

        # 4. Greedy pre-pack by calibrated size (keeps verification O(1)):
        # measure the envelope once with the identified counter, derive a
        # chars-per-token rate from that REAL sample, then pack items by char
        # size. The verify loop below still enforces the exact budget.
        def _item_chars(item: Any) -> int:
            return len(
                json.dumps(
                    item.model_dump(mode="json", by_alias=True),
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                )
            )

        envelope_probe = ContextSnapshot(
            snapshot_id=snapshot.snapshot_id,
            schema_version=snapshot.schema_version,
            request_id=request.request_id,
            issued_at=snapshot.issued_at,
            expires_at=snapshot.expires_at,
            purpose_granted=request.stated_purpose,
            scope_granted=request.requested_scopes,
            active_facts=[],
            active_hypotheses=[],
            evidence_provenance_refs=[],
            redaction_manifest=compact_prune_manifest(manifest),
            disclaimer=snapshot.disclaimer,
            overflow=False,
            budget=None,
        )
        probe_serialized = canonical_snapshot_json(envelope_probe)
        probe_tokens, probe_tokenizer = count_budget_tokens(probe_serialized)
        chars_per_token = (len(probe_serialized) / probe_tokens) if probe_tokens > 0 else 4.0
        if chars_per_token <= 0:
            chars_per_token = 4.0
        char_budget = int(budget * chars_per_token) - len(probe_serialized)
        running_chars = 0
        prepacked_facts: List[DerivedFact] = []
        for fact in packed_facts:
            size = _item_chars(fact)
            if running_chars + size <= char_budget:
                prepacked_facts.append(fact)
                running_chars += size
        kept_fact_ids = {id(f) for f in prepacked_facts}
        for fact in packed_facts:
            if id(fact) not in kept_fact_ids:
                manifest.append(f"pruned_fact_budget_exceeded:{fact.fact_id}")
        omitted_prefacts = len(packed_facts) - len(prepacked_facts)
        packed_facts = prepacked_facts
        prepacked_hypos: List[Hypothesis] = []
        for hypo in packed_hypos:
            size = _item_chars(hypo)
            if running_chars + size <= char_budget:
                prepacked_hypos.append(hypo)
                running_chars += size
        kept_hypo_ids = {id(h) for h in prepacked_hypos}
        for hypo in packed_hypos:
            if id(hypo) not in kept_hypo_ids:
                manifest.append(f"pruned_hypothesis_budget_exceeded:{hypo.hypothesis_id}")
        omitted_prehypos = len(packed_hypos) - len(prepacked_hypos)
        packed_hypos = prepacked_hypos

        # 5. Verify loop on the real serialization: drop lowest-priority items
        # until the sealed snapshot fits. Hypotheses yield before facts.
        _, tokenizer_id = count_budget_tokens("")
        omitted_facts = omitted_prefacts
        omitted_hypos = omitted_prehypos
        provisional = SnapshotBudget(
            budget_tokens=budget,
            used_tokens=0,
            used_chars=0,
            tokenizer=tokenizer_id,
            overflow=bool(omitted_prefacts or omitted_prehypos),
            omitted_facts=omitted_prefacts,
            omitted_hypotheses=omitted_prehypos,
        )

        def _build(
            facts: List[DerivedFact],
            hypos: List[Hypothesis],
            block: SnapshotBudget,
            max_manifest: int = PRUNE_MANIFEST_MAX_ENTRIES,
        ) -> ContextSnapshot:
            refs = sorted({e for f in facts for e in f.supporting_evidence_ids})
            return ContextSnapshot(
                snapshot_id=snapshot.snapshot_id,
                schema_version=snapshot.schema_version,
                request_id=request.request_id,
                issued_at=snapshot.issued_at,
                expires_at=snapshot.expires_at,
                purpose_granted=request.stated_purpose,
                scope_granted=request.requested_scopes,
                active_facts=facts,
                active_hypotheses=hypos,
                evidence_provenance_refs=refs,
                redaction_manifest=compact_prune_manifest(manifest, max_entries=max_manifest),
                disclaimer=snapshot.disclaimer,
                overflow=block.overflow,
                budget=block,
            )

        def _raise_exceeded(used_tokens: int, used_chars: int, tokenizer: str) -> None:
            raise BudgetExceededError(
                f"minimum snapshot envelope ({used_chars} chars, "
                f"{used_tokens} {tokenizer} tokens) exceeds the "
                f"declared budget of {budget} tokens",
                budget_tokens=budget,
                used_tokens=used_tokens,
                used_chars=used_chars,
                tokenizer=tokenizer,
            )

        # Under token pressure the prune ledger yields to its floor BEFORE
        # retained content is pruned (mirrors the packet omission ledger).
        manifest_cap = PRUNE_MANIFEST_MAX_ENTRIES
        max_iterations = len(packed_facts) + len(packed_hypos) + 5
        for _ in range(max_iterations):
            candidate = _build(packed_facts, packed_hypos, provisional, manifest_cap)
            serialized = canonical_snapshot_json(candidate)
            used_tokens, used_tokenizer = count_budget_tokens(serialized)
            used_chars = len(serialized)
            if used_tokens <= budget:
                final_block = SnapshotBudget(
                    budget_tokens=budget,
                    used_tokens=used_tokens,
                    used_chars=used_chars,
                    tokenizer=used_tokenizer,
                    overflow=provisional.overflow,
                    omitted_facts=omitted_facts,
                    omitted_hypotheses=omitted_hypos,
                )
                if (
                    final_block.used_tokens == provisional.used_tokens
                    and final_block.used_chars == provisional.used_chars
                    and final_block.tokenizer == provisional.tokenizer
                ):
                    return _build(packed_facts, packed_hypos, final_block, manifest_cap)
                provisional = final_block
                continue
            if manifest_cap > PRUNE_MANIFEST_MIN_KEPT:
                manifest_cap = PRUNE_MANIFEST_MIN_KEPT
                provisional = SnapshotBudget(
                    budget_tokens=budget,
                    used_tokens=provisional.used_tokens,
                    used_chars=provisional.used_chars,
                    tokenizer=provisional.tokenizer,
                    overflow=True,
                    omitted_facts=omitted_facts,
                    omitted_hypotheses=omitted_hypos,
                )
                continue
            if packed_hypos:
                dropped_hypo = packed_hypos.pop()
                manifest.append(f"pruned_hypothesis_budget_exceeded:{dropped_hypo.hypothesis_id}")
                omitted_hypos += 1
            elif packed_facts:
                dropped_fact = packed_facts.pop()
                manifest.append(f"pruned_fact_budget_exceeded:{dropped_fact.fact_id}")
                omitted_facts += 1
            else:
                _raise_exceeded(used_tokens, used_chars, used_tokenizer)
            provisional = SnapshotBudget(
                budget_tokens=budget,
                used_tokens=provisional.used_tokens,
                used_chars=provisional.used_chars,
                tokenizer=provisional.tokenizer,
                overflow=True,
                omitted_facts=omitted_facts,
                omitted_hypotheses=omitted_hypos,
            )
        raise BudgetExceededError(
            "snapshot budget verification did not converge",
            budget_tokens=budget,
            used_tokens=0,
            used_chars=0,
            tokenizer=tokenizer_id,
        )

    # --------------------------------------------------------------------------
    # Audit Logging
    # --------------------------------------------------------------------------

    def _record_audit_event(
        self,
        action: str,
        details: str,
        permitted: bool = True,
    ) -> str:
        """Create a tamper-evident audit event log entry."""
        audit_id = generate_uuidv7()
        event = {
            "audit_id": audit_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "details": details,
            "permitted": permitted,
        }
        self.audit_log.append(event)
        # Cap audit log length in memory
        if len(self.audit_log) > 5000:
            self.audit_log = self.audit_log[-5000:]
        return audit_id

    def get_audit_trail(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve recent audit events."""
        return self.audit_log[-limit:]
