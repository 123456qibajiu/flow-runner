"""全局捕获热键检测。"""

import ctypes
import time

VK_F9 = 0x78


def _get_f9_state():
    return ctypes.windll.user32.GetAsyncKeyState(VK_F9)


def is_f9_down():
    """只检查 F9 当前是否按下，不使用可能残留的低位历史状态。"""
    return bool(_get_f9_state() & 0x8000)


def wait_for_new_f9_press(cancelled, poll_interval=0.02):
    """忽略旧状态，等待一次“释放后重新按下”的 F9 动作。"""
    while is_f9_down():
        if cancelled():
            return False
        time.sleep(poll_interval)

    while not cancelled():
        if is_f9_down():
            return True
        time.sleep(poll_interval)
    return False
