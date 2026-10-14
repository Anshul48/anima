import asyncio
import json
from pathlib import Path
import pytest
import struct
from datetime import datetime, timezone

from typing import Optional
from unittest.mock import AsyncMock, patch

from entorhinal.ports.named_pipe import NamedPipeServerProtocol
from entorhinal.api.vnext_provider import VNextProvider
from entorhinal.query.service import ContextSnapshotService, PermissionDeniedError
from entorhinal.schemas.models import ContextSnapshot, DerivedFact

def _find_corpus_path() -> Optional[Path]:
    # Repo-relative only: parents[3] is Utilities/ upstream (sibling `relfex`)
    # or components/ in the staged mono-repo (sibling `reflex`). Machine-local
    # absolute candidates were removed for public release.
    candidates = [
        Path(__file__).resolve().parents[3] / "reflex" / "docs" / "contract" / "vNext" / "corpus.json",
        Path(__file__).resolve().parents[3] / "relfex" / "docs" / "contract" / "vNext" / "corpus.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None

CORPUS_PATH = _find_corpus_path()

class DummyTransport:
    def __init__(self):
        self.buffer = bytearray()
        self.closed = False
        self._extra = {'pipe_handle': None}
    def write(self, data):
        self.buffer.extend(data)
    def close(self):
        self.closed = True
    def _get_extra_info(self, name):
        return self._extra.get(name)

@pytest.fixture
def corpus_data():
    if CORPUS_PATH is None or not CORPUS_PATH.exists():
        pytest.skip("Corpus file not found")
    with open(CORPUS_PATH, "r") as f:
        return json.load(f)

@pytest.mark.asyncio
async def test_vnext_conformance_fixtures(corpus_data):
    for fixture in corpus_data.get("fixtures", []):
        req_data = fixture["request"]
        expected_resp = fixture["response"]
        
        service_mock = AsyncMock(spec=ContextSnapshotService)
        
        if expected_resp["status"] == "AVAILABLE":
            mock_facts = []
            for f in expected_resp["payload"]["facts"]:
                mock_facts.append(DerivedFact(
                    fact_id=f["fact_id"],
                    entity_uri="test",
                    attribute="test",
                    value=f.get("text", ""),
                    confidence=f["confidence"],
                    supporting_evidence_ids=[f["provenance_ref"]],
                    derived_by="test"
                ))
            mock_snap = ContextSnapshot(
                snapshot_id=expected_resp["payload"]["snapshot_id"],
                purpose_granted=expected_resp["payload"]["granted_purpose"],
                scope_granted=expected_resp["payload"]["granted_scopes"],
                active_facts=mock_facts,
                expires_at=datetime.fromisoformat(expected_resp["payload"]["expires_at"].replace('Z', '+00:00'))
            )
            service_mock.request_snapshot.return_value = mock_snap
        elif expected_resp["status"] == "NO_CONTEXT":
            mock_snap = ContextSnapshot(
                purpose_granted=req_data["purpose"],
                scope_granted=req_data["scopes"],
                active_facts=[],
                expires_at=datetime.now(timezone.utc)
            )
            service_mock.request_snapshot.return_value = mock_snap
        elif expected_resp["status"] == "DENIED":
            service_mock.request_snapshot.side_effect = PermissionDeniedError("policy_denial")
        else:
            service_mock.request_snapshot.return_value = None
            
        provider = VNextProvider(service_mock)
        
        msg_bytes = json.dumps(req_data).encode("utf-8")
        size_prefix = struct.pack("!I", len(msg_bytes))
        full_msg = size_prefix + msg_bytes
        
        protocol = NamedPipeServerProtocol(provider.handle_request)
        transport = DummyTransport()
        protocol.connection_made(transport)
        
        protocol.data_received(full_msg)
        await asyncio.sleep(0.05)
        
        if len(transport.buffer) >= 4:
            resp_size = struct.unpack("!I", transport.buffer[:4])[0]
            resp_bytes = transport.buffer[4:4+resp_size]
            actual_resp = json.loads(resp_bytes.decode("utf-8"))
            
            assert actual_resp["status"] == expected_resp["status"], f"Fixture {fixture['id']} mismatch: {actual_resp} != {expected_resp}"
            
            if "payload" in expected_resp:
                assert "payload" in actual_resp
                assert actual_resp["payload"]["granted_purpose"] == expected_resp["payload"]["granted_purpose"]
                assert actual_resp["payload"]["granted_scopes"] == expected_resp["payload"]["granted_scopes"]
                if fixture["id"] == "CORPUS-12-INJECTION":
                    assert actual_resp["payload"]["facts"][0]["text"] == expected_resp["payload"]["facts"][0]["text"]
