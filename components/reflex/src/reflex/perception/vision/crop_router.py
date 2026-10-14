"""Reflex Crop and Route Engine: Extracts native-resolution crops, formats base64, and attaches spatial metadata."""

from __future__ import annotations

import base64
import io
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from PIL import Image

from reflex.schemas.fallback import CropPacket
from reflex.schemas.state import BoundingBox


class CropAndRouteEngine:
    """Crops native-resolution bounding box regions from screenshots and packages CropPacket payloads.

    To eliminate the O(N^2) computational overhead and token cost of full-screen VLM inference,
    this router isolates target interaction bounding boxes, calculates their spatial screen quadrant,
    injects container and semantic role metadata, and produces high-resolution lossless base64 crops.
    """

    def __init__(self, default_format: str = "PNG") -> None:
        self.default_format = default_format

    def compute_quadrant(
        self,
        bounds: Union[BoundingBox, Tuple[int, int, int, int]],
        viewport_width: int,
        viewport_height: int,
    ) -> str:
        """Determines the screen position quadrant of a bounding box.

        Possible values: 'Top-Left', 'Top-Right', 'Bottom-Left', 'Bottom-Right', 'Center'.
        """
        if viewport_width <= 0 or viewport_height <= 0:
            return "Center"

        if isinstance(bounds, BoundingBox):
            x1, y1, x2, y2 = bounds.x1, bounds.y1, bounds.x2, bounds.y2
        else:
            x1, y1, x2, y2 = int(bounds[0]), int(bounds[1]), int(bounds[2]), int(bounds[3])

        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0

        rx = cx / float(viewport_width)
        ry = cy / float(viewport_height)

        # Center band: 33% to 67% on both axes
        if 0.33 <= rx <= 0.67 and 0.33 <= ry <= 0.67:
            return "Center"

        vertical = "Top" if ry < 0.5 else "Bottom"
        horizontal = "Left" if rx < 0.5 else "Right"
        return f"{vertical}-{horizontal}"

    def crop_region(
        self,
        frame_bytes: bytes,
        bounds: Union[BoundingBox, Tuple[int, int, int, int]],
        parent_label: str = "",
        element_role: str = "",
        task_context: str = "",
        image_format: Optional[str] = None,
    ) -> CropPacket:
        """Extracts a native-resolution crop from screenshot bytes and returns a CropPacket."""
        fmt = image_format or self.default_format

        with Image.open(io.BytesIO(frame_bytes)) as img:
            img_w, img_h = img.size

            if isinstance(bounds, BoundingBox):
                x1, y1, x2, y2 = bounds.x1, bounds.y1, bounds.x2, bounds.y2
            else:
                x1, y1, x2, y2 = int(bounds[0]), int(bounds[1]), int(bounds[2]), int(bounds[3])

            # Ensure valid non-inverted coordinate ordering
            x_min = min(x1, x2)
            x_max = max(x1, x2)
            y_min = min(y1, y2)
            y_max = max(y1, y2)

            # Clamp coordinates to image viewport
            cx1 = max(0, min(img_w, x_min))
            cy1 = max(0, min(img_h, y_min))
            cx2 = max(cx1, min(img_w, x_max))
            cy2 = max(cy1, min(img_h, y_max))

            # Handle zero-area box by enforcing minimum 1x1 crop if possible
            if cx2 <= cx1:
                cx2 = min(img_w, cx1 + 1)
            if cy2 <= cy1:
                cy2 = min(img_h, cy1 + 1)

            cropped = img.crop((cx1, cy1, cx2, cy2))

            out_buf = io.BytesIO()
            cropped.save(out_buf, format=fmt)
            crop_bytes = out_buf.getvalue()
            crop_base64 = base64.b64encode(crop_bytes).decode("utf-8")

            quadrant = self.compute_quadrant((cx1, cy1, cx2, cy2), img_w, img_h)

            return CropPacket(
                bounding_box=(cx1, cy1, cx2, cy2),
                crop_base64=crop_base64,
                parent_label=parent_label,
                element_role=element_role,
                screen_position_quadrant=quadrant,
                task_context=task_context,
            )

    def batch_crop(
        self,
        frame_bytes: bytes,
        targets: Sequence[Union[
            Tuple[Union[BoundingBox, Tuple[int, int, int, int]], str, str],
            Dict[str, Any],
            BoundingBox,
        ]],
        task_context: str = "",
        image_format: Optional[str] = None,
    ) -> List[CropPacket]:
        """Performs batch crop extraction from a single frame buffer."""
        packets: List[CropPacket] = []
        for target in targets:
            if isinstance(target, (tuple, list)) and len(target) >= 3:
                box = target[0]
                parent = str(target[1])
                role = str(target[2])
                ctx = str(target[3]) if len(target) > 3 else task_context
            elif isinstance(target, dict):
                box = target.get("bounding_box") or target.get("bounds")
                parent = str(target.get("parent_label", ""))
                role = str(target.get("element_role", ""))
                ctx = str(target.get("task_context", task_context))
            elif isinstance(target, BoundingBox):
                box = target
                parent = ""
                role = ""
                ctx = task_context
            else:
                box = target  # type: ignore[assignment]
                parent = ""
                role = ""
                ctx = task_context

            packet = self.crop_region(
                frame_bytes=frame_bytes,
                bounds=box,  # type: ignore[arg-type]
                parent_label=parent,
                element_role=role,
                task_context=ctx,
                image_format=image_format,
            )
            packets.append(packet)

        return packets

    @staticmethod
    def decode_crop(crop_packet: CropPacket) -> bytes:
        """Decodes base64 string from CropPacket back to raw image bytes."""
        return base64.b64decode(crop_packet.crop_base64.encode("utf-8"))
