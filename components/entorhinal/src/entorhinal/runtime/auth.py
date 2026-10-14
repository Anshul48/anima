"""Role authentication and persisted grants for the Entorhinal serving path.

Accepted control (PLAN.md/E1): bind loopback and authenticate the source,
reader, and administration roles. This module is the persisted home of those
credentials and grants:

- :class:`Principal`: one authenticated identity (source/reader/admin) with
  explicit purposes, scopes, and budget.
- :class:`AuthStore`: JSON persistence under the runtime root (0600,
  atomic writes, mtime-checked refresh). Secrets are held as sha256 hashes;
  a raw secret is returned exactly once, at creation.

Unknown, revoked, or disabled principals authenticate to ``None`` (callers
map that to HTTP 401/403). Revoked ids are never recycled. There is no
implicit wildcard grant: ``"*"`` is honored only when explicitly persisted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import hmac
import json
import logging
import os
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

AUTH_FILE_VERSION = 1
SECRET_PREFIX = "ent_"
SECRET_HEX_BYTES = 32

ROLE_SOURCE = "source"
ROLE_READER = "reader"
ROLE_ADMIN = "admin"
ROLES = (ROLE_SOURCE, ROLE_READER, ROLE_ADMIN)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Principal:
    """One authenticated identity with explicit persisted grants."""

    principal_id: str
    role: str
    allowed_purposes: List[str] = field(default_factory=list)
    allowed_scopes: List[str] = field(default_factory=list)
    max_budget: int = 4096
    source_id: Optional[str] = None
    grant_revision: str = "grant:r1"
    label: str = ""
    created_at: str = ""
    disabled: bool = False

    def covers_scope(self, scope: str) -> bool:
        """Whether this principal's grant covers one requested scope string."""
        import fnmatch

        for allowed in self.allowed_scopes:
            if allowed == "*" or scope == allowed or fnmatch.fnmatch(scope, allowed):
                return True
        return False

    def covers_purpose(self, purpose: str) -> bool:
        """Whether this principal's grant covers one stated purpose."""
        import fnmatch

        for allowed in self.allowed_purposes:
            if allowed == "*" or purpose == allowed or fnmatch.fnmatch(purpose, allowed):
                return True
        return False


