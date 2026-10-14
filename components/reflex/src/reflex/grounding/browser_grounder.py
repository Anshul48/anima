"""Reflex Browser Grounding Engine: Semantic target resolution against Canonical UI Graphs."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode


@dataclass(frozen=True)
class GroundingQuery:
    """Target resolution request from Planner or Skill."""

    target_text: str
    target_role: Optional[str] = None
    container_hint: Optional[str] = None
    min_confidence: float = 0.80


@dataclass(frozen=True)
class GroundingResult:
    """Resolved concrete UI target."""

    target_node: UIStateNode
    confidence: float
    click_coords: Tuple[int, int]
    is_ambiguous: bool = False
    candidate_count: int = 1
    provenance: str = "cdp_dom_ax"


class BrowserGroundingPort(ABC):
    """Abstract port for resolving semantic target queries against Canonical UI Graphs."""

    @abstractmethod
    def resolve_target(
        self, graph: CanonicalUIGraph, query: GroundingQuery
    ) -> Optional[GroundingResult]:
        """Resolves target against the current UI state graph."""
        ...


class BrowserGroundingEngine(BrowserGroundingPort):
    """Semantic grounding engine mapping intent descriptions to interactable UI nodes."""

    def __init__(
        self,
        text_weight: float = 0.55,
        role_weight: float = 0.25,
        visibility_weight: float = 0.20,
    ) -> None:
        self.text_weight = text_weight
        self.role_weight = role_weight
        self.visibility_weight = visibility_weight

    @staticmethod
    def _normalize_text(text: Optional[str]) -> str:
        if not text:
            return ""
        return re.sub(r"\s+", " ", str(text).strip().lower())

    @staticmethod
    def _levenshtein_distance(s1: str, s2: str) -> int:
        if len(s1) < len(s2):
            return BrowserGroundingEngine._levenshtein_distance(s2, s1)
        if len(s2) == 0:
            return len(s1)
        previous_row = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        return previous_row[-1]

    def _compute_text_similarity(self, query_text: str, candidate_text: str) -> float:
        """Computes text similarity in [0.0, 1.0] using exact, prefix, substring, and fuzzy matching."""
        q = self._normalize_text(query_text)
        c = self._normalize_text(candidate_text)

        if not q or not c:
            return 0.0

        # Exact match
        if q == c:
            return 1.0

        # Whole word match or word boundary
        q_tokens = set(re.findall(r"\w+", q))
        c_tokens = set(re.findall(r"\w+", c))

        if q_tokens and q_tokens.issubset(c_tokens):
            token_ratio = len(q_tokens) / max(len(c_tokens), 1)
            return round(0.85 + 0.12 * token_ratio, 4)

        if q in c or c in q:
            len_ratio = min(len(q), len(c)) / max(len(q), len(c))
            return round(0.80 + 0.15 * len_ratio, 4)

        # Jaccard token overlap
        if q_tokens and c_tokens:
            overlap = len(q_tokens & c_tokens)
            union = len(q_tokens | c_tokens)
            if overlap > 0:
                jaccard = overlap / union
                return round(0.60 + 0.30 * jaccard, 4)

        # Fuzzy edit distance
        dist = self._levenshtein_distance(q, c)
        max_len = max(len(q), len(c))
        if max_len > 0:
            sim = 1.0 - (dist / max_len)
            if sim >= 0.70:
                return round(0.50 + 0.40 * sim, 4)

        return 0.0

    def _score_node_text(self, query_text: str, node: UIStateNode) -> float:
        """Scores all possible text representations of a node against query text."""
        scores: List[float] = []

        # 1. Primary label
        if node.label:
            scores.append(self._compute_text_similarity(query_text, node.label) * 1.0)

        # 2. Value
        if node.value:
            scores.append(self._compute_text_similarity(query_text, node.value) * 0.95)

        # 3. Attributes (placeholder, title, aria-label, name, id, data-testid)
        attrs = node.attributes
        if "placeholder" in attrs:
            scores.append(self._compute_text_similarity(query_text, str(attrs["placeholder"])) * 0.95)
        if "aria-label" in attrs:
            scores.append(self._compute_text_similarity(query_text, str(attrs["aria-label"])) * 0.95)
        if "title" in attrs:
            scores.append(self._compute_text_similarity(query_text, str(attrs["title"])) * 0.90)
        if "name" in attrs:
            scores.append(self._compute_text_similarity(query_text, str(attrs["name"])) * 0.85)
        if "data-testid" in attrs:
            scores.append(self._compute_text_similarity(query_text, str(attrs["data-testid"])) * 0.90)
        if "id" in attrs:
            scores.append(self._compute_text_similarity(query_text, str(attrs["id"])) * 0.80)
        if node.node_id:
            scores.append(self._compute_text_similarity(query_text, node.node_id) * 0.75)

        return max(scores) if scores else 0.0

    def _score_node_role(self, query_role: Optional[str], node: UIStateNode) -> float:
        """Scores role compatibility between query and node."""
        node_role_str = node.role.value.lower() if isinstance(node.role, NodeRole) else str(node.role).lower()

        if not query_role:
            # Prefer interactive elements when no role specified
            if node_role_str in ("button", "input", "checkbox", "radio", "toggle", "link"):
                return 1.0
            elif node_role_str in ("text", "image", "modal"):
                return 0.7
            else:
                return 0.5

        q_role = query_role.lower().strip()
        if q_role == node_role_str:
            return 1.0

        # Synonyms & compatibility
        synonyms: Dict[str, Set[str]] = {
            "button": {"link", "toggle", "checkbox"},
            "input": {"textbox", "searchbox", "textarea", "combobox"},
            "checkbox": {"toggle", "switch"},
            "toggle": {"checkbox", "switch", "button"},
            "link": {"button", "tab"},
            "text": {"label", "heading", "statictext"},
            "modal": {"dialog", "alertdialog", "container"},
            "container": {"modal", "form", "table", "section", "region"},
        }

        if q_role in synonyms and node_role_str in synonyms[q_role]:
            return 0.8
        if node_role_str in synonyms and q_role in synonyms[node_role_str]:
            return 0.8

        return 0.1

    def _score_visibility(self, node: UIStateNode) -> float:
        """Evaluates node visibility, clickable state, and occlusion status."""
        if node.bounds.width <= 0 or node.bounds.height <= 0:
            return 0.0

        score = 1.0

        # Occlusion / Clickable check
        is_topmost = node.attributes.get("is_topmost", node.is_clickable)
        if not is_topmost:
            score *= 0.2
        elif not node.is_clickable:
            score *= 0.6

        # Disabled status check
        if not node.is_enabled:
            score *= 0.3

        return score

    def _find_matching_containers(
        self, graph: CanonicalUIGraph, container_hint: str
    ) -> List[UIStateNode]:
        """Finds container/ancestor nodes matching container_hint, prioritizing most specific containers."""
        hint = self._normalize_text(container_hint)
        direct_matches: List[UIStateNode] = []
        subtree_matches: List[UIStateNode] = []

        for node in graph.nodes.values():
            node_label = self._normalize_text(node.label)
            node_id = self._normalize_text(node.node_id)
            node_class = self._normalize_text(str(node.attributes.get("class", "")))
            node_role = node.role.value.lower() if isinstance(node.role, NodeRole) else str(node.role).lower()

            # 1. Direct label, id, class, role, or attribute match
            if hint in node_label or hint in node_id or hint in node_class or hint in node_role:
                direct_matches.append(node)
                continue

            for attr_val in node.attributes.values():
                if hint in self._normalize_text(str(attr_val)):
                    direct_matches.append(node)
                    break
            else:
                # 2. Subtree text match for container/modal nodes
                if (node_role in ("container", "modal", "table") or node.children_ids) and self._subtree_contains_text(graph, node, hint):
                    subtree_matches.append(node)

        # Prioritize direct matches if available
        candidates = direct_matches if direct_matches else subtree_matches

        # Prune broader ancestor containers when more specific descendant containers match
        return self._prune_ancestor_containers(candidates, graph)

    def _prune_ancestor_containers(
        self, containers: List[UIStateNode], graph: CanonicalUIGraph
    ) -> List[UIStateNode]:
        """Prunes broader ancestor containers when more specific descendant containers are present."""
        if len(containers) <= 1:
            return containers

        pruned: List[UIStateNode] = []
        for c in containers:
            has_descendant_match = False
            for other in containers:
                if other.node_id != c.node_id:
                    curr = other.parent_id
                    visited: Set[str] = set()
                    while curr and curr in graph.nodes and curr not in visited:
                        if curr == c.node_id:
                            has_descendant_match = True
                            break
                        visited.add(curr)
                        curr = graph.nodes[curr].parent_id
                    if has_descendant_match:
                        break
            if not has_descendant_match:
                pruned.append(c)

        return pruned if pruned else containers

    def _subtree_contains_text(
        self, graph: CanonicalUIGraph, root: UIStateNode, text: str
    ) -> bool:
        """Checks if a node or any of its descendants contain the specified text."""
        if text in self._normalize_text(root.label) or text in self._normalize_text(root.value):
            return True
        for child_id in root.children_ids:
            if child_id in graph.nodes:
                child = graph.nodes[child_id]
                if self._subtree_contains_text(graph, child, text):
                    return True
        return False

    def _is_in_container(
        self, graph: CanonicalUIGraph, node: UIStateNode, container: UIStateNode
    ) -> bool:
        """Checks if node is a descendant or spatially enclosed by container."""
        # 1. Structural hierarchy check (parent_id traversal)
        curr_id = node.parent_id
        visited: Set[str] = set()
        while curr_id and curr_id in graph.nodes and curr_id not in visited:
            if curr_id == container.node_id:
                return True
            visited.add(curr_id)
            curr_id = graph.nodes[curr_id].parent_id

        # 2. Spatial bounding box containment check
        c_bounds = container.bounds
        n_bounds = node.bounds
        if (
            c_bounds.width > 0
            and c_bounds.height > 0
            and c_bounds.x1 <= n_bounds.x1
            and c_bounds.y1 <= n_bounds.y1
            and n_bounds.x2 <= c_bounds.x2
            and n_bounds.y2 <= c_bounds.y2
        ):
            return True

        return False

    def find_candidates(
        self, graph: CanonicalUIGraph, query: GroundingQuery
    ) -> List[Tuple[UIStateNode, float]]:
        """Scores and ranks all candidate nodes in graph against query."""
        candidates: List[Tuple[UIStateNode, float]] = []

        # Resolve container context if specified
        allowed_containers: Optional[List[UIStateNode]] = None
        if query.container_hint:
            allowed_containers = self._find_matching_containers(graph, query.container_hint)
            if not allowed_containers:
                # If container hint not found at all, return empty candidates
                return []

        w_text = self.text_weight if query.target_role else (self.text_weight + self.role_weight * 0.6)
        w_role = self.role_weight if query.target_role else (self.role_weight * 0.4)
        w_vis = self.visibility_weight

        for node in graph.nodes.values():
            # Exclude zero-dimension nodes
            if node.bounds.width <= 0 or node.bounds.height <= 0:
                continue

            # Container filter
            if allowed_containers is not None:
                in_container = any(
                    self._is_in_container(graph, node, c) for c in allowed_containers
                )
                if not in_container:
                    continue

            text_score = self._score_node_text(query.target_text, node)
            if text_score <= 0.0:
                continue

            role_score = self._score_node_role(query.target_role, node)
            vis_score = self._score_visibility(node)

            total_score = (w_text * text_score) + (w_role * role_score) + (w_vis * vis_score)
            total_score = min(1.0, max(0.0, total_score))

            if total_score > 0.0:
                candidates.append((node, round(total_score, 4)))

        # Sort candidates descending by score
        candidates.sort(key=lambda item: item[1], reverse=True)
        return candidates

    def resolve_target(
        self, graph: CanonicalUIGraph, query: GroundingQuery
    ) -> Optional[GroundingResult]:
        """Resolves target against the current UI state graph."""
        candidates = self.find_candidates(graph, query)
        if not candidates:
            return None

        top_node, top_score = candidates[0]

        if top_score < query.min_confidence:
            return None

        # Check for ambiguity among top candidates
        matching_top = [
            c for c in candidates
            if c[1] >= query.min_confidence and (top_score - c[1]) < 0.05
        ]

        is_ambiguous = len(matching_top) > 1
        candidate_count = len(matching_top)

        # Compute click coordinates (center of bounding box)
        click_x, click_y = top_node.bounds.center

        # Clamp click coordinates within viewport
        vp_w, vp_h = graph.viewport_size
        click_x = max(0, min(vp_w, click_x))
        click_y = max(0, min(vp_h, click_y))

        return GroundingResult(
            target_node=top_node,
            confidence=top_score,
            click_coords=(click_x, click_y),
            is_ambiguous=is_ambiguous,
            candidate_count=candidate_count,
            provenance="cdp_dom_ax",
        )

    def validate_target(
        self,
        graph: CanonicalUIGraph,
        target_node_id: str,
        expected_bounds: Optional[BoundingBox] = None,
        tolerance_px: int = 5,
    ) -> bool:
        """Validates that a previously resolved target node is still present, stable, and interactable."""
        if target_node_id not in graph.nodes:
            return False

        node = graph.nodes[target_node_id]

        if not node.is_enabled:
            return False

        if node.bounds.width <= 0 or node.bounds.height <= 0:
            return False

        if expected_bounds is not None:
            dx1 = abs(node.bounds.x1 - expected_bounds.x1)
            dy1 = abs(node.bounds.y1 - expected_bounds.y1)
            dx2 = abs(node.bounds.x2 - expected_bounds.x2)
            dy2 = abs(node.bounds.y2 - expected_bounds.y2)
            if max(dx1, dy1, dx2, dy2) > tolerance_px:
                return False

        return True
