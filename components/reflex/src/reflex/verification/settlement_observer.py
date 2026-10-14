"""Settlement Observer: Multi-signal browser quiescence and stability detector."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Set, Tuple

from reflex.ports.clock import ClockPort, SystemClock


class CDPSessionProtocol(Protocol):
    """Protocol for CDP client connections."""

    async def send(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        ...


@dataclass(frozen=True)
class SettlementResult:
    """Outcome of a browser settlement wait cycle."""
    settled: bool
    timed_out: bool
    duration_ms: float
    in_flight_count: int
    mutations_count: int
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "settled": self.settled,
            "timed_out": self.timed_out,
            "duration_ms": self.duration_ms,
            "in_flight_count": self.in_flight_count,
            "mutations_count": self.mutations_count,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SettlementResult:
        return cls(
            settled=bool(data.get("settled", False)),
            timed_out=bool(data.get("timed_out", False)),
            duration_ms=float(data.get("duration_ms", 0.0)),
            in_flight_count=int(data.get("in_flight_count", 0)),
            mutations_count=int(data.get("mutations_count", 0)),
            details=str(data.get("details", "")),
        )


class SettlementObserver:
    """Monitors browser quiescence across network in-flight requests, DOM mutations,

    CSS animations, and page lifecycle events with bounding timeouts.
    """

    def __init__(
        self,
        cdp_session: Optional[CDPSessionProtocol] = None,
        page: Optional[Any] = None,
        clock: Optional[ClockPort] = None,
        debounce_window_ms: float = 150.0,
        max_timeout_ms: float = 5000.0,
        poll_interval_ms: float = 15.0,
    ) -> None:
        self.cdp_session = cdp_session
        self.page = page
        self._clock: ClockPort = clock or SystemClock()
        self.debounce_window_ms = debounce_window_ms
        self.max_timeout_ms = max_timeout_ms
        self.poll_interval_ms = poll_interval_ms

        self._in_flight_requests: Set[str] = set()
        self._excluded_streaming_requests: Set[str] = set()
        self._last_mutation_time_ms: float = 0.0
        self._mutations_count: int = 0
        self._running_animations_count: int = 0
        self._is_page_loaded: bool = True
        self._event_log: List[Dict[str, Any]] = []

    @property
    def in_flight_request_count(self) -> int:
        return len(self._in_flight_requests)

    @property
    def mutations_count(self) -> int:
        return self._mutations_count

    @property
    def running_animations_count(self) -> int:
        return self._running_animations_count

    @property
    def is_page_loaded(self) -> bool:
        return self._is_page_loaded

    def record_request_started(
        self,
        request_id: str,
        url: str = "",
        is_streaming: bool = False,
    ) -> None:
        """Records an outgoing network request."""
        # Long-polling / streaming / WebSocket exclusion
        url_lower = url.lower()
        if is_streaming or url_lower.startswith("ws://") or url_lower.startswith("wss://") or "eventsource" in url_lower:
            self._excluded_streaming_requests.add(request_id)
            return

        self._in_flight_requests.add(request_id)
        self._event_log.append({
            "event": "request_started",
            "request_id": request_id,
            "url": url,
            "timestamp_ms": self._clock.now_ms(),
        })

    def record_request_finished(self, request_id: str) -> None:
        """Records completion of a network request."""
        self._in_flight_requests.discard(request_id)
        self._excluded_streaming_requests.discard(request_id)
        self._event_log.append({
            "event": "request_finished",
            "request_id": request_id,
            "timestamp_ms": self._clock.now_ms(),
        })

    def record_request_failed(self, request_id: str, error: str = "") -> None:
        """Records failure of a network request."""
        self._in_flight_requests.discard(request_id)
        self._excluded_streaming_requests.discard(request_id)
        self._event_log.append({
            "event": "request_failed",
            "request_id": request_id,
            "error": error,
            "timestamp_ms": self._clock.now_ms(),
        })

    def record_mutation(self, timestamp_ms: Optional[float] = None) -> None:
        """Records a DOM mutation and resets the quiet debounce timer."""
        now_ms = timestamp_ms if timestamp_ms is not None else self._clock.now_ms()
        self._last_mutation_time_ms = now_ms
        self._mutations_count += 1
        self._event_log.append({
            "event": "dom_mutation",
            "timestamp_ms": now_ms,
            "total_mutations": self._mutations_count,
        })

    def record_animation_start(self) -> None:
        """Records start of a CSS/JS animation or transition."""
        self._running_animations_count += 1
        self._event_log.append({
            "event": "animation_start",
            "running_count": self._running_animations_count,
            "timestamp_ms": self._clock.now_ms(),
        })

    def record_animation_end(self) -> None:
        """Records end of a CSS/JS animation or transition."""
        self._running_animations_count = max(0, self._running_animations_count - 1)
        self._event_log.append({
            "event": "animation_end",
            "running_count": self._running_animations_count,
            "timestamp_ms": self._clock.now_ms(),
        })

    def record_page_loaded(self, is_loaded: bool = True) -> None:
        """Records page lifecycle state (interactive/complete vs loading)."""
        self._is_page_loaded = is_loaded
        self._event_log.append({
            "event": "page_loaded",
            "is_loaded": is_loaded,
            "timestamp_ms": self._clock.now_ms(),
        })

    def handle_cdp_event(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        """Processes CDP protocol event notifications for settlement tracking."""
        params = params or {}
        if method == "Network.requestWillBeSent":
            req_id = str(params.get("requestId", ""))
            url = str(params.get("request", {}).get("url", ""))
            req_type = str(params.get("type", ""))
            is_streaming = req_type in ("WebSocket", "EventSource") or "text/event-stream" in str(params)
            self.record_request_started(req_id, url=url, is_streaming=is_streaming)
        elif method in ("Network.loadingFinished", "Network.responseReceived"):
            req_id = str(params.get("requestId", ""))
            if method == "Network.loadingFinished":
                self.record_request_finished(req_id)
        elif method == "Network.loadingFailed":
            req_id = str(params.get("requestId", ""))
            err = str(params.get("errorText", ""))
            self.record_request_failed(req_id, error=err)
        elif method in (
            "DOM.childNodeInserted",
            "DOM.childNodeRemoved",
            "DOM.attributeModified",
            "DOM.characterDataModified",
        ):
            self.record_mutation()
        elif method == "Page.loadEventFired":
            self.record_page_loaded(True)
        elif method == "Page.frameStartedLoading":
            self.record_page_loaded(False)
        elif method in ("Page.frameStoppedLoading", "Page.frameNavigated"):
            self.record_page_loaded(True)

    def is_network_idle(self) -> bool:
        """Returns True if no non-streaming network requests are in-flight."""
        return len(self._in_flight_requests) == 0

    def is_dom_quiescent(self, current_time_ms: Optional[float] = None) -> bool:
        """Returns True if DOM mutations have ceased for at least debounce_window_ms."""
        now_ms = current_time_ms if current_time_ms is not None else self._clock.now_ms()
        if self._last_mutation_time_ms <= 0.0:
            return True
        return (now_ms - self._last_mutation_time_ms) >= self.debounce_window_ms

    def is_animations_idle(self) -> bool:
        """Returns True if no running CSS animations/transitions are registered."""
        return self._running_animations_count <= 0

    def is_settled(self, current_time_ms: Optional[float] = None) -> bool:
        """Returns True if all four stability conditions are satisfied."""
        return (
            self.is_network_idle()
            and self.is_dom_quiescent(current_time_ms)
            and self.is_animations_idle()
            and self.is_page_loaded
        )

    def reset(self) -> None:
        """Resets all settlement counters and in-flight request tracking."""
        self._in_flight_requests.clear()
        self._excluded_streaming_requests.clear()
        self._last_mutation_time_ms = 0.0
        self._mutations_count = 0
        self._running_animations_count = 0
        self._is_page_loaded = True
        self._event_log.clear()

    async def _probe_live_browser_state(self) -> Tuple[bool, bool, bool]:
        """Probes live CDP session or Playwright Page if available.

        Returns (ready_state_complete, animations_idle, dom_busy).
        """
        if self.page is not None:
            try:
                # Check document readyState and running animations
                probe_res = await self.page.evaluate(
                    """() => {
                        const ready = document.readyState === 'complete' || document.readyState === 'interactive';
                        let animsIdle = true;
                        if (typeof document.getAnimations === 'function') {
                            animsIdle = document.getAnimations().filter(a => a.playState === 'running').length === 0;
                        }
                        const ariaBusy = document.querySelector('[aria-busy="true"]') !== null;
                        return { ready, animsIdle, ariaBusy };
                    }"""
                )
                if isinstance(probe_res, dict):
                    return (
                        bool(probe_res.get("ready", True)),
                        bool(probe_res.get("animsIdle", True)),
                        bool(probe_res.get("ariaBusy", False)),
                    )
            except Exception:
                pass

        elif self.cdp_session is not None:
            try:
                resp = await self.cdp_session.send(
                    "Runtime.evaluate",
                    {
                        "expression": """(() => {
                            const ready = document.readyState === 'complete' || document.readyState === 'interactive';
                            let animsIdle = true;
                            if (typeof document.getAnimations === 'function') {
                                animsIdle = document.getAnimations().filter(a => a.playState === 'running').length === 0;
                            }
                            const ariaBusy = document.querySelector('[aria-busy="true"]') !== null;
                            return JSON.stringify({ ready, animsIdle, ariaBusy });
                        })()""",
                        "returnByValue": True,
                    },
                )
                val_str = resp.get("result", {}).get("value")
                if val_str:
                    import json
                    parsed = json.loads(val_str)
                    return (
                        bool(parsed.get("ready", True)),
                        bool(parsed.get("animsIdle", True)),
                        bool(parsed.get("ariaBusy", False)),
                    )
            except Exception:
                pass

        return (True, True, False)

    async def wait_for_settlement(
        self,
        timeout_ms: Optional[float] = None,
        debounce_window_ms: Optional[float] = None,
    ) -> SettlementResult:
        """Awaits browser stability across network, DOM mutations, animations, and lifecycle.

        Guarantees strict timeout bounding to prevent indefinite hangs.
        """
        effective_timeout = timeout_ms if timeout_ms is not None else self.max_timeout_ms
        effective_debounce = debounce_window_ms if debounce_window_ms is not None else self.debounce_window_ms

        start_mono = self._clock.monotonic_ms()

        while True:
            now_mono = self._clock.monotonic_ms()
            elapsed_ms = now_mono - start_mono
            now_wall = self._clock.now_ms()

            # 1. Check timeout bounding
            if elapsed_ms >= effective_timeout:
                reasons: List[str] = []
                if not self.is_network_idle():
                    reasons.append(f"{len(self._in_flight_requests)} network request(s) in-flight")
                if self._last_mutation_time_ms > 0 and (now_wall - self._last_mutation_time_ms) < effective_debounce:
                    reasons.append(f"DOM mutating (last mutation {(now_wall - self._last_mutation_time_ms):.1f}ms ago)")
                if self._running_animations_count > 0:
                    reasons.append(f"{self._running_animations_count} animation(s) active")
                if not self._is_page_loaded:
                    reasons.append("page load in progress")

                reason_str = ", ".join(reasons) if reasons else "settlement duration exceeded ceiling"
                return SettlementResult(
                    settled=False,
                    timed_out=True,
                    duration_ms=elapsed_ms,
                    in_flight_count=len(self._in_flight_requests),
                    mutations_count=self._mutations_count,
                    details=f"Settlement timed out after {elapsed_ms:.1f}ms ({reason_str})",
                )

            # 2. Probe live browser state if attached
            live_ready, live_anims_idle, live_busy = await self._probe_live_browser_state()

            # 3. Check all quiescence criteria
            net_idle = len(self._in_flight_requests) == 0
            dom_quiet = (self._last_mutation_time_ms <= 0) or ((now_wall - self._last_mutation_time_ms) >= effective_debounce)
            anims_idle = (self._running_animations_count <= 0) and live_anims_idle
            lifecycle_ready = self._is_page_loaded and live_ready and not live_busy

            if net_idle and dom_quiet and anims_idle and lifecycle_ready:
                return SettlementResult(
                    settled=True,
                    timed_out=False,
                    duration_ms=elapsed_ms,
                    in_flight_count=0,
                    mutations_count=self._mutations_count,
                    details=f"Settled successfully in {elapsed_ms:.1f}ms ({self._mutations_count} mutations detected)",
                )

            # 4. Sleep for poll interval before next check
            sleep_s = max(0.001, self.poll_interval_ms / 1000.0)
            await self._clock.sleep(sleep_s)
