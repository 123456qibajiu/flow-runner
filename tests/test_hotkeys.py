"""F9 捕获边沿检测回归测试。"""

import unittest
from unittest import mock

import hotkeys


class F9DetectionTests(unittest.TestCase):
    def test_low_bit_history_does_not_trigger_capture(self):
        states = iter([0x0001, 0x0001, 0x8000])
        with (
            mock.patch.object(hotkeys, "_get_f9_state", side_effect=states),
            mock.patch.object(hotkeys.time, "sleep"),
        ):
            detected = hotkeys.wait_for_new_f9_press(lambda: False)

        self.assertTrue(detected)

    def test_preexisting_key_down_must_be_released_before_new_press(self):
        states = iter([0x8000, 0x8000, 0x0000, 0x0000, 0x8000])
        with (
            mock.patch.object(hotkeys, "_get_f9_state", side_effect=states) as state,
            mock.patch.object(hotkeys.time, "sleep"),
        ):
            detected = hotkeys.wait_for_new_f9_press(lambda: False)

        self.assertTrue(detected)
        self.assertEqual(state.call_count, 5)

    def test_wait_can_be_cancelled(self):
        with (
            mock.patch.object(hotkeys, "_get_f9_state", return_value=0),
            mock.patch.object(hotkeys.time, "sleep"),
        ):
            detected = hotkeys.wait_for_new_f9_press(lambda: True)

        self.assertFalse(detected)


if __name__ == "__main__":
    unittest.main()
