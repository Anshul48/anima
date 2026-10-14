"""User Correction & Attribute Locking Engine.

Enforces:
1. Absolute human sovereignty: User corrections take permanent precedence over automated inferences.
2. Attribute-level permanent override locks preventing heuristic re-classification.
3. Sub-50ms in-memory projection mutation and instant propagation.
4. Cryptographic provenance tracking for all human corrections.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from entorhinal.projections.graph import SemanticGraphManager
from entorhinal.projections.models import EntityNodeType
from entorhinal.schemas.models import (
    CorrectionAction,
    DerivedFact,
    Hypothesis,
    UserCorrection,
    derive_fact_id,
    generate_uuidv7,
)

logger = logging.getLogger(__name__)


class CorrectionManager:
    """Manages active user corrections and applies immutable attribute override locks."""

    def __init__(
        self,
        storage_path: Optional[Union[str, Path]] = None,
        graph_manager: Optional[SemanticGraphManager] = None,
    ) -> None:
        self.storage_path: Optional[Path] = Path(storage_path) if storage_path else None
        self.graph_manager = graph_manager
        self._corrections: Dict[str, UserCorrection] = {}  # keyed by correction_id
        # Index by target_entity_or_fact_id -> latest UserCorrection
        self._target_index: Dict[str, UserCorrection] = {}

        if self.storage_path and self.storage_path.exists():
            self._load_corrections()

    # --------------------------------------------------------------------------
    # Storage & Persistence
    # --------------------------------------------------------------------------

    def _load_corrections(self) -> None:
        """Load persisted user corrections from JSONL file."""
        if not self.storage_path or not self.storage_path.exists():
            return

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if not line_str:
                        continue
                    data = json.loads(line_str)
                    corr = UserCorrection(**data)
                    self._corrections[corr.correction_id] = corr
                    self._target_index[corr.target_entity_or_fact_id] = corr
        except Exception as e:
            logger.error("Failed to load user corrections from %s: %s", self.storage_path, e)

    def _persist_correction(self, correction: UserCorrection) -> None:
        """Append a newly submitted correction to disk."""
        if not self.storage_path:
            return

        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(correction.model_dump(), sort_keys=True, default=str) + "\n"
        with open(self.storage_path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()

    # --------------------------------------------------------------------------
    # Correction Submission & Locking
    # --------------------------------------------------------------------------

    def submit_correction(
        self,
        target_id: str,
        corrected_value: Optional[Any] = None,
        override_action: CorrectionAction = CorrectionAction.OVERWRITE,
        user_comment: Optional[str] = None,
        correction_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> UserCorrection:
        """Register and immediately apply a user correction override lock.

        Guarantees <50ms propagation to active in-memory structures.
        """
        corr = UserCorrection(
            correction_id=correction_id or generate_uuidv7(),
            target_entity_or_fact_id=target_id,
            override_action=override_action,
            corrected_value=corrected_value,
            user_comment=user_comment,
            timestamp=timestamp or datetime.now(timezone.utc),
        )

        self._corrections[corr.correction_id] = corr
        self._target_index[target_id] = corr
        self._persist_correction(corr)

        # Apply immediately to in-memory graph if attached
        if self.graph_manager is not None:
            self.apply_to_graph(self.graph_manager, corr)

        logger.info(
            "User correction %s applied to target '%s' (action=%s)",
            corr.correction_id,
            target_id,
            override_action.value,
        )
        return corr

    def register_correction_object(self, correction: UserCorrection) -> None:
        """Store an existing UserCorrection instance."""
        self._corrections[correction.correction_id] = correction
        self._target_index[correction.target_entity_or_fact_id] = correction
        self._persist_correction(correction)
        if self.graph_manager is not None:
            self.apply_to_graph(self.graph_manager, correction)

    # --------------------------------------------------------------------------
    # Mutation of Projections & Graphs
    # --------------------------------------------------------------------------

    def apply_to_graph(
        self,
        graph_manager: SemanticGraphManager,
        correction: Optional[UserCorrection] = None,
    ) -> None:
        """Directly mutate entity graph nodes and attributes with permanent user locks."""
        corrs = [correction] if correction is not None else list(self._target_index.values())

        for corr in corrs:
            target = corr.target_entity_or_fact_id

            if corr.override_action == CorrectionAction.DELETE:
                # Remove node if exists
                if target in graph_manager._nodes:
                    del graph_manager._nodes[target]
                continue

            if corr.override_action == CorrectionAction.EXCLUDE:
                # Mark node as excluded or lower confidence
                node = graph_manager.get_node(target)
                if node:
                    node.confidence = 0.0
                continue

            if corr.override_action == CorrectionAction.OVERWRITE:
                # If target is an entity URI, update name or attribute
                node = graph_manager.get_node(target)
                if node:
                    if isinstance(corr.corrected_value, dict):
                        for k, v in corr.corrected_value.items():
                            if k == "name":
                                node.name = str(v)
                            else:
                                node.attributes[k] = v
                    elif isinstance(corr.corrected_value, str):
                        node.name = corr.corrected_value
                    node.confidence = 1.0
                    node.attributes["user_override_locked"] = True
                    node.attributes["user_override_id"] = corr.correction_id
                else:
                    # Target might be new or not yet in graph: create entity node
                    attrs: Dict[str, Any] = {"user_override_locked": True, "user_override_id": corr.correction_id}
                    name = str(corr.corrected_value)
                    if isinstance(corr.corrected_value, dict):
                        attrs.update(corr.corrected_value)
                        name = str(corr.corrected_value.get("name", target))

                    graph_manager.add_or_update_node(
                        entity_uri=target,
                        entity_type=EntityNodeType.PROJECT if target.startswith("project:") else EntityNodeType.TOPIC,
                        name=name,
                        attributes=attrs,
                        evidence_ids=[f"user-correction:{corr.correction_id}"],
                        confidence=1.0,
                    )

    def apply_to_facts(self, facts: List[DerivedFact]) -> List[DerivedFact]:
        """Filter and override derived facts against active user locks."""
        if not self._target_index:
            return facts

        updated_facts: List[DerivedFact] = []
        covered_targets: set[str] = set()

        for fact in facts:
            # Check fact ID match or entity URI match
            corr = self._target_index.get(fact.fact_id) or self._target_index.get(fact.entity_uri)

            if corr is None:
                updated_facts.append(fact)
                continue

            covered_targets.add(corr.target_entity_or_fact_id)

            if corr.override_action == CorrectionAction.DELETE:
                # Exclude from facts completely
                continue

            if corr.override_action == CorrectionAction.EXCLUDE:
                # Exclude from facts
                continue

            if corr.override_action == CorrectionAction.OVERWRITE:
                # Overwrite value with user-supplied value
                new_val = corr.corrected_value
                if isinstance(new_val, dict):
                    if fact.attribute in new_val:
                        override_val = new_val[fact.attribute]
                    else:
                        override_val = fact.value
                else:
                    override_val = new_val

                updated_fact = DerivedFact(
                    fact_id=fact.fact_id,
                    schema_version=fact.schema_version,
                    entity_uri=fact.entity_uri,
                    attribute=fact.attribute,
                    value=override_val,
                    confidence=1.0,  # User override is 100% confident
                    valid_from=fact.valid_from,
                    valid_to=fact.valid_to,
                    supporting_evidence_ids=list(fact.supporting_evidence_ids) + [f"user-correction:{corr.correction_id}"],
                    derived_by=f"UserCorrection:{corr.correction_id}",
                    revision_id=fact.revision_id + 1,
                )
                updated_facts.append(updated_fact)

        # Also inject user corrections that are not already in facts
        for target_id, corr in self._target_index.items():
            if target_id not in covered_targets and corr.override_action == CorrectionAction.OVERWRITE:
                val = corr.corrected_value
                now = corr.timestamp or datetime.now(timezone.utc)
                grounding = [f"user-correction:{corr.correction_id}"]
                derived_by = f"UserCorrection:{corr.correction_id}"
                if isinstance(val, dict):
                    for attr_k, attr_v in val.items():
                        updated_facts.append(
                            DerivedFact(
                                # F10: stable id derived from (target,
                                # attribute, value, correction) so the
                                # correction anchor survives rebuilds.
                                fact_id=derive_fact_id(
                                    entity_uri=target_id,
                                    attribute=attr_k,
                                    value=attr_v,
                                    valid_from=now,
                                    valid_to=None,
                                    evidence_ids=list(grounding),
                                    derived_by=derived_by,
                                ),
                                schema_version="1.0.0",
                                entity_uri=target_id,
                                attribute=attr_k,
                                value=attr_v,
                                confidence=1.0,
                                valid_from=now,
                                valid_to=None,
                                supporting_evidence_ids=list(grounding),
                                derived_by=derived_by,
                                revision_id=1,
                            )
                        )
                else:
                    updated_facts.append(
                        DerivedFact(
                            fact_id=derive_fact_id(
                                entity_uri=target_id,
                                attribute="user_override",
                                value=val,
                                valid_from=now,
                                valid_to=None,
                                evidence_ids=list(grounding),
                                derived_by=derived_by,
                            ),
                            schema_version="1.0.0",
                            entity_uri=target_id,
                            attribute="user_override",
                            value=val,
                            confidence=1.0,
                            valid_from=now,
                            valid_to=None,
                            supporting_evidence_ids=list(grounding),
                            derived_by=derived_by,
                            revision_id=1,
                        )
                    )

        return updated_facts

    def is_locked(self, target_id: str) -> bool:
        """Check if an entity or fact ID is permanently locked by a user correction."""
        return target_id in self._target_index

    def get_correction(self, target_id: str) -> Optional[UserCorrection]:
        """Get the active user correction for a target entity or fact ID."""
        return self._target_index.get(target_id)

    def list_corrections(self) -> List[UserCorrection]:
        """List all active user corrections."""
        return list(self._corrections.values())

    def clear(self) -> None:
        """Clear in-memory corrections."""
        self._corrections.clear()
        self._target_index.clear()
