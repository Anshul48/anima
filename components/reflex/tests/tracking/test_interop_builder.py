"""Candidate-native interop: tracking outputs convert via builder schemas 1:1."""

from reflex.perception.tracking.adapters import (
    ModelRunAdapter,
    static_parse_to_node_dicts,
)
from reflex.schemas.observation import ObservationRecord
from reflex.schemas.state import CanonicalUIGraph, UIStateNode
from reflex.perception.tracking.frame import frame_from_observation_dict
from tests.tracking.synth_fixtures import make_frec


def test_node_dicts_convert_via_builder_schema():
    parse = ModelRunAdapter(source_id="iop").parse_frame_record(make_frec())
    nodes, _ = static_parse_to_node_dicts(parse)
    assert len(nodes) == 2
    n0 = UIStateNode.from_dict(nodes[0])
    assert n0.source.value == "vision"
    assert n0.attributes["pixel_sha256"] == "aa" * 32
    assert n0.to_dict()["node_id"] == nodes[0]["node_id"]


def test_obs_bridge_accepts_real_builder_record_dict():
    graph = CanonicalUIGraph(timestamp_ms=1000.0, nodes={})
    rec = ObservationRecord(
        observation_id="obs-real-shape", timestamp_ms=1000.0,
        source_adapter="BrowserSource", platform="linux", graph=graph,
    )
    frame, _unsupported = frame_from_observation_dict(
        rec.to_dict(), pixel_sha256="ee" * 32, width_px=800, height_px=600)
    assert frame.frame_id == "obs-real-shape"
    assert frame.source_id == "BrowserSource/linux"
    assert frame.has_pixels()
