"""Integration tests for end-to-end task pipelines and receipt storage."""

from pathlib import Path

import pytest
import yaml

from stc.core.config import Settings
from stc.schemas.models import TaskSpec, TaskStatus
from stc.services.engine import STCEngine


@pytest.mark.asyncio
async def test_end_to_end_spec_file_lifecycle(tmp_path: Path) -> None:
    """Test full cycle: YAML Spec file on disk -> Engine execution -> Receipt verification."""
    spec_data = {
        "task_id": "task_integration_001",
        "name": "integration-compute",
        "action": "compute",
        "priority": "high",
        "payload": {
            "op": "prod",
            "values": [2, 3, 4],
        },
        "timeout_seconds": 10.0,
    }

    spec_file = tmp_path / "test_spec.yaml"
    with spec_file.open("w", encoding="utf-8") as f:
        yaml.dump(spec_data, f)

    # Load and validate spec
    loaded_data = yaml.safe_load(spec_file.read_text(encoding="utf-8"))
    spec = TaskSpec.model_validate(loaded_data)

    settings = Settings(
        environment="test",
        workspace_root=tmp_path,
        artifacts_dir=Path("artifacts"),
    )
    engine = STCEngine(settings)

    receipt = await engine.run_task(spec)

    assert receipt.task_id == "task_integration_001"
    assert receipt.status == TaskStatus.COMPLETED
    assert receipt.result["result"] == 24
    assert receipt.result["operation"] == "prod"

    # Verify physical file existence
    receipt_file = engine.receipts_dir / f"{receipt.receipt_id}.json"
    assert receipt_file.exists()
    assert receipt_file.stat().st_size > 0

    # Retrieve via receipt store
    retrieved = engine.get_receipt(receipt.receipt_id)
    assert retrieved is not None
    assert retrieved.checksum_sha256 == receipt.checksum_sha256
