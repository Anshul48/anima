"""Reflex Procedural Skill Extractor.

Mines recurring, successful sub-trajectories from golden episodes, parameterizes variable
text/slot inputs into Jinja/brace templates (e.g. {{user_email}}, {{query}}), strips
brittle absolute coordinates in favor of semantic locators, and computes deterministic
precondition hashes from DOM subgraphs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union
import uuid

from reflex.episodes.journal import EpisodeJournalPort
from reflex.episodes.redactor import PrivacyRedactor
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.memory import MotorSkill, TransitionTuple
from reflex.schemas.state import CanonicalUIGraph, NodeRole, UIStateNode


@dataclass(frozen=True)
class AffordanceItem:
    """Invariant descriptor of an interactable UI affordance."""

    role: str
    label: str
    is_clickable: bool = False
    is_editable: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "label": self.label,
            "is_clickable": self.is_clickable,
            "is_editable": self.is_editable,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AffordanceItem:
        return cls(
            role=str(data.get("role", "")),
            label=str(data.get("label", "")),
            is_clickable=bool(data.get("is_clickable", False)),
            is_editable=bool(data.get("is_editable", False)),
        )


@dataclass(frozen=True)
class AffordancePattern:
    """Invariant affordance pattern replacing brittle exact state hashes.

    Captures required application context (domain or window type) and required
    interactable affordances (roles and semantic labels) invariant to dynamic
    element IDs, coordinate shifts, or unrelated page changes.
    """

    app_or_domain: str
    required_affordances: Tuple[AffordanceItem, ...]
    pattern_signature: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "app_or_domain": self.app_or_domain,
            "required_affordances": [item.to_dict() for item in self.required_affordances],
            "pattern_signature": self.pattern_signature,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AffordancePattern:
        items = tuple(AffordanceItem.from_dict(d) for d in data.get("required_affordances", []))
        return cls(
            app_or_domain=str(data.get("app_or_domain", "")),
            required_affordances=items,
            pattern_signature=str(data.get("pattern_signature", "")),
        )


class SkillExtractor:
    """Extracts, parameterizes, and compiles procedural MotorSkill instances from episode journals."""

    # Heuristic regex patterns for slot detection
    EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
    URL_REGEX = re.compile(r"^https?://[^\s/$.?#].[^\s]*$")
    DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    PHONE_REGEX = re.compile(r"^\+?[\d\s\-\(\)]{7,15}$")
    NUMBER_REGEX = re.compile(r"^\d+(\.\d+)?$")

    def __init__(self, redactor: Optional[PrivacyRedactor] = None) -> None:
        self.redactor = redactor or PrivacyRedactor()

    # =========================================================================
    # Precondition Hashing
    # =========================================================================

    def compute_preconditions_hash(
        self,
        graph: CanonicalUIGraph,
        relevant_node_ids: Optional[Sequence[str]] = None,
    ) -> str:
        """Computes a deterministic SHA-256 precondition hash from a UI state graph or DOM subgraph.
        
        If relevant_node_ids is provided, hashes only that subgraph and its structural hierarchy.
        Otherwise, hashes all interactable affordances (buttons, inputs, links, etc.) and page context.
        """
        if relevant_node_ids:
            target_ids = set(relevant_node_ids)
            # Include parent containers if present
            for nid in list(target_ids):
                node = graph.nodes.get(nid)
                if node and node.parent_id:
                    target_ids.add(node.parent_id)
            nodes_to_hash = [n for nid, n in graph.nodes.items() if nid in target_ids]
        else:
            # Filter to interactable nodes or structural containers
            interactable_roles = {
                NodeRole.BUTTON,
                NodeRole.INPUT,
                NodeRole.CHECKBOX,
                NodeRole.RADIO,
                NodeRole.TOGGLE,
                NodeRole.LINK,
                NodeRole.MODAL,
            }
            nodes_to_hash = [
                n for n in graph.nodes.values()
                if n.is_clickable or n.is_editable or n.role in interactable_roles
            ]

        # Canonical deterministic serialization
        serialized_nodes = [
            {
                "id": n.node_id,
                "role": n.role.value if isinstance(n.role, NodeRole) else str(n.role),
                "label": self._normalize_label(n.label),
                "is_clickable": n.is_clickable,
                "is_editable": n.is_editable,
                "parent_id": n.parent_id,
                "children_count": len(n.children_ids),
            }
            for n in sorted(nodes_to_hash, key=lambda x: x.node_id)
        ]

        payload = {
            "url": self._normalize_url(graph.url),
            "window": graph.active_window_title or "",
            "nodes": serialized_nodes,
        }

        raw_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw_bytes).hexdigest()

    def compute_subgraph_hash(
        self,
        nodes: Sequence[UIStateNode],
        context_label: str = "",
    ) -> str:
        """Computes a precondition hash directly for an explicit sequence of UIStateNodes."""
        serialized_nodes = [
            {
                "id": n.node_id,
                "role": n.role.value if isinstance(n.role, NodeRole) else str(n.role),
                "label": self._normalize_label(n.label),
                "is_clickable": n.is_clickable,
                "is_editable": n.is_editable,
            }
            for n in sorted(nodes, key=lambda x: x.node_id)
        ]
        payload = {
            "context": context_label,
            "nodes": serialized_nodes,
        }
        raw_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw_bytes).hexdigest()

    # =========================================================================
    # Invariant Affordance Pattern Extraction & Matching
    # =========================================================================

    def extract_affordance_pattern(
        self,
        graph: CanonicalUIGraph,
        actions: Optional[Sequence[TypedAction]] = None,
    ) -> AffordancePattern:
        """Extracts an invariant affordance pattern from a UI graph and action targets.

        Unlike brittle SHA-256 hashes of the entire DOM, this captures only the
        essential interactable affordances needed for the procedural routine.
        """
        # 1. Resolve application or domain context
        app_or_domain = ""
        if graph.url:
            clean_url = self._normalize_url(graph.url)
            match = re.search(r"https?://([^/:]+)", clean_url)
            app_or_domain = match.group(1).lower() if match else clean_url.lower()
        elif graph.active_window_title:
            win = graph.active_window_title.lower()
            if "notepad" in win:
                app_or_domain = "notepad"
            elif "calculator" in win:
                app_or_domain = "calculator"
            elif "browser" in win or "chrome" in win or "edge" in win:
                app_or_domain = "browser"
            else:
                tokens = re.findall(r"\w+", win)
                app_or_domain = tokens[0] if tokens else "desktop"

        # 2. Extract required affordances
        items: List[AffordanceItem] = []
        if actions:
            seen_targets: Set[Tuple[str, str]] = set()
            for act in actions:
                t_label = self._normalize_label(act.target_label or "")
                t_node = graph.nodes.get(act.target_node_id) if act.target_node_id else None
                if not t_label and t_node and t_node.label:
                    t_label = self._normalize_label(t_node.label)

                role_str = (
                    t_node.role.value if t_node and isinstance(t_node.role, NodeRole)
                    else str(t_node.role) if t_node
                    else "input" if act.action_type == ActionType.TYPE
                    else "button" if act.action_type in (ActionType.CLICK, ActionType.DOUBLE_CLICK)
                    else "element"
                )
                key = (role_str, t_label)
                if key not in seen_targets and (role_str or t_label):
                    seen_targets.add(key)
                    items.append(
                        AffordanceItem(
                            role=role_str,
                            label=t_label,
                            is_clickable=act.action_type in (ActionType.CLICK, ActionType.DOUBLE_CLICK),
                            is_editable=act.action_type == ActionType.TYPE,
                        )
                    )
        else:
            interactable_roles = {
                NodeRole.BUTTON,
                NodeRole.INPUT,
                NodeRole.CHECKBOX,
                NodeRole.RADIO,
                NodeRole.TOGGLE,
                NodeRole.LINK,
                NodeRole.MODAL,
            }
            for n in graph.nodes.values():
                if n.is_clickable or n.is_editable or n.role in interactable_roles:
                    items.append(
                        AffordanceItem(
                            role=n.role.value if isinstance(n.role, NodeRole) else str(n.role),
                            label=self._normalize_label(n.label),
                            is_clickable=n.is_clickable,
                            is_editable=n.is_editable,
                        )
                    )

        sorted_items = tuple(sorted(items, key=lambda x: (x.role, x.label)))
        affordances_str = "|".join(f"[{item.role}:{item.label}]" for item in sorted_items)
        pattern_sig = f"affordance:[app:{app_or_domain}]:{affordances_str}"

        return AffordancePattern(
            app_or_domain=app_or_domain,
            required_affordances=sorted_items,
            pattern_signature=pattern_sig,
        )

    def extract_affordance_pattern_from_skill(self, skill: MotorSkill) -> AffordancePattern:
        """Derives the invariant affordance pattern directly from a compiled MotorSkill routine."""
        items: List[AffordanceItem] = []
        seen: Set[Tuple[str, str]] = set()

        for act in skill.action_sequence:
            label = self._normalize_label(act.target_label or "")
            if not label and act.target_node_id:
                label = self._normalize_label(act.target_node_id)
            if not label:
                label = "input" if act.action_type == ActionType.TYPE else "button"

            role_str = "input" if act.action_type == ActionType.TYPE else "button"
            key = (role_str, label)
            if key not in seen:
                seen.add(key)
                items.append(
                    AffordanceItem(
                        role=role_str,
                        label=label,
                        is_clickable=act.action_type in (ActionType.CLICK, ActionType.DOUBLE_CLICK),
                        is_editable=act.action_type == ActionType.TYPE,
                    )
                )

        sorted_items = tuple(sorted(items, key=lambda x: (x.role, x.label)))
        affordances_str = "|".join(f"[{item.role}:{item.label}]" for item in sorted_items)
        pattern_sig = f"affordance:[app:*]:{affordances_str}"

        return AffordancePattern(
            app_or_domain="*",
            required_affordances=sorted_items,
            pattern_signature=pattern_sig,
        )

    def compute_affordance_pattern_hash(self, pattern: Union[AffordancePattern, str]) -> str:
        """Computes a SHA-256 hash for an affordance pattern signature."""
        sig = pattern.pattern_signature if isinstance(pattern, AffordancePattern) else str(pattern)
        return hashlib.sha256(sig.encode("utf-8")).hexdigest()

    def matches_affordance_pattern(
        self,
        pattern: Union[AffordancePattern, str],
        state: CanonicalUIGraph,
    ) -> bool:
        """Checks if a UI state satisfies the required affordance pattern."""
        if not state or not state.nodes:
            return False

        if isinstance(pattern, str):
            if not pattern.startswith("affordance:"):
                # Fallback to exact hash check
                return pattern in (self.compute_preconditions_hash(state), state.compute_state_hash())
            app_match = re.search(r"affordance:\[app:([^\]]*)\]:(.*)", pattern)
            if not app_match:
                return False
            app_req = app_match.group(1).lower()
            affordances_part = app_match.group(2)
            req_items = []
            for item_match in re.finditer(r"\[([^:]+):([^\]]*)\]", affordances_part):
                req_items.append(AffordanceItem(role=item_match.group(1), label=item_match.group(2)))
            pattern = AffordancePattern(
                app_or_domain=app_req,
                required_affordances=tuple(req_items),
                pattern_signature=pattern,
            )

        # Check app/domain if specified and not wildcard
        if pattern.app_or_domain and pattern.app_or_domain not in ("*", "any", "desktop"):
            state_app = ""
            if state.url:
                state_app = state.url.lower()
            elif state.active_window_title:
                state_app = state.active_window_title.lower()
            if pattern.app_or_domain not in state_app:
                return False

        # Check all required affordances exist in state
        nodes = list(state.nodes.values())
        for req in pattern.required_affordances:
            req_label = self._normalize_label(req.label)
            req_role = req.role.lower()
            matched = False
            for node in nodes:
                node_label = self._normalize_label(node.label)
                node_role = (node.role.value if isinstance(node.role, NodeRole) else str(node.role)).lower()
                node_id = self._normalize_label(node.node_id)

                role_match = (
                    req_role in ("element", "any", "*", "")
                    or req_role == node_role
                    or (req_role == "input" and (node.is_editable or node_role in ("input", "textarea", "edit")))
                    or (req_role == "button" and (node.is_clickable or node_role in ("button", "link")))
                )

                label_match = (
                    not req_label
                    or req_label == node_label
                    or req_label in node_label
                    or node_label in req_label
                    or req_label in node_id
                    or (len(req_label) > 2 and any(w in node_label for w in req_label.split() if len(w) > 2))
                )

                if role_match and label_match:
                    matched = True
                    break

            if not matched:
                return False

        return True

    def reground_action_sequence(
        self,
        actions: Sequence[TypedAction],
        state: CanonicalUIGraph,
        bindings: Optional[Dict[str, Any]] = None,
    ) -> List[TypedAction]:
        """Dynamically re-grounds abstract actions to live UI state nodes and interpolates parameter slots."""
        regrounded: List[TypedAction] = []
        vw, vh = state.viewport_size or (1920, 1080)
        bindings = bindings or {}

        for act in actions:
            target_label = (act.target_label or "").strip()
            matched_node: Optional[UIStateNode] = None

            # Priority 1: Match by exact or normalized label
            if target_label:
                t_clean = self._normalize_label(target_label)
                for node in state.nodes.values():
                    if self._normalize_label(node.label) == t_clean:
                        matched_node = node
                        break
                if not matched_node:
                    for node in state.nodes.values():
                        n_lbl = self._normalize_label(node.label)
                        n_id = self._normalize_label(node.node_id)
                        if t_clean in n_lbl or n_lbl in t_clean or t_clean in n_id:
                            matched_node = node
                            break
                if not matched_node and len(t_clean) > 2:
                    words = [w for w in t_clean.split() if len(w) > 2]
                    for node in state.nodes.values():
                        n_lbl = self._normalize_label(node.label)
                        if any(w in n_lbl for w in words):
                            matched_node = node
                            break

            # Priority 2: Fall back to existing target_node_id if valid
            if not matched_node and act.target_node_id and act.target_node_id in state.nodes:
                matched_node = state.nodes[act.target_node_id]

            # Priority 3: Match by action role heuristic
            if not matched_node:
                if act.action_type == ActionType.TYPE:
                    for node in state.nodes.values():
                        if node.is_editable or node.role == NodeRole.INPUT:
                            matched_node = node
                            break
                elif act.action_type in (ActionType.CLICK, ActionType.DOUBLE_CLICK):
                    for node in state.nodes.values():
                        if node.is_clickable or node.role in (NodeRole.BUTTON, NodeRole.LINK):
                            matched_node = node
                            break

            # Resolve coordinates and node ID
            resolved_node_id = matched_node.node_id if matched_node else act.target_node_id
            resolved_coords = act.coords
            if matched_node:
                cx, cy = matched_node.bounds.center
                resolved_coords = NormalizedCoords(
                    x=round(cx / max(1, vw), 4),
                    y=round(cy / max(1, vh), 4),
                )

            # Interpolate payload template
            payload = act.text_payload
            if payload and bindings:
                for k, v in bindings.items():
                    payload = payload.replace(f"{{{{{k}}}}}", str(v))

            regrounded.append(
                TypedAction(
                    action_type=act.action_type,
                    target_node_id=resolved_node_id,
                    target_label=act.target_label or (matched_node.label if matched_node else None),
                    coords=resolved_coords,
                    text_payload=payload,
                    key_code=act.key_code,
                    scroll_delta=act.scroll_delta,
                    safety_class=act.safety_class,
                    metadata=dict(act.metadata),
                )
            )

        return regrounded

    # =========================================================================
    # Parameterization & Template Extraction
    # =========================================================================

    def parameterize_action(
        self,
        action: TypedAction,
        slot_name: Optional[str] = None,
        custom_mappings: Optional[Dict[str, str]] = None,
    ) -> Tuple[TypedAction, Dict[str, str]]:
        """Parameterizes variable text/input payloads into Jinja/brace template slots {{slot_name}}.
        
        Also strips brittle absolute pixel coordinates in favor of semantic locators.
        """
        extracted_slots: Dict[str, str] = {}
        payload = action.text_payload

        if payload is not None and action.action_type in (ActionType.TYPE, ActionType.KEY_PRESS):
            param_name = slot_name or self._infer_slot_name(action, custom_mappings)
            if param_name:
                # Sanitize slot name
                safe_slot = self._sanitize_slot_name(param_name)
                extracted_slots[safe_slot] = payload
                payload = f"{{{{{safe_slot}}}}}"

        # Strip absolute pixel coordinates (dynamic re-grounding invariant)
        parameterized_action = TypedAction(
            action_type=action.action_type,
            target_node_id=action.target_node_id,
            target_label=action.target_label,
            coords=None,  # NEVER store fixed pixel coordinates in compiled MotorSkill
            text_payload=payload,
            key_code=action.key_code,
            scroll_delta=action.scroll_delta,
            safety_class=action.safety_class,
            metadata=dict(action.metadata),
        )

        return parameterized_action, extracted_slots

    def parameterize_action_sequence(
        self,
        actions: Sequence[TypedAction],
        slot_mappings: Optional[Dict[str, str]] = None,
    ) -> Tuple[List[TypedAction], Dict[str, str]]:
        """Parameterizes a full sequence of actions and returns all extracted parameter slots."""
        all_slots: Dict[str, str] = {}
        parameterized_actions: List[TypedAction] = []

        for idx, act in enumerate(actions):
            explicit_slot = slot_mappings.get(f"step_{idx}") if slot_mappings else None
            param_act, slots = self.parameterize_action(
                act,
                slot_name=explicit_slot,
                custom_mappings=slot_mappings,
            )
            all_slots.update(slots)
            parameterized_actions.append(param_act)

        return parameterized_actions, all_slots

    def _infer_slot_name(
        self,
        action: TypedAction,
        custom_mappings: Optional[Dict[str, str]] = None,
    ) -> str:
        """Infers a meaningful parameter slot name based on target label, node ID, or payload format."""
        target_label = (action.target_label or "").lower()
        target_id = (action.target_node_id or "").lower()
        payload = action.text_payload or ""

        if custom_mappings:
            for k, v in custom_mappings.items():
                if k.lower() in target_label or k.lower() in target_id:
                    return v

        # Check explicit target semantic heuristics
        if any(w in target_label for w in ("search", "query", "find", "searchbox")):
            return "query"
        if any(w in target_label for w in ("username", "user_name", "login", "userid", "user_id")):
            return "username"
        if any(w in target_label for w in ("password", "passwd", "pass")):
            return "password"
        if any(w in target_label for w in ("email", "e-mail", "mail")):
            return "user_email"

        # Check payload format heuristics
        if self.EMAIL_REGEX.match(payload):
            return "user_email"
        if self.URL_REGEX.match(payload):
            return "target_url"
        if self.DATE_REGEX.match(payload):
            return "date_value"
        if self.PHONE_REGEX.match(payload):
            return "phone_number"

        # Check general field heuristics
        if "first name" in target_label or "firstname" in target_label:
            return "first_name"
        if "last name" in target_label or "lastname" in target_label:
            return "last_name"
        if any(w in target_label for w in ("zip", "postal", "zipcode", "postcode")):
            return "zip_code"
        if "city" in target_label:
            return "city"
        if any(w in target_label for w in ("address", "street", "addr")):
            return "street_address"
        if "phone" in target_label or "mobile" in target_label:
            return "phone_number"
        if "amount" in target_label or "quantity" in target_label or "qty" in target_label:
            return "amount"

        # Fallback based on target label or generic slot
        if action.target_label:
            clean_label = re.sub(r"[^\w]+", "_", action.target_label.strip().lower()).strip("_")
            if clean_label:
                return f"{clean_label}_input"

        return "input_value"

    def _sanitize_slot_name(self, slot_name: str) -> str:
        """Sanitizes parameter names to valid identifiers [a-zA-Z0-9_] preventing injection."""
        clean = re.sub(r"[^\w]+", "_", slot_name.strip()).strip("_")
        if not clean or not clean[0].isalpha() and clean[0] != "_":
            clean = f"param_{clean}"
        return clean

    @staticmethod
    def _normalize_label(label: str) -> str:
        return re.sub(r"\s+", " ", label.strip().lower())

    @staticmethod
    def _normalize_url(url: Optional[str]) -> str:
        if not url:
            return ""
        # Strip query parameters and hash fragments for robust precondition matching
        clean = url.split("?")[0].split("#")[0]
        return clean.rstrip("/")

    # =========================================================================
    # Extraction from Trajectories & Episodes
    # =========================================================================

    def extract_from_single_episode(
        self,
        transitions: Sequence[TransitionTuple],
        goal_text: Optional[str] = None,
        initial_state: Optional[CanonicalUIGraph] = None,
        slot_mappings: Optional[Dict[str, str]] = None,
        skill_id: Optional[str] = None,
    ) -> MotorSkill:
        """Compiles a candidate MotorSkill from a single verified TransitionTuple sequence."""
        if not transitions:
            raise ValueError("Cannot extract skill from empty transition sequence")

        first_tx = transitions[0]
        goal = goal_text or first_tx.goal_text
        goal_emb = list(first_tx.goal_embedding) if first_tx.goal_embedding else [0.0] * 384
        vis_emb = list(first_tx.visual_embedding) if first_tx.visual_embedding is not None else [0.0] * 384

        # Compute preconditions hash
        if initial_state is not None:
            preconditions_hash = self.compute_preconditions_hash(initial_state)
        else:
            preconditions_hash = first_tx.ui_state_hash

        # Parameterize action sequence
        raw_actions = [tx.action for tx in transitions]
        parameterized_actions, _ = self.parameterize_action_sequence(raw_actions, slot_mappings)

        # Merge state deltas and calculate timing
        total_duration = sum(tx.duration_ms for tx in transitions)
        durations = [tx.duration_ms for tx in transitions]
        mean_duration = total_duration / len(transitions) if transitions else 0.0
        var_duration = (
            sum((d - mean_duration) ** 2 for d in durations) / len(durations)
            if len(durations) > 1
            else 0.0
        )
        std_duration = math.sqrt(var_duration)

        merged_delta = self._merge_deltas([tx.delta for tx in transitions])
        highest_safety = self._aggregate_safety_class(raw_actions)

        sk_id = skill_id or f"skill_{preconditions_hash[:8]}_{uuid.uuid4().hex[:8]}"

        return MotorSkill(
            skill_id=sk_id,
            version=1,
            preconditions_hash=preconditions_hash,
            goal_embedding=goal_emb,
            visual_context_embedding=vis_emb,
            action_sequence=parameterized_actions,
            expected_delta=merged_delta,
            timing_mean_ms=mean_duration,
            timing_std_ms=std_duration,
            confidence=0.8,
            safety_class=highest_safety,
            provenance_episode_ids=[first_tx.episode_id],
            validated_count=1,
        )

    def extract_from_episodes(
        self,
        episode_traces: Sequence[Sequence[TransitionTuple]],
        goal_text: Optional[str] = None,
        state_graphs: Optional[Dict[str, CanonicalUIGraph]] = None,
        slot_mappings: Optional[Dict[str, str]] = None,
        min_occurrences: int = 1,
    ) -> List[MotorSkill]:
        """Identifies recurring procedural sub-trajectories across multiple episodes and compiles them."""
        if not episode_traces:
            return []

        # Filter to non-empty traces
        valid_traces = [t for t in episode_traces if len(t) >= 1]
        if not valid_traces or len(valid_traces) < min_occurrences:
            return []

        # Group traces by action sequence signature (action types and targets)
        groups: Dict[str, List[Sequence[TransitionTuple]]] = {}
        for trace in valid_traces:
            sig = self._compute_trace_signature(trace)
            groups.setdefault(sig, []).append(trace)

        skills: List[MotorSkill] = []

        for sig, matching_traces in groups.items():
            if len(matching_traces) < min_occurrences:
                continue

            first_trace = matching_traces[0]
            first_tx = first_trace[0]
            g_text = goal_text or first_tx.goal_text

            # Parameterize actions across all matching traces to detect variable slots
            parameterized_actions, _ = self._parameterize_across_traces(matching_traces, slot_mappings)

            # Precondition hash
            first_ep_id = first_tx.episode_id
            init_graph = state_graphs.get(first_ep_id) if state_graphs else None
            if init_graph:
                preconditions_hash = self.compute_preconditions_hash(init_graph)
            else:
                preconditions_hash = first_tx.ui_state_hash

            # Aggregate timing statistics
            trace_durations = [sum(tx.duration_ms for tx in trace) for trace in matching_traces]
            mean_timing = sum(trace_durations) / len(trace_durations)
            var_timing = (
                sum((d - mean_timing) ** 2 for d in trace_durations) / len(trace_durations)
                if len(trace_durations) > 1
                else 0.0
            )
            std_timing = math.sqrt(var_timing)

            # Average goal embedding
            goal_embeddings = [t[0].goal_embedding for t in matching_traces if t[0].goal_embedding]
            if goal_embeddings:
                dim = len(goal_embeddings[0])
                avg_goal = [
                    sum(emb[d] for emb in goal_embeddings) / len(goal_embeddings)
                    for d in range(dim)
                ]
            else:
                avg_goal = [0.0] * 384

            # Average visual embedding
            vis_embeddings = [
                t[0].visual_embedding for t in matching_traces if t[0].visual_embedding is not None
            ]
            if vis_embeddings:
                dim = len(vis_embeddings[0])
                avg_vis = [
                    sum(emb[d] for emb in vis_embeddings) / len(vis_embeddings)
                    for d in range(dim)
                ]
            else:
                avg_vis = [0.0] * 384

            # Merged deltas and safety class
            all_actions = [tx.action for tx in first_trace]
            highest_safety = self._aggregate_safety_class(all_actions)
            merged_delta = self._merge_deltas([tx.delta for tx in first_trace])
            ep_ids = list(dict.fromkeys(t[0].episode_id for t in matching_traces))

            sk_id = f"skill_{preconditions_hash[:8]}_{uuid.uuid4().hex[:8]}"

            skill = MotorSkill(
                skill_id=sk_id,
                version=1,
                preconditions_hash=preconditions_hash,
                goal_embedding=avg_goal,
                visual_context_embedding=avg_vis,
                action_sequence=parameterized_actions,
                expected_delta=merged_delta,
                timing_mean_ms=mean_timing,
                timing_std_ms=std_timing,
                confidence=min(0.95, 0.70 + 0.05 * len(matching_traces)),
                safety_class=highest_safety,
                provenance_episode_ids=ep_ids,
                validated_count=len(matching_traces),
            )
            skills.append(skill)

        return skills

    async def extract_from_journal(
        self,
        journal: EpisodeJournalPort,
        min_occurrences: int = 1,
        success_only: bool = True,
    ) -> List[MotorSkill]:
        """Queries verified episodes from a LocalEpisodeJournal and extracts candidate motor skills."""
        episodes = await journal.list_episodes()
        if success_only:
            episodes = [ep for ep in episodes if ep.success]

        traces: List[List[TransitionTuple]] = []
        for ep in episodes:
            txs = await journal.get_episode_transitions(ep.episode_id)
            if txs:
                traces.append(txs)

        return self.extract_from_episodes(traces, min_occurrences=min_occurrences)

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    def _compute_trace_signature(self, trace: Sequence[TransitionTuple]) -> str:
        """Computes a structural action signature to identify identical execution paths."""
        parts = []
        for tx in trace:
            act = tx.action
            target_key = (
                act.target_label
                or act.target_node_id
                or (f"key_{act.key_code}" if act.key_code else "")
                or "none"
            )
            parts.append(f"{act.action_type.value}:{target_key}")
        return "->".join(parts)

    def _parameterize_across_traces(
        self,
        traces: Sequence[Sequence[TransitionTuple]],
        custom_mappings: Optional[Dict[str, str]] = None,
    ) -> Tuple[List[TypedAction], Dict[str, List[str]]]:
        """Compares values across multiple traces to automatically parameterize differing payloads."""
        base_trace = traces[0]
        step_count = len(base_trace)
        parameterized_actions: List[TypedAction] = []
        slot_values: Dict[str, List[str]] = {}

        for step_idx in range(step_count):
            base_act = base_trace[step_idx].action
            payloads = [
                trace[step_idx].action.text_payload
                for trace in traces
                if step_idx < len(trace) and trace[step_idx].action.text_payload is not None
            ]

            # Check if payloads vary across runs
            distinct_payloads = set(payloads)
            if len(distinct_payloads) > 1 or base_act.action_type == ActionType.TYPE:
                # Differing text payload detected -> Parameterize into template
                inferred_name = self._infer_slot_name(base_act, custom_mappings)
                slot_name = self._sanitize_slot_name(inferred_name)
                slot_values[slot_name] = payloads

                new_act = TypedAction(
                    action_type=base_act.action_type,
                    target_node_id=base_act.target_node_id,
                    target_label=base_act.target_label,
                    coords=None,  # dynamic re-grounding invariant
                    text_payload=f"{{{{{slot_name}}}}}",
                    key_code=base_act.key_code,
                    scroll_delta=base_act.scroll_delta,
                    safety_class=base_act.safety_class,
                    metadata=dict(base_act.metadata),
                )
            else:
                # Fixed invariant action (e.g. static click or enter)
                new_act = TypedAction(
                    action_type=base_act.action_type,
                    target_node_id=base_act.target_node_id,
                    target_label=base_act.target_label,
                    coords=None,
                    text_payload=base_act.text_payload,
                    key_code=base_act.key_code,
                    scroll_delta=base_act.scroll_delta,
                    safety_class=base_act.safety_class,
                    metadata=dict(base_act.metadata),
                )
            parameterized_actions.append(new_act)

        return parameterized_actions, slot_values

    def _merge_deltas(self, deltas: Sequence[StateDelta]) -> StateDelta:
        """Combines multiple step StateDeltas into a consolidated expected delta."""
        if not deltas:
            return StateDelta()

        added: Set[str] = set()
        removed: Set[str] = set()
        modified: Set[str] = set()
        boxes: List[Tuple[int, int, int, int]] = []
        max_pixel_ratio = 0.0
        final_outcome = deltas[-1].outcome_class if deltas else OutcomeClass.SUCCESS

        for d in deltas:
            added.update(d.added_nodes)
            removed.update(d.removed_nodes)
            modified.update(d.modified_nodes)
            boxes.extend(d.changed_bounding_boxes)
            max_pixel_ratio = max(max_pixel_ratio, d.pixel_change_ratio)

        return StateDelta(
            added_nodes=list(added),
            removed_nodes=list(removed),
            modified_nodes=list(modified),
            pixel_change_ratio=round(max_pixel_ratio, 4),
            changed_bounding_boxes=boxes[:10],
            outcome_class=final_outcome,
        )

    def _aggregate_safety_class(self, actions: Sequence[TypedAction]) -> SafetyClass:
        """Determines the highest safety risk across all steps in the routine."""
        if any(a.safety_class == SafetyClass.DESTRUCTIVE for a in actions):
            return SafetyClass.DESTRUCTIVE
        if any(a.safety_class == SafetyClass.AMBIGUOUS for a in actions):
            return SafetyClass.AMBIGUOUS
        return SafetyClass.REVERSIBLE
