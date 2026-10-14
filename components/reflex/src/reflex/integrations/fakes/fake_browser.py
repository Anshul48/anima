from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
import time
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class FakeElementLocator:
    """Simulated element locator matching Playwright Locator semantics."""
    selector: str
    page: FakeBrowserPage
    tag_name: str = "button"
    text: str = ""
    value: str = ""
    bounds: Tuple[int, int, int, int] = (100, 100, 200, 50)  # x, y, width, height
    is_visible_flag: bool = True
    disabled: bool = False

    async def click(self, button: str = "left", force: bool = False, timeout: float = 30000.0) -> None:
        if self.disabled and not force:
            raise RuntimeError(f"Element '{self.selector}' is disabled and cannot be clicked")
        self.page.event_log.append({
            "event": "element_click",
            "selector": self.selector,
            "button": button,
            "force": force,
            "timestamp": time.time(),
        })

    async def dblclick(self, button: str = "left", force: bool = False, timeout: float = 30000.0) -> None:
        self.page.event_log.append({
            "event": "element_dblclick",
            "selector": self.selector,
            "button": button,
            "force": force,
            "timestamp": time.time(),
        })

    async def fill(self, value: str, timeout: float = 30000.0) -> None:
        self.value = value
        self.page.event_log.append({
            "event": "element_fill",
            "selector": self.selector,
            "value": value,
            "timestamp": time.time(),
        })

    async def type(self, text: str, delay: float = 0.0, timeout: float = 30000.0) -> None:
        self.value += text
        self.page.event_log.append({
            "event": "element_type",
            "selector": self.selector,
            "text": text,
            "delay": delay,
            "timestamp": time.time(),
        })

    async def press(self, key: str, delay: float = 0.0, timeout: float = 30000.0) -> None:
        self.page.event_log.append({
            "event": "element_press",
            "selector": self.selector,
            "key": key,
            "delay": delay,
            "timestamp": time.time(),
        })

    async def hover(self, timeout: float = 30000.0) -> None:
        self.page.event_log.append({
            "event": "element_hover",
            "selector": self.selector,
            "timestamp": time.time(),
        })

    async def scroll_into_view_if_needed(self, timeout: float = 30000.0) -> None:
        self.page.event_log.append({
            "event": "element_scroll_into_view",
            "selector": self.selector,
            "timestamp": time.time(),
        })

    async def drag_to(self, target: Any, timeout: float = 30000.0) -> None:
        target_selector = getattr(target, "selector", str(target))
        self.page.event_log.append({
            "event": "element_drag_to",
            "source_selector": self.selector,
            "target_selector": target_selector,
            "timestamp": time.time(),
        })

    async def is_visible(self) -> bool:
        return self.is_visible_flag

    async def input_value(self) -> str:
        return self.value

    async def text_content(self) -> str:
        return self.text

    async def bounding_box(self) -> Optional[Dict[str, float]]:
        return {
            "x": float(self.bounds[0]),
            "y": float(self.bounds[1]),
            "width": float(self.bounds[2]),
            "height": float(self.bounds[3]),
        }


