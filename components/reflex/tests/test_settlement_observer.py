"""Unit and integration test suite for SettlementObserver."""

import asyncio
import unittest

from reflex.ports.clock import DeterministicClock, SystemClock
from reflex.perception.browser.cdp_provider import FakeCDPClient
from reflex.integrations.fakes.fake_browser import FakeBrowserPage
from reflex.verification.settlement_observer import (
    SettlementObserver,
    SettlementResult,
)


class TestSettlementObserver(unittest.TestCase):
    """Test suite covering browser settlement and quiescence detection."""

    def test_immediate_settlement_when_idle(self):
        """Observer immediately returns settled if no network, mutations, or animations are active."""
        async def run():
            clock = DeterministicClock(start_time_ms=1000.0)
            observer = SettlementObserver(clock=clock, debounce_window_ms=100.0, max_timeout_ms=2000.0)

            result = await observer.wait_for_settlement()
            self.assertTrue(result.settled)
            self.assertFalse(result.timed_out)
            self.assertEqual(result.in_flight_count, 0)
            self.assertEqual(result.mutations_count, 0)

        asyncio.run(run())

    def test_network_request_in_flight_blocks_settlement_until_complete(self):
        """Observer waits for in-flight network requests to hit 0 before settling."""
        async def run():
            clock = SystemClock()
            observer = SettlementObserver(clock=clock, debounce_window_ms=20.0, max_timeout_ms=1000.0, poll_interval_ms=5.0)

            observer.record_request_started("req_1", url="https://api.example.com/data")
            self.assertEqual(observer.in_flight_request_count, 1)
            self.assertFalse(observer.is_settled())

            # Spawn settlement task
            task = asyncio.create_task(observer.wait_for_settlement())
            await asyncio.sleep(0.02)

            self.assertFalse(task.done())

            # Finish network request
            observer.record_request_finished("req_1")
            self.assertEqual(observer.in_flight_request_count, 0)

            result = await task
            self.assertTrue(result.settled)
            self.assertFalse(result.timed_out)

        asyncio.run(run())

    def test_dom_mutation_debounce_resets_timer(self):
        """DOM mutations reset the quiet debounce window."""
        async def run():
            clock = DeterministicClock(start_time_ms=1000.0)
            observer = SettlementObserver(clock=clock, debounce_window_ms=150.0, max_timeout_ms=3000.0, poll_interval_ms=20.0)

            # Record initial mutation at t=1000
            observer.record_mutation(timestamp_ms=1000.0)
            self.assertFalse(observer.is_dom_quiescent(current_time_ms=1050.0))

            # Simulate another mutation at t=1100 before debounce expired
            observer.record_mutation(timestamp_ms=1100.0)
            self.assertFalse(observer.is_dom_quiescent(current_time_ms=1200.0))  # 100ms since last mutation < 150ms

            # At t=1260 (160ms since last mutation), DOM is quiescent
            self.assertTrue(observer.is_dom_quiescent(current_time_ms=1260.0))
            self.assertEqual(observer.mutations_count, 2)

        asyncio.run(run())

    def test_timeout_bounding_guard(self):
        """Observer strictly bounds wait duration and flags timed_out when max_timeout is exceeded."""
        async def run():
            clock = DeterministicClock(start_time_ms=1000.0)
            observer = SettlementObserver(
                clock=clock,
                debounce_window_ms=100.0,
                max_timeout_ms=500.0,
                poll_interval_ms=50.0,
            )

            # Keep a network request pending permanently
            observer.record_request_started("stuck_req", url="https://hang.example.com")

            result = await observer.wait_for_settlement()
            self.assertFalse(result.settled)
            self.assertTrue(result.timed_out)
            self.assertGreaterEqual(result.duration_ms, 500.0)
            self.assertEqual(result.in_flight_count, 1)
            self.assertIn("network request(s) in-flight", result.details)

        asyncio.run(run())

    def test_css_animation_tracking(self):
        """Active CSS/JS animations block settlement until completion."""
        async def run():
            clock = SystemClock()
            observer = SettlementObserver(clock=clock, debounce_window_ms=20.0, max_timeout_ms=1000.0, poll_interval_ms=5.0)

            observer.record_animation_start()
            self.assertFalse(observer.is_animations_idle())

            task = asyncio.create_task(observer.wait_for_settlement())
            await asyncio.sleep(0.02)
            self.assertFalse(task.done())

            observer.record_animation_end()
            self.assertTrue(observer.is_animations_idle())

            result = await task
            self.assertTrue(result.settled)

        asyncio.run(run())

    def test_page_lifecycle_loading_state(self):
        """Page frame loading state prevents premature settlement."""
        async def run():
            clock = SystemClock()
            observer = SettlementObserver(clock=clock, debounce_window_ms=20.0, max_timeout_ms=1000.0, poll_interval_ms=5.0)

            observer.record_page_loaded(False)
            self.assertFalse(observer.is_page_loaded)

            task = asyncio.create_task(observer.wait_for_settlement())
            await asyncio.sleep(0.02)
            self.assertFalse(task.done())

            observer.record_page_loaded(True)
            result = await task
            self.assertTrue(result.settled)

        asyncio.run(run())

    def test_streaming_and_websocket_exclusions(self):
        """WebSocket and Server-Sent Event streaming connections are excluded from in-flight counters."""
        clock = DeterministicClock(start_time_ms=1000.0)
        observer = SettlementObserver(clock=clock)

        observer.record_request_started("ws_1", url="wss://stream.example.com/socket", is_streaming=True)
        observer.record_request_started("sse_1", url="https://api.example.com/eventsource")

        self.assertEqual(observer.in_flight_request_count, 0)
        self.assertTrue(observer.is_network_idle())

    def test_cdp_event_handler(self):
        """Handles CDP network, DOM, and lifecycle protocol events."""
        clock = DeterministicClock(start_time_ms=1000.0)
        observer = SettlementObserver(clock=clock)

        # Network lifecycle
        observer.handle_cdp_event("Network.requestWillBeSent", {"requestId": "r100", "request": {"url": "http://test.com"}})
        self.assertEqual(observer.in_flight_request_count, 1)

        observer.handle_cdp_event("Network.loadingFinished", {"requestId": "r100"})
        self.assertEqual(observer.in_flight_request_count, 0)

        # Failed request
        observer.handle_cdp_event("Network.requestWillBeSent", {"requestId": "r101", "request": {"url": "http://err.com"}})
        observer.handle_cdp_event("Network.loadingFailed", {"requestId": "r101", "errorText": "net::ERR_FAILED"})
        self.assertEqual(observer.in_flight_request_count, 0)

        # DOM mutations
        observer.handle_cdp_event("DOM.childNodeInserted", {})
        self.assertEqual(observer.mutations_count, 1)

        # Page lifecycle
        observer.handle_cdp_event("Page.frameStartedLoading", {})
        self.assertFalse(observer.is_page_loaded)
        observer.handle_cdp_event("Page.loadEventFired", {})
        self.assertTrue(observer.is_page_loaded)

    def test_settlement_result_serialization(self):
        """SettlementResult serializes to and from dict correctly."""
        res = SettlementResult(
            settled=True,
            timed_out=False,
            duration_ms=154.2,
            in_flight_count=0,
            mutations_count=3,
            details="Settled cleanly",
        )
        d = res.to_dict()
        reconstructed = SettlementResult.from_dict(d)
        self.assertEqual(res, reconstructed)


if __name__ == "__main__":
    unittest.main()
