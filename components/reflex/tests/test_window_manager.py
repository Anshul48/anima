"""Test Suite: Native Window Manager and Deterministic Desktop Tiling."""

from __future__ import annotations

import unittest

from reflex.execution.native.window_manager import (
    MockWindowManagerSubstrate,
    NativeWindowManager,
    WindowInfo,
)


class TestNativeWindowManager(unittest.TestCase):
    """Tests window discovery, manipulation, and deterministic layout tiling."""

    def setUp(self) -> None:
        self.substrate = MockWindowManagerSubstrate()
        self.wm = NativeWindowManager(
            substrate=self.substrate,
            screen_width=1920,
            screen_height=1080,
        )

    def test_window_discovery_and_filtering(self) -> None:
        """Asserts window listing with process and title filters."""
        h1 = self.substrate.add_window("Document1.txt - Notepad", process_name="notepad.exe")
        h2 = self.substrate.add_window("Document2.txt - Notepad", process_name="notepad.exe")
        h3 = self.substrate.add_window("Calculator", process_name="calc.exe")
        h4 = self.substrate.add_window("Hidden Task", is_visible=False)

        all_visible = self.wm.list_windows()
        self.assertEqual(len(all_visible), 3)

        notepads = self.wm.list_windows(process_name="notepad")
        self.assertEqual(len(notepads), 2)
        self.assertEqual({w.handle for w in notepads}, {h1, h2})

        calc = self.wm.find_windows("calc")
        self.assertEqual(len(calc), 1)
        self.assertEqual(calc[0].handle, h3)

    def test_window_focus_and_retrieval(self) -> None:
        """Asserts focusing brings window to foreground."""
        h1 = self.substrate.add_window("Notes 1", process_name="notepad.exe")
        h2 = self.substrate.add_window("Notes 2", process_name="notepad.exe")

        self.wm.focus_window(h2)
        focused = self.wm.get_focused_window()
        self.assertIsNotNone(focused)
        self.assertEqual(focused.handle, h2)

        # Focus by title query
        self.wm.focus_window("Notes 1")
        focused2 = self.wm.get_focused_window()
        self.assertIsNotNone(focused2)
        self.assertEqual(focused2.handle, h1)

    def test_window_move_and_resize(self) -> None:
        """Asserts exact bounds modification."""
        h = self.substrate.add_window("Test Window")
        ok = self.wm.move_resize_window(h, x=100, y=150, width=800, height=500)
        self.assertTrue(ok)

        window = self.wm.list_windows()[0]
        self.assertEqual(window.bounds, (100, 150, 800, 500))

    def test_window_minimization_maximization_and_restore(self) -> None:
        """Asserts minimize, maximize, and restore window states."""
        h = self.substrate.add_window("Test Window")

        self.wm.minimize_window(h)
        w = self.substrate.windows[h]
        self.assertTrue(w["is_minimized"])

        self.wm.maximize_window(h)
        w = self.substrate.windows[h]
        self.assertTrue(w["is_maximized"])
        self.assertFalse(w["is_minimized"])

        self.wm.restore_window(h)
        w = self.substrate.windows[h]
        self.assertFalse(w["is_maximized"])
        self.assertFalse(w["is_minimized"])

    def test_window_close(self) -> None:
        """Asserts closing window removes it from active windows."""
        h = self.substrate.add_window("To Close")
        self.assertEqual(len(self.wm.list_windows()), 1)

        ok = self.wm.close_window(h)
        self.assertTrue(ok)
        self.assertEqual(len(self.wm.list_windows()), 0)

    def test_tile_windows_two_windows_horizontal_columns(self) -> None:
        """Asserts 2 windows tile side-by-side."""
        self.substrate.add_window("Note 1", process_name="notepad.exe")
        self.substrate.add_window("Note 2", process_name="notepad.exe")

        tiled = self.wm.tile_windows(layout="horizontal", margin=10)
        self.assertEqual(len(tiled), 2)

        # Expected width per column: (1920 - 3 * 10) // 2 = 1890 // 2 = 945
        b1 = tiled[0]["bounds"]
        b2 = tiled[1]["bounds"]
        self.assertEqual(b1["x"], 10)
        self.assertEqual(b1["width"], 945)
        self.assertEqual(b2["x"], 10 + 945 + 10)
        self.assertEqual(b2["width"], 945)

    def test_tile_windows_vertical_rows(self) -> None:
        """Asserts windows tile in stacked vertical rows."""
        self.substrate.add_window("Note 1")
        self.substrate.add_window("Note 2")

        tiled = self.wm.tile_windows(layout="vertical", margin=10)
        self.assertEqual(len(tiled), 2)

        b1 = tiled[0]["bounds"]
        b2 = tiled[1]["bounds"]
        self.assertEqual(b1["y"], 10)
        self.assertEqual(b2["y"], 10 + b1["height"] + 10)

    def test_tile_windows_grid_four_windows_matrix(self) -> None:
        """Asserts 4 windows tile in a 2x2 grid matrix."""
        for i in range(1, 5):
            self.substrate.add_window(f"Note {i}", process_name="notepad.exe")

        tiled = self.wm.tile_windows(layout="grid", margin=10)
        self.assertEqual(len(tiled), 4)

        # 4 windows -> cols=2, rows=2
        # col_width = (1920 - 30) // 2 = 945
        # row_height = (1080 - 30) // 2 = 525
        self.assertEqual(tiled[0]["bounds"], {"x": 10, "y": 10, "width": 945, "height": 525})
        self.assertEqual(tiled[1]["bounds"], {"x": 965, "y": 10, "width": 945, "height": 525})
        self.assertEqual(tiled[2]["bounds"], {"x": 10, "y": 545, "width": 945, "height": 525})
        self.assertEqual(tiled[3]["bounds"], {"x": 965, "y": 545, "width": 945, "height": 525})

    def test_tile_windows_restores_minimized_window(self) -> None:
        """Asserts minimized windows are automatically restored before tiling."""
        h1 = self.substrate.add_window("Note 1", is_minimized=True)
        h2 = self.substrate.add_window("Note 2")

        tiled = self.wm.tile_windows(layout="grid")
        self.assertEqual(len(tiled), 2)
        self.assertFalse(self.substrate.windows[h1]["is_minimized"])

    def test_tile_windows_clamping_for_large_window_count(self) -> None:
        """Asserts that tiling 100 windows clamps dimensions to minimum safe bounds."""
        for i in range(100):
            self.substrate.add_window(f"Win_{i}")

        tiled = self.wm.tile_windows(layout="horizontal", screen_width=800, margin=10)
        self.assertEqual(len(tiled), 100)
        for w in tiled:
            self.assertGreaterEqual(w["bounds"]["width"], 50)
            self.assertGreaterEqual(w["bounds"]["height"], 50)

    def test_tile_windows_layout_aliases(self) -> None:
        """Asserts layout aliases like 'columns' and 'stacked' work."""
        self.substrate.add_window("A")
        self.substrate.add_window("B")

        tiled_cols = self.wm.tile_windows(layout="columns")
        self.assertEqual(len(tiled_cols), 2)

        tiled_stacked = self.wm.tile_windows(layout="stacked")
        self.assertEqual(len(tiled_stacked), 2)

    def test_resolve_handle_formats(self) -> None:
        """Asserts resolving handles via int, hex, hwnd string, and title."""
        h = self.substrate.add_window("Alpha Window")
        self.assertEqual(self.wm._resolve_handle(h), h)
        self.assertEqual(self.wm._resolve_handle(str(h)), h)
        self.assertEqual(self.wm._resolve_handle(f"hwnd {h}"), h)
        self.assertEqual(self.wm._resolve_handle(f"[HWND {h}]"), h)
        self.assertEqual(self.wm._resolve_handle("Alpha"), h)

    def test_launch_application_mock_substrate(self) -> None:
        """Asserts launch_application adds windows to mock substrate."""
        self.wm.launch_application("notepad.exe")
        wins = self.wm.list_windows()
        self.assertEqual(len(wins), 1)
        self.assertIn("Notepad", wins[0].title)

        self.wm.launch_application("start chrome")
        wins2 = self.wm.list_windows()
        self.assertEqual(len(wins2), 2)
        self.assertTrue(any("Chrome" in w.title for w in wins2))

    def test_native_window_manager_defaults_to_mock_on_linux(self) -> None:
        """Asserts NativeWindowManager instantiated without substrate defaults to mock on non-Windows."""
        wm_default = NativeWindowManager()
        self.assertIsNotNone(wm_default.substrate)
        self.assertIsInstance(wm_default.substrate, MockWindowManagerSubstrate)


if __name__ == "__main__":
    unittest.main()