class FakeMouse:
    """Simulated Playwright Page.mouse interface."""

    def __init__(self, page: FakeBrowserPage):
        self.page = page
        self.x: float = 0.0
        self.y: float = 0.0
        self.history: List[Dict[str, Any]] = []

    async def move(self, x: float, y: float, steps: int = 1) -> None:
        self.x = x
        self.y = y
        entry = {"action": "move", "x": x, "y": y, "steps": steps, "timestamp": time.time()}
        self.history.append(entry)
        self.page.event_log.append(entry)

    async def down(self, button: str = "left", click_count: int = 1) -> None:
        entry = {
            "action": "down",
            "button": button,
            "click_count": click_count,
            "x": self.x,
            "y": self.y,
            "timestamp": time.time(),
        }
        self.history.append(entry)
        self.page.event_log.append(entry)

    async def up(self, button: str = "left", click_count: int = 1) -> None:
        entry = {
            "action": "up",
            "button": button,
            "click_count": click_count,
            "x": self.x,
            "y": self.y,
            "timestamp": time.time(),
        }
        self.history.append(entry)
        self.page.event_log.append(entry)

    async def click(
        self,
        x: float,
        y: float,
        button: str = "left",
        click_count: int = 1,
        delay: float = 0.0,
    ) -> None:
        self.x = x
        self.y = y
        entry = {
            "action": "click",
            "x": x,
            "y": y,
            "button": button,
            "click_count": click_count,
            "delay": delay,
            "timestamp": time.time(),
        }
        self.history.append(entry)
        self.page.event_log.append(entry)

    async def dblclick(self, x: float, y: float, button: str = "left") -> None:
        self.x = x
        self.y = y
        entry = {
            "action": "dblclick",
            "x": x,
            "y": y,
            "button": button,
            "click_count": 2,
            "timestamp": time.time(),
        }
        self.history.append(entry)
        self.page.event_log.append(entry)

    async def wheel(self, delta_x: float, delta_y: float) -> None:
        entry = {
            "action": "wheel",
            "delta_x": delta_x,
            "delta_y": delta_y,
            "x": self.x,
            "y": self.y,
            "timestamp": time.time(),
        }
        self.history.append(entry)
        self.page.event_log.append(entry)


class FakeKeyboard:
    """Simulated Playwright Page.keyboard interface."""

    def __init__(self, page: FakeBrowserPage):
        self.page = page
        self.typed_text: str = ""
        self.history: List[Dict[str, Any]] = []

    async def type(self, text: str, delay: float = 0.0) -> None:
        self.typed_text += text
        entry = {"action": "type", "text": text, "delay": delay, "timestamp": time.time()}
        self.history.append(entry)
        self.page.event_log.append(entry)

    async def press(self, key: str, delay: float = 0.0) -> None:
        entry = {"action": "press", "key": key, "delay": delay, "timestamp": time.time()}
        self.history.append(entry)
        self.page.event_log.append(entry)

    async def down(self, key: str) -> None:
        entry = {"action": "down", "key": key, "timestamp": time.time()}
        self.history.append(entry)
        self.page.event_log.append(entry)

    async def up(self, key: str) -> None:
        entry = {"action": "up", "key": key, "timestamp": time.time()}
        self.history.append(entry)
        self.page.event_log.append(entry)


