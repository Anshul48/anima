"""F4 controls: exact default-deny scopes and honest delivered budgets.

Scope matching binds facts to explicit tags (no cross-scope leakage, no
implicit wildcard); budgets count the actual delivered serialization with an
identified tokenizer and fail explicitly when the minimum envelope cannot
fit. Reads obey CURRENT deletion/consent restrictions. Synthetic only.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from entorhinal.evidence.journal import EvidenceJournal
from entorhinal.policy.engine import (
    BudgetExceededError,
    ConsumerPermission,
    PolicyEngine,
    TOKENIZER_TIKTOKEN_O200K,
    canonical_snapshot_json,
    count_budget_tokens,
)
from entorhinal.projections.compiler import MultiTimescaleCompiler
from entorhinal.query.service import ContextSnapshotService, PermissionDeniedError
from entorhinal.schemas.models import (
    ContextRequest,
    EvidenceRecord,
    SourceType,
    fact_matches_scope,
)

NOW = datetime.now(timezone.utc)


def _record(
    record_id: str,
    source_type: SourceType,
    app: str,
    target: str,
    payload: dict,
    at: datetime | None = None,
) -> EvidenceRecord:
    return EvidenceRecord.create(
        source_type=source_type,
        app_identifier=app,
        sanitized_payload=dict(payload),
        previous_record_hash="0" * 64,
        window_title=f"SYNTHETIC {app} window",
        target_uri=target,
        record_id=record_id,
        persisted_at=at or NOW,
    )


def _workspace_request(budget: int = 4096) -> ContextRequest:
    return ContextRequest(
        consumer_id="probe.reader",
        stated_purpose="synthetic probe",
        requested_scopes=["scope:workspace.active_project"],
        token_or_size_budget=budget,
        max_freshness_seconds=86400,
    )


def _service_with_corpus(tmp_path: Path) -> tuple[ContextSnapshotService, EvidenceJournal]:
    journal = EvidenceJournal(storage_path=tmp_path / "scope_journal.jsonl")
    return (
        ContextSnapshotService(
            compiler=MultiTimescaleCompiler(journal=journal),
            policy_engine=PolicyEngine(),
            journal=journal,
        ),
        journal,
    )


async def _seed_corpus(journal: EvidenceJournal) -> list[str]:
    """One workspace record + one unrelated browser mail record (synthetic)."""
    workspace = _record(
        "syn-scope-ws-1",
        SourceType.OS_WINDOW,
        "VSCode",
        "file:///synthetic/workspace/probe.py",
        {"workspace": "synthetic-probe", "file_path": "/synthetic/workspace/probe.py"},
    )
    mail = _record(
        "syn-scope-mail-1",
        SourceType.BROWSER,
        "Chrome",
        "https://mail.example.test/inbox/SYNTHETIC",
        {"url": "https://mail.example.test/inbox/SYNTHETIC", "title": "SYNTHETIC inbox"},
    )
    await journal.append(workspace)
    await journal.append(mail)
    return [workspace.record_id, mail.record_id]


def _grant_probe(policy: PolicyEngine) -> None:
    policy.register_consumer_permission(
        ConsumerPermission(
            consumer_id="probe.reader",
            allowed_purposes=["synthetic probe"],
            allowed_scopes=["scope:workspace.*", "scope:browser.*", "scope:terminal.*"],
            max_budget=8192,
        )
    )


# --------------------------------------------------------------------------
# Matcher unit semantics
# --------------------------------------------------------------------------

def test_matcher_exact_and_class() -> None:
    assert fact_matches_scope("project:demo", ["scope:workspace"], "scope:workspace.active_project")
    assert fact_matches_scope("project:demo", ["scope:workspace"], "project:demo")
    assert not fact_matches_scope("project:demo", ["scope:workspace"], "scope:browser.recent_tabs")


def test_matcher_no_substring_or_prefix_implication() -> None:
    # The old P8 leak: any workspace-flavored request matched every fact.
    assert not fact_matches_scope("tool:personal.mail", ["scope:browser"], "scope:workspace.active_project")
    assert not fact_matches_scope(
        "document:https://mail.example.test/inbox", ["scope:browser"], "scope:workspace"
    )
    # (A bare `document:mail` URI with no URL falls back to scope:workspace
    # by the documented prefix table; that is explicit design, not a leak.)


def test_matcher_stored_tags_take_precedence_over_fallback() -> None:
    # Entity URIs are slugified (`https_//`), which can mislead the URI
    # fallback table; explicit stored tags are ground truth and win.
    assert not fact_matches_scope(
        "document:https_//mail.example.test/inbox", ["scope:browser"], "scope:workspace"
    )
    assert fact_matches_scope(
        "document:https_//mail.example.test/inbox", ["scope:browser"], "scope:browser.recent"
    )


def test_matcher_fallback_applies_when_untagged() -> None:
    assert fact_matches_scope("project:demo", [], "scope:workspace.active_project")
    assert fact_matches_scope("session:cluster-v1-abc", [], "scope:workspace")


def test_matcher_default_deny_unknown() -> None:
    assert not fact_matches_scope("weird:thing", [], "scope:workspace")
    assert not fact_matches_scope("weird:thing", [], "not-a-scope")
    assert not fact_matches_scope("weird:thing", ["scope:workspace"], "")


def test_matcher_explicit_wildcard_only() -> None:
    assert fact_matches_scope("project:demo", ["scope:workspace"], "*")
    # Even "*" discloses nothing for untagged facts.
    assert not fact_matches_scope("weird:thing", [], "*")


def test_no_implicit_wildcard_grant() -> None:
    policy = PolicyEngine()
    perm = policy.consumer_permissions["reflex.system2.planner"]
    assert "*" not in perm.allowed_purposes
    assert "*" not in perm.allowed_scopes
    # A caller outside the explicit grant is denied, not defaulted in.
    assert not policy.check_query_permission(
        ContextRequest(
            consumer_id="audit.unknown.consumer",
            stated_purpose="synthetic probe",
            requested_scopes=["scope:workspace.active_project"],
            token_or_size_budget=64,
            max_freshness_seconds=60,
        )
    )


def test_explicit_persisted_wildcard_still_honored() -> None:
    policy = PolicyEngine()
    policy.register_consumer_permission(
        ConsumerPermission(
            consumer_id="explicit.star",
            allowed_purposes=["synthetic probe"],
            allowed_scopes=["*"],
            max_budget=1024,
        )
    )
    assert policy.check_query_permission(
        ContextRequest(
            consumer_id="explicit.star",
            stated_purpose="synthetic probe",
            requested_scopes=["scope:terminal.last_commands"],
            token_or_size_budget=64,
            max_freshness_seconds=60,
        )
    )


def test_permission_register_remove_roundtrip() -> None:
    policy = PolicyEngine()
    policy.register_consumer_permission(
        ConsumerPermission(
            consumer_id="temp.consumer",
            allowed_purposes=["p"],
            allowed_scopes=["scope:workspace"],
            max_budget=64,
        )
    )
    assert "temp.consumer" in policy.consumer_permissions
    assert policy.remove_consumer_permission("temp.consumer") is True
    assert "temp.consumer" not in policy.consumer_permissions
    assert policy.remove_consumer_permission("temp.consumer") is False


# --------------------------------------------------------------------------
# Service-level scope separation (narrow request, no cross-scope leak)
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_narrow_workspace_request_excludes_mail(tmp_path: Path) -> None:
    service, journal = _service_with_corpus(tmp_path)
    _grant_probe(service.policy_engine)
    await _seed_corpus(journal)
    await service.compiler.compile_batch_projection()
    snapshot = await service.request_snapshot(_workspace_request())
    assert snapshot.active_facts, "workspace corpus must yield workspace facts"
    for fact in snapshot.active_facts:
        assert fact_matches_scope(fact.entity_uri, fact.scopes, "scope:workspace.active_project"), fact.entity_uri
    uris = [f.entity_uri for f in snapshot.active_facts]
    assert not any("mail.example.test" in u for u in uris), uris
    assert not any(u == "tool:chrome" for u in uris), uris


@pytest.mark.asyncio
async def test_session_aggregate_requires_all_contributing_classes(tmp_path: Path) -> None:
    """Mixed-class session values embed raw URIs: AND-gate, with disclosure."""
    service, journal = _service_with_corpus(tmp_path)
    _grant_probe(service.policy_engine)
    await _seed_corpus(journal)
    await service.compiler.compile_batch_projection()
    narrow = await service.request_snapshot(_workspace_request())
    assert not any(f.entity_uri.startswith("session:") for f in narrow.active_facts)
    assert any(
        m.startswith("session_multi_scope_excluded_count:") for m in narrow.redaction_manifest
    )
    # The same session IS disclosed when every contributing class is granted.
    wide = _workspace_request()
    wide.requested_scopes = ["scope:workspace.*", "scope:browser.*"]
    wide_snapshot = await service.request_snapshot(wide)
    assert any(f.entity_uri.startswith("session:") for f in wide_snapshot.active_facts)


@pytest.mark.asyncio
async def test_ungranted_scope_denied_at_service(tmp_path: Path) -> None:
    service, journal = _service_with_corpus(tmp_path)
    _grant_probe(service.policy_engine)
    await _seed_corpus(journal)
    request = _workspace_request()
    request.requested_scopes = ["scope:credentials.vault"]
    with pytest.raises(PermissionDeniedError):
        await service.request_snapshot(request)


# --------------------------------------------------------------------------
# Honest delivered-serialization budgets
# --------------------------------------------------------------------------

def test_budget_counter_is_identified() -> None:
    count, tokenizer = count_budget_tokens("SYNTHETIC budget probe text")
    assert count > 0
    assert tokenizer == TOKENIZER_TIKTOKEN_O200K


@pytest.mark.asyncio
async def test_tiny_budget_fails_explicitly(tmp_path: Path) -> None:
    service, journal = _service_with_corpus(tmp_path)
    _grant_probe(service.policy_engine)
    await _seed_corpus(journal)
    await service.compiler.compile_batch_projection()
    with pytest.raises(BudgetExceededError) as exc_info:
        await service.request_snapshot(_workspace_request(budget=1))
    assert exc_info.value.budget_tokens == 1
    assert exc_info.value.used_tokens > 1
    assert exc_info.value.tokenizer == TOKENIZER_TIKTOKEN_O200K


@pytest.mark.asyncio
async def test_budget_accounting_is_truthful(tmp_path: Path) -> None:
    service, journal = _service_with_corpus(tmp_path)
    _grant_probe(service.policy_engine)
    # Enough records that a mid budget must prune with disclosure.
    for i in range(12):
        await journal.append(
            _record(
                f"syn-budget-{i:02d}",
                SourceType.OS_WINDOW if i % 2 == 0 else SourceType.BROWSER,
                "VSCode" if i % 2 == 0 else "Chrome",
                f"file:///synthetic/workspace/mod{i}.py" if i % 2 == 0 else f"https://docs.example.test/synth/{i}",
                {"workspace": "synthetic-probe", "file_path": f"/synthetic/workspace/mod{i}.py"}
                if i % 2 == 0
                else {"url": f"https://docs.example.test/synth/{i}"},
                at=NOW - timedelta(minutes=i),
            )
        )
    await service.compiler.compile_batch_projection()
    request = _workspace_request(budget=1024)
    request.requested_scopes = ["scope:workspace.*", "scope:browser.*"]
    snapshot = await service.request_snapshot(request)
    assert snapshot.budget is not None
    assert snapshot.budget.tokenizer == TOKENIZER_TIKTOKEN_O200K
    assert snapshot.budget.used_tokens <= 1024
    assert snapshot.overflow is True
    assert snapshot.budget.omitted_facts > 0
    assert any(m.startswith("pruned_") for m in snapshot.redaction_manifest)
    # The disclosed count matches an independent count of the serialization.
    recount, _ = count_budget_tokens(canonical_snapshot_json(snapshot))
    assert recount == snapshot.budget.used_tokens


# --------------------------------------------------------------------------
# Current restrictions: tombstones and revoked consent filter every read
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tombstoned_grounding_withholds_facts(tmp_path: Path) -> None:
    service, journal = _service_with_corpus(tmp_path)
    _grant_probe(service.policy_engine)
    record_ids, _ = [await _seed_corpus(journal)][0], None
    await service.compiler.compile_batch_projection()
    before = await service.request_snapshot(_workspace_request())
    assert before.active_facts
    assert await journal.tombstone_record(record_ids[0], reason="synthetic probe deletion") is True
    after = await service.request_snapshot(_workspace_request())
    assert len(after.active_facts) < len(before.active_facts)
    assert any(m.startswith("restricted_current_policy_count:") for m in after.redaction_manifest)


@pytest.mark.asyncio
async def test_revoked_consent_withholds_facts(tmp_path: Path) -> None:
    service, journal = _service_with_corpus(tmp_path)
    _grant_probe(service.policy_engine)
    await _seed_corpus(journal)
    await service.compiler.compile_batch_projection()
    assert (await service.request_snapshot(_workspace_request())).active_facts
    service.policy_engine.add_consent_rule(
        allow=False, source_type=SourceType.OS_WINDOW, app_pattern="*", domain_pattern="*", priority=100
    )
    after = await service.request_snapshot(_workspace_request())
    assert not after.active_facts
    assert any(m.startswith("restricted_current_policy_count:") for m in after.redaction_manifest)


@pytest.mark.asyncio
async def test_purge_evidence_clears_focus_and_rebuilds_aggregates(tmp_path: Path) -> None:
    service, journal = _service_with_corpus(tmp_path)
    record_ids, _ = [await _seed_corpus(journal)][0], None
    records = await journal.scan_evidence(limit=10)
    for record in records:
        service.compiler.process_incremental_event(record)
    assert service.compiler.get_current_context().immediate_focus is not None
    proof = await service.compiler.purge_evidence([record_ids[0]], reason="synthetic probe")
    assert proof["aggregates_rebuilt"] == 1
    assert proof["app_usage_events_before"] >= proof["app_usage_events_after"]
    # Tombstone first, then purge: the deleted event leaves the aggregates.
    assert await journal.tombstone_record(record_ids[0], reason="synthetic probe deletion") is True
    proof2 = await service.compiler.purge_evidence([record_ids[0]], reason="synthetic probe")
    assert proof2["app_usage_events_after"] < proof["app_usage_events_before"]
