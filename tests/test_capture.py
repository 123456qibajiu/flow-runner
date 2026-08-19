"""捕获组件回归测试：不依赖 Windows UIA 或真实桌面。"""

import importlib
import sys
import types
import unittest
from types import SimpleNamespace
from unittest import mock


def _load_engine_with_fake_dependencies():
    fake_auto = types.ModuleType("uiautomation")
    fake_auto.ControlType = SimpleNamespace(WindowControl=1)
    fake_auto.ControlFromCursor = lambda: None

    fake_pyautogui = types.ModuleType("pyautogui")
    fake_pyautogui.position = lambda: SimpleNamespace(x=410, y=320)

    fake_pyperclip = types.ModuleType("pyperclip")
    fake_pyperclip.copy = lambda _text: None

    sys.modules["uiautomation"] = fake_auto
    sys.modules["pyautogui"] = fake_pyautogui
    sys.modules["pyperclip"] = fake_pyperclip
    sys.modules.pop("engine", None)
    return importlib.import_module("engine")


engine = _load_engine_with_fake_dependencies()


class ElementCaptureFallbackTests(unittest.TestCase):
    def setUp(self):
        engine.pyautogui.position = lambda: SimpleNamespace(x=410, y=320)

    def test_uia_exception_uses_native_window_and_relative_position(self):
        rect = SimpleNamespace(left=100, top=50, right=900, bottom=650)
        native = {
            "hwnd": 123,
            "title": "目标窗口",
            "class_name": "TargetWindowClass",
            "rect": rect,
        }
        with (
            mock.patch.object(
                engine.auto, "ControlFromCursor", side_effect=RuntimeError("UIA unavailable")
            ),
            mock.patch.object(
                engine.ElementCapture, "_native_window_at", return_value=native
            ),
        ):
            info = engine.ElementCapture.capture_at_cursor()

        self.assertEqual(info["window_title"], "目标窗口")
        self.assertEqual(info["win_class"], "TargetWindowClass")
        self.assertEqual((info["rel_x"], info["rel_y"]), (310, 270))
        self.assertEqual((info["x"], info["y"]), (410, 320))
        self.assertEqual(info["control_type"], "UnknownControl")

    def test_total_identification_failure_still_returns_absolute_position(self):
        with (
            mock.patch.object(
                engine.auto, "ControlFromCursor", side_effect=RuntimeError("UIA unavailable")
            ),
            mock.patch.object(
                engine.ElementCapture, "_native_window_at", return_value=None
            ),
        ):
            info = engine.ElementCapture.capture_at_cursor()

        self.assertIsNotNone(info)
        self.assertEqual((info["x"], info["y"]), (410, 320))
        self.assertEqual(info["window_title"], "")
        self.assertIsNone(info["rel_x"])
        self.assertIsNone(info["rel_y"])

    def test_coordinate_capture_uses_native_window_when_uia_fails(self):
        rect = SimpleNamespace(left=10, top=20, right=810, bottom=620)
        native = {
            "hwnd": 456,
            "title": "坐标窗口",
            "class_name": "CoordinateWindowClass",
            "rect": rect,
        }
        with (
            mock.patch.object(
                engine.auto, "ControlFromCursor", side_effect=RuntimeError("UIA unavailable")
            ),
            mock.patch.object(
                engine.ElementCapture, "_native_window_at", return_value=native
            ),
        ):
            info = engine.ElementCapture.capture_cursor_pos()

        self.assertEqual((info["rel_x"], info["rel_y"]), (400, 300))
        self.assertEqual(info["window_title"], "坐标窗口")
        self.assertEqual(info["win_class"], "CoordinateWindowClass")


if __name__ == "__main__":
    unittest.main()
