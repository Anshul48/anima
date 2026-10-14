"""Thin local Reflex perception service: same ObservationPort contract, separate process.

Stdlib only (http.server + urllib): no new dependencies. The server binds one
ObservationPort (live CDP source or ReplaySource) and serves JSON over
localhost. PNG pixels travel as base64 alongside the observation dict, with
their SHA-256 digest for independent verification.

Routes:
  GET  /healthz            -> {status, source_adapter, session/recording identity}
  POST /observe             -> {observation: {...}, screenshot_b64|null, png_sha256|null}
  POST /update              -> {previous_observation_id} captures current, returns
                               {observation, delta, screenshot_b64|null, png_sha256|null};
                               unknown previous IDs are explicit 404 unavailable-reference.
  POST /query               -> {observation_id, selector:{by,id|role|label,value}}
                               returns matching nodes from the retained snapshot.
  POST /shutdown            -> clean stop for bounded runner scripts.
"""

from __future__ import annotations

from reflex.service.client import PerceptionServiceClient, ServiceError
from reflex.service.server import PerceptionServiceServer, serve_forever

__all__ = [
    "PerceptionServiceClient",
    "PerceptionServiceServer",
    "ServiceError",
    "serve_forever",
]