class AuthStore:
    """Persisted principal + grant store for one runtime root."""

    def __init__(self, path: Any) -> None:
        self._path = Path(path)
        self._principals: Dict[str, Dict[str, Any]] = {}
        self._loaded_mtime: Optional[float] = None
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> None:
        if not self._path.exists():
            self._principals = {}
            self._loaded_mtime = None
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error("Auth store %s unreadable; treating as empty: %s", self._path, e)
            self._principals = {}
            self._loaded_mtime = None
            return
        principals = raw.get("principals", {}) if isinstance(raw, dict) else {}
        if not isinstance(principals, dict):
            principals = {}
        self._principals = principals
        try:
            self._loaded_mtime = self._path.stat().st_mtime
        except OSError:
            self._loaded_mtime = None

    def refresh(self) -> None:
        """Reload from disk when another writer (e.g. CLI) changed the file."""
        try:
            mtime = self._path.stat().st_mtime if self._path.exists() else None
        except OSError:
            mtime = None
        if mtime != self._loaded_mtime:
            self._load()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": AUTH_FILE_VERSION, "principals": self._principals}
        fd, tmp_name = tempfile.mkstemp(
            dir=str(self._path.parent), prefix=self._path.name + ".", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, sort_keys=True)
                fh.write("\n")
            try:
                os.chmod(tmp_name, 0o600)
            except OSError:
                pass
            os.replace(tmp_name, self._path)
        finally:
            try:
                if os.path.exists(tmp_name):
                    os.unlink(tmp_name)
            except OSError:
                pass
        try:
            self._loaded_mtime = self._path.stat().st_mtime
        except OSError:
            self._loaded_mtime = None

    # ------------------------------------------------------------------
    # Principal lifecycle
    # ------------------------------------------------------------------

    def _materialize(self, entry: Dict[str, Any]) -> Principal:
        return Principal(
            principal_id=str(entry.get("principal_id", "")),
            role=str(entry.get("role", "")),
            allowed_purposes=list(entry.get("allowed_purposes", []) or []),
            allowed_scopes=list(entry.get("allowed_scopes", []) or []),
            max_budget=int(entry.get("max_budget", 4096)),
            source_id=entry.get("source_id"),
            grant_revision=str(entry.get("grant_revision", "grant:r1")),
            label=str(entry.get("label", "") or ""),
            created_at=str(entry.get("created_at", "") or ""),
            disabled=bool(entry.get("disabled", False)),
        )

    def create_principal(
        self,
        *,
        role: str,
        principal_id: str,
        allowed_purposes: Optional[List[str]] = None,
        allowed_scopes: Optional[List[str]] = None,
        max_budget: int = 4096,
        source_id: Optional[str] = None,
        grant_revision: str = "grant:r1",
        label: str = "",
    ) -> Tuple[Principal, str]:
        """Create a principal with explicit grants; returns (principal, secret).

        The secret is returned exactly once and never stored in the clear.
        Raises ValueError on duplicate ids, unknown roles, or empty grants
        for reader principals.
        """
        if role not in ROLES:
            raise ValueError(f"unknown role {role!r}; expected one of {list(ROLES)}")
        principal_id = (principal_id or "").strip()
        if not principal_id:
            raise ValueError("principal_id must be non-empty")
        self.refresh()
        if principal_id in self._principals:
            raise ValueError(f"principal {principal_id!r} already exists")
        purposes = list(allowed_purposes or [])
        scopes = list(allowed_scopes or [])
        if role == ROLE_READER and (not purposes or not scopes):
            raise ValueError("reader principals require explicit purposes and scopes")
        if role == ROLE_SOURCE and not purposes:
            purposes = ["ingest"]
        if role == ROLE_ADMIN and not purposes:
            purposes = ["administration"]
        if int(max_budget) < 1:
            raise ValueError("max_budget must be >= 1")
        secret = SECRET_PREFIX + secrets.token_hex(SECRET_HEX_BYTES)
        entry = {
            "principal_id": principal_id,
            "role": role,
            "secret_sha256": _hash_secret(secret),
            "allowed_purposes": purposes,
            "allowed_scopes": scopes,
            "max_budget": int(max_budget),
            "source_id": source_id,
            "grant_revision": grant_revision,
            "label": label,
            "created_at": _utcnow_iso(),
            "disabled": False,
        }
        self._principals[principal_id] = entry
        self._save()
        logger.info("auth principal created: id=%s role=%s", principal_id, role)
        return self._materialize(entry), secret

    def authenticate(self, bearer: Optional[str]) -> Optional[Principal]:
        """Resolve a bearer secret to its principal, or None when unknown."""
        if not bearer:
            return None
        token = bearer.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        if not token:
            return None
        self.refresh()
        candidate = _hash_secret(token)
        for entry in self._principals.values():
            stored = str(entry.get("secret_sha256", ""))
            if stored and hmac.compare_digest(stored, candidate):
                if entry.get("disabled", False):
                    return None
                return self._materialize(entry)
        return None

    def get(self, principal_id: str) -> Optional[Principal]:
        self.refresh()
        entry = self._principals.get(principal_id)
        return self._materialize(entry) if entry else None

    def list_principals(self) -> List[Principal]:
        self.refresh()
        return [self._materialize(e) for _, e in sorted(self._principals.items())]

    def revoke(self, principal_id: str) -> bool:
        """Delete a principal; afterwards the id authenticates as unknown."""
        self.refresh()
        if principal_id not in self._principals:
            return False
        del self._principals[principal_id]
        self._save()
        logger.info("auth principal revoked: id=%s", principal_id)
        return True

    def set_disabled(self, principal_id: str, disabled: bool) -> bool:
        self.refresh()
        entry = self._principals.get(principal_id)
        if entry is None:
            return False
        entry["disabled"] = bool(disabled)
        self._save()
        return True

    def update_grants(
        self,
        principal_id: str,
        *,
        allowed_purposes: Optional[List[str]] = None,
        allowed_scopes: Optional[List[str]] = None,
        max_budget: Optional[int] = None,
        grant_revision: Optional[str] = None,
    ) -> Optional[Principal]:
        self.refresh()
        entry = self._principals.get(principal_id)
        if entry is None:
            return None
        if allowed_purposes is not None:
            entry["allowed_purposes"] = list(allowed_purposes)
        if allowed_scopes is not None:
            entry["allowed_scopes"] = list(allowed_scopes)
        if max_budget is not None:
            if int(max_budget) < 1:
                raise ValueError("max_budget must be >= 1")
            entry["max_budget"] = int(max_budget)
        if grant_revision is not None:
            entry["grant_revision"] = grant_revision
        self._save()
        return self._materialize(entry)

    def ensure_bootstrap_admin(
        self, principal_id: str = "admin.bootstrap"
    ) -> Optional[Tuple[Principal, str]]:
        """Create the first admin ONLY when the store is empty, else None.

        This is the single bootstrap seam (called by CLI/deploy tooling, never
        by HTTP). Returns None when any principal already exists.
        """
        self.refresh()
        if self._principals:
            return None
        return self.create_principal(
            role=ROLE_ADMIN,
            principal_id=principal_id,
            allowed_purposes=["administration"],
            allowed_scopes=["*"],
            label="bootstrap administrator",
        )


def extract_bearer(authorization: Optional[str], query_token: Optional[str] = None) -> Optional[str]:
    """Extract a bearer secret from a header value or explicit token param."""
    if authorization:
        text = authorization.strip()
        if text.lower().startswith("bearer "):
            token = text[7:].strip()
            return token or None
        return text or None
    if query_token:
        return query_token.strip() or None
    return None
