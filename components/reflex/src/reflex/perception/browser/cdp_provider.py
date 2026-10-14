"""Reflex Browser Observation Provider: CDP and DOM distillation ingestion."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field, replace
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple, Union
import uuid

from reflex.ports.clock import ClockPort, SystemClock
from reflex.ports.observation import ObservationPort
from reflex.schemas.observation import (
    CorruptedObservationError,
    ObservationQuality,
    ObservationRecord,
    PerceptionError,
    validate_screenshot_bytes,
)
from reflex.schemas.state import (
    BoundingBox,
    CanonicalUIGraph,
    ModalitySource,
    NodeRole,
    UIStateNode,
)


class CDPSessionProtocol(Protocol):
    """Protocol for Chrome DevTools Protocol (CDP) client connections."""

    async def send(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        ...


@dataclass
class FakeCDPClient:
    """In-memory Fake CDP Client for testing and deterministic offline evaluation."""

    ax_tree: Dict[str, Any] = field(default_factory=lambda: {"nodes": []})
    flattened_document: Dict[str, Any] = field(default_factory=lambda: {"nodes": []})
    box_models: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    eval_result: Optional[Dict[str, Any]] = None
    screenshot_bytes: bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRfake_png_cdp_bytes"
    url: str = "http://localhost:8000/fixture"
    title: str = "Test Fixture Page"
    viewport_size: Optional[Tuple[int, int]] = None
    sent_commands: List[Tuple[str, Optional[Dict[str, Any]]]] = field(default_factory=list)

    async def send(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.sent_commands.append((method, params))
        if method == "Accessibility.getFullAXTree":
            return self.ax_tree
        elif method == "DOM.getFlattenedDocument" or method == "DOM.getDocument":
            return self.flattened_document
        elif method == "DOM.getBoxModel":
            backend_id = params.get("backendNodeId", 0) if params else 0
            if backend_id in self.box_models:
                return {"model": self.box_models[backend_id]}
            return {
                "model": {
                    "content": [0, 0, 100, 0, 100, 30, 0, 30],
                    "width": 100,
                    "height": 30,
                }
            }
        elif method == "Runtime.evaluate":
            if self.eval_result is not None:
                return {"result": {"type": "object", "value": self.eval_result}}
            value: Dict[str, Any] = {
                "url": self.url,
                "title": self.title,
                "nodes": {},
            }
            if self.viewport_size is not None:
                value["viewport_size"] = list(self.viewport_size)
            return {"result": {"type": "object", "value": value}}
        elif method == "Page.captureScreenshot":
            return {"data": base64.b64encode(self.screenshot_bytes).decode("utf-8")}
        elif method == "Target.getTargetInfo":
            return {"targetInfo": {"url": self.url, "title": self.title}}
        return {}


class CDPObservationProvider(ObservationPort):
    """Observation adapter extracting canonical UI state graphs from Chromium via CDP or Playwright."""

    def __init__(
        self,
        cdp_session: Optional[CDPSessionProtocol] = None,
        page: Optional[Any] = None,
        clock: Optional[ClockPort] = None,
        viewport_size: Tuple[int, int] = (1920, 1080),
        prefer_js_distiller: bool = True,
    ) -> None:
        self.cdp_session = cdp_session
        self.page = page
        self.clock = clock or SystemClock()
        self.viewport_size = viewport_size
        self.prefer_js_distiller = prefer_js_distiller
        self._distiller_script: Optional[str] = None
        self._session_epoch = uuid.uuid4().hex
        self.target_id: Optional[str] = getattr(page, "target_id", None)
        self._last_tree_error: Optional[str] = None
        self._last_distilled_revision: Any = None
        self._observed_pixel_size: Optional[Tuple[int, int]] = None

    def _effective_viewport(self) -> Tuple[int, int]:
        """Observed pixel dimensions once captured, else the requested size."""
        return self._observed_pixel_size or self.viewport_size

    @property
    def session_epoch(self) -> str:
        """Current source session epoch; rotates on restart/reconnect."""
        return self._session_epoch

    def new_epoch(self) -> str:
        """Rotates the session epoch after a disconnect/restart.

        Observations captured after rotation carry the new epoch; references
        bound to the previous epoch must be revalidated, never silently reused.
        """
        self._session_epoch = uuid.uuid4().hex
        return self._session_epoch

    async def capture_observation(self) -> ObservationRecord:
        """Captures an observation stamped with real source identity and epoch.

        Tree acquisition faults are preserved (never a silent valid-empty
        tree), and the tree is re-read after pixel capture: a pre/post
        mismatch proves a cross-modality tear and degrades the observation
        with an explicit asynchronous binding record.
        """
        self._last_tree_error = None
        self._last_distilled_revision = None
        obs = await super().capture_observation()
        tree_error_1 = self._last_tree_error
        revision_1 = self._last_distilled_revision
        post_graph = await self.capture_state()
        tree_error_2 = self._last_tree_error
        revision_2 = self._last_distilled_revision
        torn = post_graph.compute_evidence_hash() != obs.graph.compute_evidence_hash()

        modality_status = dict(obs.platform_metadata.get("modality_status", {}))
        errors: List[str] = [obs.error_message] if obs.error_message else []
        tree_fault = tree_error_1 or tree_error_2
        if tree_fault is not None:
            modality_status["tree"] = f"fault: {tree_fault}"
            errors.append(f"Tree acquisition fault: {tree_fault}")
        if torn:
            errors.append(
                "Cross-modality tear: tree evidence changed across pixel capture; "
                "tree and pixels are not bound to the same state."
            )
        if torn:
            binding: Dict[str, Any] = {
                "same_state": False,
                "status": "asynchronous",
                "requires_target_revalidation": True,
                "tree_revision": revision_1,
                "pixel_revision": revision_2,
                "evidence": "pre/post tree evidence hashes differ across pixel capture",
            }
        else:
            binding = {
                "same_state": True,
                "status": "pre-post-consistent",
                "requires_target_revalidation": False,
                "tree_revision": revision_1,
                "pixel_revision": revision_2,
                "evidence": "pre/post tree evidence hashes identical; atomicity not proven",
            }

        quality = obs.quality
        if quality != ObservationQuality.CORRUPTED and (tree_fault is not None or torn):
            quality = ObservationQuality.DEGRADED

        if obs.screenshot_bytes is not None and self.page is not None:
            updater = getattr(self.page, "update_observed_viewport", None)
            if callable(updater):
                try:
                    width, height = validate_screenshot_bytes(obs.screenshot_bytes)
                    updater(width, height)
                    self._observed_pixel_size = (width, height)
                except CorruptedObservationError:
                    pass

        metadata = dict(obs.platform_metadata)
        metadata.update(
            {
                "session_epoch": self._session_epoch,
                # Warm/tracking binding epochs (tracking HANDOFF Q1): surface
                # follows the source session; document follows target+url+title.
                # Same-URL SPA navigation without target/url/title change is a
                # known gap (future loader/nav counter), never silently bridged.
                "surface_epoch": self._session_epoch,
                "document_epoch": self._document_epoch(obs.graph),
                "declared_viewport": [self.viewport_size[0], self.viewport_size[1]],
                "target_id": self.target_id,
                "modality_status": modality_status,
                "capture_binding": binding,
            }
        )
        return replace(
            obs,
            source_adapter="cdp_chromium",
            platform="linux",
            quality=quality,
            error_message="; ".join(errors) if errors else None,
            platform_metadata=metadata,
        )

    def _document_epoch(self, graph) -> str:
        """Document identity for one captured graph: target + url + title.

        Any change resyncs tracking/warm bindings; unknown parts hash as "".
        """
        target = self.target_id or ""
        url = graph.url or ""
        title = graph.active_window_title or ""
        return hashlib.sha256(f"{target}\n{url}\n{title}".encode("utf-8")).hexdigest()[:16]

    def _load_distiller_script(self) -> str:
        if self._distiller_script is None:
            script_path = Path(__file__).parent / "dom_distiller.js"
            if script_path.exists():
                self._distiller_script = script_path.read_text(encoding="utf-8")
            else:
                self._distiller_script = ""
        return self._distiller_script

    @staticmethod
    def map_role(role_name: Optional[str], tag_name: Optional[str] = None) -> NodeRole:
        """Maps arbitrary DOM/ARIA role strings to standard NodeRole enum."""
        if not role_name and tag_name:
            tag = tag_name.upper()
            if tag == "BUTTON":
                return NodeRole.BUTTON
            elif tag in ("INPUT", "TEXTAREA", "SELECT"):
                return NodeRole.INPUT
            elif tag == "A":
                return NodeRole.LINK
            elif tag in ("H1", "H2", "H3", "H4", "H5", "H6", "P", "SPAN", "LABEL", "STRONG", "EM"):
                return NodeRole.TEXT
            elif tag in ("IMG", "CANVAS", "SVG"):
                return NodeRole.IMAGE
            elif tag in ("DIALOG",):
                return NodeRole.MODAL
            elif tag in ("NAV", "MAIN", "SECTION", "ARTICLE", "FORM", "TABLE", "DIV", "HEADER", "FOOTER"):
                return NodeRole.CONTAINER
            return NodeRole.UNKNOWN

        r = (role_name or "").lower().strip()
        if r in ("button", "menuitembutton"):
            return NodeRole.BUTTON
        elif r in ("textbox", "searchbox", "input", "combobox", "spinbutton"):
            return NodeRole.INPUT
        elif r == "checkbox":
            return NodeRole.CHECKBOX
        elif r == "radio":
            return NodeRole.RADIO
        elif r in ("switch", "toggle"):
            return NodeRole.TOGGLE
        elif r in ("link", "tab"):
            return NodeRole.LINK
        elif r in ("heading", "text", "statictext", "paragraph", "label", "caption", "code"):
            return NodeRole.TEXT
        elif r in ("image", "img", "graphic", "figure"):
            return NodeRole.IMAGE
        elif r in ("dialog", "alertdialog", "modal"):
            return NodeRole.MODAL
        elif r == "scrollbar":
            return NodeRole.SCROLLBAR
        elif r in ("container", "region", "group", "main", "navigation", "form", "table", "row", "cell", "grid", "list", "listitem", "tree"):
            return NodeRole.CONTAINER
        return NodeRole.UNKNOWN

    def _parse_raw_attributes(self, raw_attrs: Union[List[str], Dict[str, Any]]) -> Dict[str, Any]:
        """Parses CDP list-of-pairs attribute format [key1, val1, key2, val2] or dict format."""
        if isinstance(raw_attrs, dict):
            return dict(raw_attrs)
        attrs: Dict[str, Any] = {}
        if isinstance(raw_attrs, list):
            for i in range(0, len(raw_attrs) - 1, 2):
                attrs[str(raw_attrs[i])] = raw_attrs[i + 1]
        return attrs

    async def capture_state(self) -> CanonicalUIGraph:
        """Captures the current canonical UI state graph from the active browser session.

        A real acquisition fault is recorded in _last_tree_error and yields an
        explicitly faulted empty graph; only a genuinely empty tree with no
        fault reads as valid-empty.
        """
        timestamp_ms = self.clock.now_ms()
        try:
            # 1. If Playwright page handle is available
            if self.page is not None:
                return await self._capture_from_playwright_page(timestamp_ms)

            # 2. If CDP session is available
            if self.cdp_session is not None:
                if self.prefer_js_distiller:
                    try:
                        return await self._capture_via_js_distiller_cdp(timestamp_ms)
                    except Exception:
                        # Fall back to protocol CDP inspection
                        return await self._capture_via_protocol_cdp(timestamp_ms)
                else:
                    return await self._capture_via_protocol_cdp(timestamp_ms)
        except Exception as exc:
            self._last_tree_error = f"{type(exc).__name__}: {exc}"

        # 3. Empty default graph (unbound provider, or faulted acquisition above)
        return CanonicalUIGraph(
            timestamp_ms=timestamp_ms,
            nodes={},
            viewport_size=self._effective_viewport(),
        )

    async def _capture_from_playwright_page(self, timestamp_ms: float) -> CanonicalUIGraph:
        """Executes distillation on a Playwright Page instance."""
        script = self._load_distiller_script()
        distilled_data: Dict[str, Any] = {}

        if script:
            try:
                distilled_data = await self.page.evaluate(script)
                if not isinstance(distilled_data, dict):
                    distilled_data = await self.page.evaluate(f"() => {{ {script} }}")
            except Exception as first_exc:
                try:
                    distilled_data = await self.page.evaluate(f"() => {{ {script} }}")
                except Exception as second_exc:
                    distilled_data = {}
                    self._last_tree_error = (
                        f"{type(second_exc).__name__}: {second_exc} "
                        f"(primary evaluate also failed: {type(first_exc).__name__})"
                    )

        return self._build_graph_from_distilled_dict(distilled_data, timestamp_ms)


    async def _capture_via_js_distiller_cdp(self, timestamp_ms: float) -> CanonicalUIGraph:
        """Executes dom_distiller.js via CDP Runtime.evaluate."""
        script = self._load_distiller_script()
        resp = await self.cdp_session.send(  # type: ignore
            "Runtime.evaluate",
            {
                "expression": script,
                "returnByValue": True,
                "awaitPromise": True,
            },
        )
        result_obj = resp.get("result", {})
        value = result_obj.get("value")
        if isinstance(value, dict):
            return self._build_graph_from_distilled_dict(value, timestamp_ms)
        elif isinstance(value, str):
            try:
                parsed = json.loads(value)
                return self._build_graph_from_distilled_dict(parsed, timestamp_ms)
            except json.JSONDecodeError:
                pass
        return self._build_graph_from_distilled_dict({}, timestamp_ms)

    async def _capture_via_protocol_cdp(self, timestamp_ms: float) -> CanonicalUIGraph:
        """Captures state by querying DOM.getFlattenedDocument and Accessibility.getFullAXTree."""
        assert self.cdp_session is not None

        # Request flattened DOM and AX tree
        dom_resp = await self.cdp_session.send("DOM.getFlattenedDocument", {"depth": -1, "pierce": True})
        ax_resp = await self.cdp_session.send("Accessibility.getFullAXTree", {"depth": -1})

        dom_nodes_raw = dom_resp.get("nodes", [])
        ax_nodes_raw = ax_resp.get("nodes", [])

        # Index AX nodes by backendDOMNodeId
        ax_by_backend_id: Dict[int, Dict[str, Any]] = {}
        for ax_node in ax_nodes_raw:
            b_id = ax_node.get("backendDOMNodeId")
            if b_id:
                ax_by_backend_id[b_id] = ax_node

        nodes: Dict[str, UIStateNode] = {}

        for d_node in dom_nodes_raw:
            node_type = d_node.get("nodeType")
            if node_type != 1:  # Only Element nodes
                continue

            node_id_int = d_node.get("nodeId", 0)
            backend_id = d_node.get("backendNodeId", 0)
            node_name = d_node.get("nodeName", "")
            raw_attrs = self._parse_raw_attributes(d_node.get("attributes", []))
            parent_id_int = d_node.get("parentId")
            parent_id_str = f"node_{parent_id_int}" if parent_id_int else None

            # Skip noise tags
            if node_name.upper() in ("SCRIPT", "STYLE", "META", "HEAD", "LINK", "NOSCRIPT", "TEMPLATE"):
                continue

            # Query box model
            box_x1, box_y1, box_x2, box_y2 = 0, 0, 0, 0
            try:
                box_resp = await self.cdp_session.send("DOM.getBoxModel", {"backendNodeId": backend_id})
                model = box_resp.get("model", {})
                content = model.get("content", [])
                if len(content) >= 8:
                    xs = [content[0], content[2], content[4], content[6]]
                    ys = [content[1], content[3], content[5], content[7]]
                    box_x1, box_y1, box_x2, box_y2 = int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))
            except Exception:
                pass

            bounds = BoundingBox(x1=box_x1, y1=box_y1, x2=box_x2, y2=box_y2)

            # AX properties
            ax_node = ax_by_backend_id.get(backend_id, {})
            ax_role = ax_node.get("role", {}).get("value") if isinstance(ax_node.get("role"), dict) else ax_node.get("role")
            ax_name = ax_node.get("name", {}).get("value") if isinstance(ax_node.get("name"), dict) else ax_node.get("name")
            ax_value = ax_node.get("value", {}).get("value") if isinstance(ax_node.get("value"), dict) else ax_node.get("value")

            role = self.map_role(ax_role, node_name)
            label = str(ax_name or raw_attrs.get("aria-label") or raw_attrs.get("placeholder") or raw_attrs.get("title") or "").strip()
            value = str(ax_value or raw_attrs.get("value") or "").strip()

            node_id_str = f"node_{node_id_int}" if node_id_int else f"node_b{backend_id}"

            is_clickable = role in (NodeRole.BUTTON, NodeRole.LINK, NodeRole.CHECKBOX, NodeRole.RADIO, NodeRole.TOGGLE) or "onclick" in raw_attrs
            is_editable = role == NodeRole.INPUT and node_name.upper() in ("INPUT", "TEXTAREA")
            is_enabled = not (raw_attrs.get("disabled") is not None or raw_attrs.get("aria-disabled") == "true")

            node = UIStateNode(
                node_id=node_id_str,
                role=role,
                bounds=bounds,
                label=label,
                value=value,
                is_clickable=is_clickable,
                is_editable=is_editable,
                is_focused=bool(ax_node.get("focused", {}).get("value", False) if isinstance(ax_node.get("focused"), dict) else ax_node.get("focused", False)),
                is_enabled=is_enabled,
                parent_id=parent_id_str,
                children_ids=[],
                source=ModalitySource.DOM,
                confidence=1.0,
                attributes=raw_attrs,
            )
            nodes[node_id_str] = node

        # Build children ids by rebuilding parents (nodes are immutable once built).
        children_by_parent: Dict[str, List[str]] = {}
        for n_id, n in nodes.items():
            if n.parent_id and n.parent_id in nodes:
                children_by_parent.setdefault(n.parent_id, [])
                if n_id not in children_by_parent[n.parent_id]:
                    children_by_parent[n.parent_id].append(n_id)
        for parent_id, child_ids in children_by_parent.items():
            parent = nodes[parent_id]
            nodes[parent_id] = replace(
                parent, children_ids=list(parent.children_ids) + child_ids
            )

        return CanonicalUIGraph(
            timestamp_ms=timestamp_ms,
            nodes=nodes,
            viewport_size=self._effective_viewport(),
        )

    def _build_graph_from_distilled_dict(
        self, distilled: Dict[str, Any], timestamp_ms: float
    ) -> CanonicalUIGraph:
        """Converts raw distillation JSON dictionary into CanonicalUIGraph."""
        self._last_distilled_revision = distilled.get("document_revision")
        url = distilled.get("url")
        title = distilled.get("title")
        raw_viewport = distilled.get("viewport_size", None) or self._effective_viewport()
        viewport_size = (int(raw_viewport[0]), int(raw_viewport[1]))
        focused_node_id = distilled.get("focused_node_id")

        raw_nodes = distilled.get("nodes", {})
        nodes: Dict[str, UIStateNode] = {}

        if isinstance(raw_nodes, list):
            # List format
            for item in raw_nodes:
                node = self._build_node_from_raw(item)
                nodes[node.node_id] = node
        elif isinstance(raw_nodes, dict):
            # Dict format
            for node_key, item in raw_nodes.items():
                if "node_id" not in item:
                    item["node_id"] = str(node_key)
                node = self._build_node_from_raw(item)
                nodes[node.node_id] = node

        return CanonicalUIGraph(
            timestamp_ms=timestamp_ms,
            nodes=nodes,
            focused_node_id=focused_node_id,
            active_window_title=title,
            url=url,
            viewport_size=viewport_size,
        )

    def _build_node_from_raw(self, item: Dict[str, Any]) -> UIStateNode:
        """Builds a single UIStateNode from a dictionary item."""
        node_id = str(item.get("node_id", "unknown_node"))
        raw_role = item.get("role", "unknown")
        tag_name = item.get("tag")
        role = self.map_role(str(raw_role), tag_name)

        bounds_data = item.get("bounds", {})
        if isinstance(bounds_data, (list, tuple)) and len(bounds_data) == 4:
            bounds = BoundingBox(
                x1=int(bounds_data[0]), y1=int(bounds_data[1]),
                x2=int(bounds_data[2]), y2=int(bounds_data[3]),
            )
        elif isinstance(bounds_data, dict):
            bounds = BoundingBox(
                x1=int(bounds_data.get("x1", 0)),
                y1=int(bounds_data.get("y1", 0)),
                x2=int(bounds_data.get("x2", 0)),
                y2=int(bounds_data.get("y2", 0)),
            )
        else:
            raise PerceptionError(
                f"Node '{item.get('node_id', '?')}' has malformed bounds: {bounds_data!r}"
            )

        label = str(item.get("label", ""))
        value = str(item.get("value", ""))
        is_clickable = bool(item.get("is_clickable", True))
        is_editable = bool(item.get("is_editable", False))
        is_focused = bool(item.get("is_focused", False))
        is_enabled = bool(item.get("is_enabled", True))
        parent_id = str(item.get("parent_id")) if item.get("parent_id") is not None else None
        children_ids = [str(c) for c in item.get("children_ids", [])]
        attributes = dict(item.get("attributes", {}))

        return UIStateNode(
            node_id=node_id,
            role=role,
            bounds=bounds,
            label=label,
            value=value,
            is_clickable=is_clickable,
            is_editable=is_editable,
            is_focused=is_focused,
            is_enabled=is_enabled,
            parent_id=parent_id,
            children_ids=children_ids,
            source=ModalitySource.DOM,
            confidence=float(item.get("confidence", 1.0)),
            attributes=attributes,
        )

    async def capture_screenshot(self) -> bytes:
        """Captures raw viewport screenshot bytes from the active session.

        Raises PerceptionError when no page or CDP session is bound: an
        unbound source has no pixels, and must never emit dummy bytes.
        """
        if self.page is not None:
            return await self.page.screenshot(type="png")

        if self.cdp_session is not None:
            resp = await self.cdp_session.send("Page.captureScreenshot", {"format": "png"})
            data_b64 = resp.get("data", "")
            if data_b64:
                return base64.b64decode(data_b64)
            raise PerceptionError("CDP Page.captureScreenshot returned no pixel data.")

        raise PerceptionError("CDPObservationProvider has no bound page or CDP session.")
