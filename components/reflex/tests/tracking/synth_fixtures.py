"""SYNTHETIC-ONLY fixtures. Hand-built dicts mimicking the model worker's
per-frame record schema (10_run_static_perception.py frec). Not model output,
not performance evidence. Real-inference validation is a separate gate."""

from __future__ import annotations

import copy
from typing import Any, Dict

SYNTHETIC_TAG = "synthetic-fixture-NOT-model-output"


def make_frec(
    fname: str = "frame_0.png",
    sha: str = "aa" * 32,
    width: int = 800,
    height: int = 600,
) -> Dict[str, Any]:
    return {
        "_synthetic": SYNTHETIC_TAG,
        "file": fname,
        "sha256": sha,
        "width": width,
        "height": height,
        "condition": "warm",
        "components": {
            "ocr": {"backend": "ocr_PP-OCRv6_tiny_det_PP-OCRv6_small_rec", "ms": 12.0,
                    "peak_gpu_mb": None, "num_entries": 2},
            "regions": {"backend": "regions_omniparser_v3", "ms": 30.0,
                        "peak_gpu_mb": None, "num_boxes": 2},
            "caption": {"backend": "caption_florence", "ms": 50.0,
                        "peak_gpu_mb": None, "num_captioned": 1,
                        "num_skipped_has_ocr_labels": 1},
        },
        "failures": [],
        "merge": {"ms": 0.5, "stats": {"detector_raw": 2,
                 "detector_after_self_suppress": 2, "detector_final": 2,
                 "ocr_consumed": 1}},
        "ocr": [
            {"polygon_xy": [[10, 10], [90, 10], [90, 30], [10, 30]],
             "box_xyxy": [10, 10, 90, 30], "text": "Apply",
             "confidence": 0.997, "ocr_id": 0, "consumed_by_region": 0},
            {"polygon_xy": [[200, 400], [260, 400], [260, 420], [200, 420]],
             "box_xyxy": [200, 400, 260, 420], "text": "Cancel",
             "confidence": 0.91, "ocr_id": 1, "consumed_by_region": None},
        ],
        "regions": [
            {"box_xyxy": [5, 5, 100, 40], "score": 0.82,
             "merge_source": "box_yolo_content_ocr", "ocr_labels": "Apply",
             "region_id": 0},
            {"box_xyxy": [300, 300, 360, 360], "score": 0.44,
             "merge_source": "box_yolo_content_yolo", "ocr_labels": "",
             "region_id": 1},
        ],
        "captions": [
            {"region_id": 1, "hypothesis_text": "opens settings panel",
             "uncertainty": {"mean_token_logprob": -0.62, "num_tokens": 4,
                             "scored_steps": 4},
             "prompt": "<CAPTION>",
             "crop": {"box_xyxy": [300, 300, 360, 360], "resized_to": [64, 64]},
             "nearby_texts": [{"ocr_id": 1, "text": "Cancel", "confidence": 0.91}]},
        ],
        "global_context": {"frame_xyxy": [0, 0, width, height],
                           "num_ocr": 2, "num_regions": 2, "num_captions": 1},
    }


def failed_component_frec(component: str) -> Dict[str, Any]:
    frec = make_frec()
    frec[component] = None
    frec["failures"] = [{"component": component, "error": f"ValueError('{component} broke')"}]
    return copy.deepcopy(frec)


def make_obs_dict(obs_id: str = "obs-1", quality: str = "healthy") -> Dict[str, Any]:
    return {
        "observation_id": obs_id,
        "timestamp_ms": 1_700_000_000_000.0,
        "source_adapter": "BrowserSource",
        "platform": "linux",
        "graph": {"timestamp_ms": 1_700_000_000_000.0, "nodes": {},
                  "focused_node_id": None, "active_window_title": "t",
                  "url": "http://app/", "viewport_size": [800, 600]},
        "quality": quality,
        "freshness_duration_ms": 500.0,
        "error_message": None,
        "platform_metadata": {"adapter_class": "BrowserSource",
                              "modality_status": {"tree": "ok", "screenshot": "ok: 800x600"}},
    }