class FakeCDPSession:
    """Simulated CDP Client Session supporting Input, DOM, and Page domains."""

    def __init__(self, page: FakeBrowserPage):
        self.page = page
        self.sent_messages: List[Dict[str, Any]] = []
        self.handlers: Dict[str, Any] = {}

    async def send(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        params = params or {}
        entry = {"method": method, "params": dict(params), "timestamp": time.time()}
        self.sent_messages.append(entry)
        self.page.event_log.append({"event": "cdp_send", "method": method, "params": dict(params)})

        if method in self.handlers:
            return await self.handlers[method](params)

        if method == "Input.dispatchMouseEvent":
            mouse_type = params.get("type", "mouseMoved")
            x = float(params.get("x", 0.0))
            y = float(params.get("y", 0.0))
            button = params.get("button", "none")
            click_count = params.get("clickCount", 1)
            delta_x = float(params.get("deltaX", 0.0))
            delta_y = float(params.get("deltaY", 0.0))
            
            if mouse_type == "mouseMoved":
                await self.page.mouse.move(x, y)
            elif mouse_type == "mousePressed":
                await self.page.mouse.down(button=button, click_count=click_count)
            elif mouse_type == "mouseReleased":
                await self.page.mouse.up(button=button, click_count=click_count)
            elif mouse_type == "mouseWheel":
                await self.page.mouse.wheel(delta_x=delta_x, delta_y=delta_y)
            return {"status": "ok"}

        if method == "Input.dispatchKeyEvent":
            key_type = params.get("type", "keyDown")
            text = params.get("text", "")
            key = params.get("key", text)
            if key_type == "keyDown":
                await self.page.keyboard.down(key)
            elif key_type == "keyUp":
                await self.page.keyboard.up(key)
            elif key_type == "char" and text:
                await self.page.keyboard.type(text)
            return {"status": "ok"}

        if method == "DOM.focus":
            return {"status": "ok"}

        if method == "DOM.scrollIntoViewIfNeeded":
            return {"status": "ok"}

        if method == "Page.navigate":
            url = params.get("url", "")
            await self.page.goto(url)
            return {"frameId": "main_frame", "loaderId": "loader_001"}

        if method == "Runtime.evaluate":
            return {"result": {"type": "undefined"}}

        return {"status": "ok"}


class FakeBrowserPage:
    """Deterministic in-memory Fake Playwright Page for fast qualification testing."""

    def __init__(self, viewport_width: int = 1280, viewport_height: int = 800):
        self.url: str = "about:blank"
        self.viewport_size: Dict[str, int] = {"width": viewport_width, "height": viewport_height}
        self.mouse = FakeMouse(self)
        self.keyboard = FakeKeyboard(self)
        self.cdp_session = FakeCDPSession(self)
        self.elements: Dict[str, FakeElementLocator] = {}
        self.event_log: List[Dict[str, Any]] = []

    def register_element(
        self,
        selector: str,
        tag_name: str = "button",
        text: str = "",
        value: str = "",
        bounds: Tuple[int, int, int, int] = (100, 100, 200, 50),
        is_visible: bool = True,
        disabled: bool = False,
    ) -> FakeElementLocator:
        """Registers a mock element matching selector queries."""
        elem = FakeElementLocator(
            selector=selector,
            page=self,
            tag_name=tag_name,
            text=text,
            value=value,
            bounds=bounds,
            is_visible_flag=is_visible,
            disabled=disabled,
        )
        self.elements[selector] = elem
        return elem

    async def goto(self, url: str, timeout: float = 30000.0) -> None:
        self.url = url
        self.event_log.append({
            "event": "page_goto",
            "url": url,
            "timestamp": time.time(),
        })

    async def wait_for_timeout(self, timeout_ms: float) -> None:
        self.event_log.append({
            "event": "wait_for_timeout",
            "timeout_ms": timeout_ms,
            "timestamp": time.time(),
        })
        if timeout_ms > 0:
            await asyncio.sleep(min(timeout_ms / 1000.0, 0.05))

    def locator(self, selector: str) -> FakeElementLocator:
        """Resolves element locator, creating on-demand if not pre-registered."""
        if selector in self.elements:
            return self.elements[selector]
        # Auto-create fallback element locator
        elem = FakeElementLocator(selector=selector, page=self)
        self.elements[selector] = elem
        return elem

    def get_by_text(self, text: str, exact: bool = False) -> FakeElementLocator:
        selector = f"text={text}"
        for elem in self.elements.values():
            if exact and elem.text == text:
                return elem
            if not exact and text in elem.text:
                return elem
        return self.locator(selector)

    def get_by_role(self, role: str, name: Optional[str] = None) -> FakeElementLocator:
        selector = f"role={role}[name={name}]" if name else f"role={role}"
        return self.locator(selector)

    async def evaluate(self, script: str, arg: Any = None) -> Any:
        self.event_log.append({
            "event": "page_evaluate",
            "script": script,
            "arg": arg,
            "timestamp": time.time(),
        })
        return None

    async def drag_and_drop(self, source: str, target: str) -> None:
        self.event_log.append({
            "event": "page_drag_and_drop",
            "source": source,
            "target": target,
            "timestamp": time.time(),
        })

    def get_cdp_session(self) -> FakeCDPSession:
        return self.cdp_session

    def clear_logs(self) -> None:
        self.event_log.clear()
        self.mouse.history.clear()
        self.keyboard.history.clear()
        self.cdp_session.sent_messages.clear()


# Alias for backward compatibility
FakeBrowserAdapter = FakeBrowserPage
