from __future__ import annotations
from typing import Any, Dict, Optional

from reflex.execution.browser.cdp_action_adapter import BrowserActionPort, CDPActionAdapter
from reflex.execution.input.synthetic_input_adapter import SyntheticInputAdapter
from reflex.host.identity.lease_manager import ActionLease, ActionLeaseManager
from reflex.ports.action import ActionReceipt
from reflex.schemas.actions import ActionType, TypedAction
from reflex.schemas.identity import ActionIdentity


class ExecutionRouter(BrowserActionPort):
    """Routes typed action execution to either direct DOM or synthetic physical input adapter based on modality."""

    def __init__(
        self,
        cdp_adapter: Optional[CDPActionAdapter] = None,
        synthetic_adapter: Optional[SyntheticInputAdapter] = None,
        lease_manager: Optional[ActionLeaseManager] = None,
        page: Any = None,
    ):
        self.cdp_adapter = cdp_adapter or CDPActionAdapter(page=page, lease_manager=lease_manager)
        self.synthetic_adapter = synthetic_adapter or SyntheticInputAdapter(page=page, lease_manager=lease_manager)
        self.lease_manager = lease_manager

    def select_adapter(self, action: TypedAction) -> BrowserActionPort:
        """Determines the appropriate execution adapter based on action modality and target properties."""
        meta = action.metadata

        # 1. Explicit modality / force overrides
        if meta.get("force_synthetic") is True:
            return self.synthetic_adapter
        if meta.get("force_direct") is True:
            return self.cdp_adapter

        modality = meta.get("modality") or meta.get("execution_mode")
        if modality:
            mod_str = str(modality).lower()
            if mod_str in ("synthetic", "physical", "canvas", "coordinate", "coords"):
                return self.synthetic_adapter
            if mod_str in ("dom", "direct", "cdp", "element"):
                return self.cdp_adapter

        # 2. Canvas element targeting
        if meta.get("is_canvas") is True or meta.get("target_is_canvas") is True:
            return self.synthetic_adapter

        # 3. Direct DOM targeting with Node ID or Selector
        if action.target_node_id:
            return self.cdp_adapter

        # 4. Target Label without Coords
        if action.target_label and action.coords is None:
            return self.cdp_adapter

        # 5. Coords provided without DOM node ID
        if action.coords is not None:
            return self.synthetic_adapter

        # 6. Global page actions (Navigate, Wait, Noop)
        if action.action_type in (ActionType.NAVIGATE, ActionType.WAIT, ActionType.NOOP):
            return self.cdp_adapter

        # 7. Drag and Drop with coordinate endpoints
        if action.action_type == ActionType.DRAG_AND_DROP and (meta.get("target_coords") or meta.get("end_coords")):
            return self.synthetic_adapter

        # Default fallback to CDP direct adapter
        return self.cdp_adapter

    async def execute_action(self, action: TypedAction, lease: ActionLease) -> ActionReceipt:
        """Routes and executes action via the selected execution adapter."""
        adapter = self.select_adapter(action)
        return await adapter.execute_action(action=action, lease=lease)

    async def dispatch_action(self, action: TypedAction, identity: ActionIdentity) -> Dict[str, Any]:
        """Dispatches an action via the selected execution adapter."""
        adapter = self.select_adapter(action)
        return await adapter.dispatch_action(action=action, identity=identity)
