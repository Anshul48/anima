"""Unit tests for Scoped Pub/Sub Hormone Protocol and Bus."""

from stc.protocols.interfaces import HormoneBusProtocol
from stc.schemas.hormones import HormoneEvent, HormoneScope, HormoneSignalType
from stc.services.hormones import ScopedHormoneBus


def test_hormone_event_auto_sha256_computation() -> None:
    """Verify that HormoneEvent automatically computes bit-exact SHA-256 over payload."""
    scope = HormoneScope(
        producer_subsystem="cell_membrane_a",
        target_subsystems=["cell_membrane_b"],
        topic="membrane.contracts",
        channel="cell_membrane_a:cell_membrane_b",
    )
    event = HormoneEvent(
        signal_type=HormoneSignalType.CONTRACT_DRIFT,
        scope=scope,
        payload={"mismatched_symbol": "verify_receipt", "expected_version": 2},
    )
    assert len(event.payload_sha256) == 64
    assert event.correlation_id.startswith("corr_")
    assert event.causation_id is None
    assert event.ttl_seconds == 300.0


def test_scoped_hormone_bus_protocol_conformance() -> None:
    """Verify that ScopedHormoneBus conforms to HormoneBusProtocol."""
    bus = ScopedHormoneBus()
    assert isinstance(bus, HormoneBusProtocol)


def test_scoped_hormone_bus_targeted_delivery() -> None:
    """Verify that hormone signals only reach targeted subscribers, preventing broadcast storms."""
    bus = ScopedHormoneBus()

    # Subsystem B and C subscribe to contract drift topic
    bus.subscribe("subsystem_b", ["membrane.contracts"])
    bus.subscribe("subsystem_c", ["membrane.contracts"])
    bus.subscribe("unrelated_subsystem", ["substrate.gates"])

    # Producer A targets ONLY subsystem B
    scope = HormoneScope(
        producer_subsystem="subsystem_a",
        target_subsystems=["subsystem_b"],
        topic="membrane.contracts",
        channel="subsystem_a:subsystem_b",
    )
    event = HormoneEvent(
        signal_type=HormoneSignalType.CONTRACT_DRIFT,
        scope=scope,
        payload={"contract": "AuthInterface", "status": "drift_detected"},
    )
    bus.publish(event)

    # Subsystem B must receive the event
    events_b = bus.poll_events("subsystem_b")
    assert len(events_b) == 1
    assert events_b[0].signal_type == HormoneSignalType.CONTRACT_DRIFT

    # Subsystem C is subscribed to the topic, but was NOT targeted in scope -> receives ZERO events
    events_c = bus.poll_events("subsystem_c")
    assert len(events_c) == 0

    # Unrelated subsystem receives ZERO events
    events_unrelated = bus.poll_events("unrelated_subsystem")
    assert len(events_unrelated) == 0

    # Polling again yields empty list (consumed)
    assert len(bus.poll_events("subsystem_b")) == 0


def test_scoped_hormone_bus_wildcard_subscription() -> None:
    """Verify wildcard topic subscription for debugging/audit monitors."""
    bus = ScopedHormoneBus()
    bus.subscribe("audit_logger", topics=None)  # Wildcard

    scope = HormoneScope(
        producer_subsystem="substrate_runner",
        target_subsystems=["audit_logger"],
        topic="substrate.failure",
        channel="substrate:audit",
    )
    event = HormoneEvent(
        signal_type=HormoneSignalType.TEST_FAILURE,
        scope=scope,
        payload={"failed_test": "test_auth_boundary"},
    )
    bus.publish(event)

    events = bus.poll_events("audit_logger")
    assert len(events) == 1
    assert events[0].payload["failed_test"] == "test_auth_boundary"


def test_scoped_hormone_bus_poll_limits_and_unsubscribed_target() -> None:
    """Verify max_events truncation and delivery to unsubscribed targets."""
    bus = ScopedHormoneBus()
    bus.subscribe("receiver", ["topic.alpha"])

    # Publish 15 events to both a subscribed and an unsubscribed target
    for i in range(15):
        scope = HormoneScope(
            producer_subsystem="sender",
            target_subsystems=["receiver", "unsubscribed_agent"],
            topic="topic.alpha",
            channel="sender:receiver",
        )
        event = HormoneEvent(
            signal_type=HormoneSignalType.CONCURRENCY_PRESSURE,
            scope=scope,
            payload={"index": i},
        )
        ret_id = bus.publish(event)
        assert ret_id == event.event_id

    # Poll with default max_events=10 -> must return exactly 10
    first_batch = bus.poll_events("receiver")
    assert len(first_batch) == 10
    for idx, ev in enumerate(first_batch):
        assert ev.payload["index"] == idx

    # Poll remaining 5 events
    second_batch = bus.poll_events("receiver")
    assert len(second_batch) == 5
    for idx, ev in enumerate(second_batch):
        assert ev.payload["index"] == idx + 10

    # Unsubscribed agent received 0 events
    assert len(bus.poll_events("unsubscribed_agent")) == 0
