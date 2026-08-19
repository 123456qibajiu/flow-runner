"""RPA 引擎 - 负责控件识别、步骤执行、流程存取。

v1.8.1: 所有可能在后台线程执行的 UI Automation 入口都会在当前线程
初始化并释放 COM，修复 WinError -2147221008（尚未调用 CoInitialize）。
"""

import time
import json
import ctypes
import webbrowser
from ctypes import wintypes
from functools import wraps

# DPI 感知: 让 GetCursorPos/SetCursorPos 与 UIA 矩形同处物理像素空间。
# 高分屏缩放(125%/150%)场景下若不声明，鼠标坐标会被系统虚拟化导致点击错位。
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import uiautomation as auto
import pyautogui
import pyperclip


def _with_uiautomation_initialized(func):
    """确保每个调用 UIA 的线程都有独立且成对的 COM 生命周期。"""
    @wraps(func)
    def wrapped(*args, **kwargs):
        with auto.UIAutomationInitializerInThread():
            return func(*args, **kwargs)
    return wrapped


# ==================== 步骤类型定义 ====================

STEP_TYPES = {
    "click": "智能点击",
    "click_pos": "坐标点击",
    "input_text": "输入文字",
    "hotkey": "快捷键",
    "wait": "等待",
    "switch_window": "切换窗口",
    "open_url": "打开网址",
}

PARAM_LABELS = {
    "window_title": "窗口标题",
    "win_class": "窗口类名",
    "control_type": "控件类型",
    "name": "控件名称",
    "automation_id": "自动化ID",
    "class_name": "类名",
    "text": "文字内容",
    "keys": "按键组合",
    "seconds": "秒数",
    "url": "网址",
    "x": "X 坐标",
    "y": "Y 坐标",
    "rel_x": "窗口内X",
    "rel_y": "窗口内Y",
}


class Step:
    """一个自动化步骤"""

    def __init__(self, step_type, **params):
        self.type = step_type
        self.params = params

    def to_dict(self):
        return {"type": self.type, "params": self.params}

    @classmethod
    def from_dict(cls, data):
        return cls(data["type"], **data.get("params", {}))

    def describe(self):
        t, p = self.type, self.params
        if t == "click":
            name = p.get("name", "") or p.get("automation_id", "")
            win = p.get("window_title", "?")
            if name:
                return f'点击 [{name}] @ {win}'
            if p.get("rel_x") is not None:
                return f'点击 窗口内({p.get("rel_x")},{p.get("rel_y")}) @ {win}'
            return f'点击 @ {win}'
        elif t == "click_pos":
            if p.get("window_title"):
                return f'窗口内点击 ({p.get("rel_x")},{p.get("rel_y")}) @ {p.get("window_title")}'
            return f'坐标点击 ({p.get("x", "?")}, {p.get("y", "?")})'
        elif t == "input_text":
            text = p.get("text", "")
            display = text[:30] + ("..." if len(text) > 30 else "")
            return f'输入: "{display}"'
        elif t == "hotkey":
            return f'快捷键: {p.get("keys", "?")}'
        elif t == "wait":
            return f'等待 {p.get("seconds", 1)} 秒'
        elif t == "switch_window":
            return f'切换到: {p.get("window_title", "?")}'
        elif t == "open_url":
            return f'打开: {p.get("url", "?")}'
        return f"未知步骤: {t}"


# ==================== 控件捕获 ====================

class ElementCapture:
    """从鼠标位置捕获 UI 控件信息"""

    @staticmethod
    def _safe_control_value(control, attr, default=""):
        """读取 UIA 属性；单个属性失败不应让整次捕获失败。"""
        if control is None:
            return default
        try:
            return getattr(control, attr) or default
        except Exception:
            return default

    @staticmethod
    def _native_window_at(x, y):
        """用 Win32 获取坐标处的顶层窗口，不依赖 UI Automation。"""
        try:
            # 独立加载函数表，避免设置 argtypes 时污染 uiautomation 共用的
            # ctypes.windll.user32 函数对象。
            user32 = ctypes.WinDLL("user32", use_last_error=True)

            # ctypes 默认把返回值当 32 位 int，会在 64 位 Windows 截断 HWND。
            user32.WindowFromPoint.argtypes = [wintypes.POINT]
            user32.WindowFromPoint.restype = wintypes.HWND
            user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
            user32.GetAncestor.restype = wintypes.HWND
            user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
            user32.GetWindowTextLengthW.restype = ctypes.c_int
            user32.GetWindowTextW.argtypes = [
                wintypes.HWND, wintypes.LPWSTR, ctypes.c_int,
            ]
            user32.GetWindowTextW.restype = ctypes.c_int
            user32.GetClassNameW.argtypes = [
                wintypes.HWND, wintypes.LPWSTR, ctypes.c_int,
            ]
            user32.GetClassNameW.restype = ctypes.c_int
            user32.GetWindowRect.argtypes = [
                wintypes.HWND, ctypes.POINTER(wintypes.RECT),
            ]
            user32.GetWindowRect.restype = wintypes.BOOL

            hwnd = user32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
            if not hwnd:
                return None

            # GA_ROOT=2：子控件句柄提升为所属顶层窗口。
            root_hwnd = user32.GetAncestor(hwnd, 2) or hwnd
            title_len = max(0, user32.GetWindowTextLengthW(root_hwnd))
            title_buf = ctypes.create_unicode_buffer(title_len + 1)
            user32.GetWindowTextW(root_hwnd, title_buf, len(title_buf))

            class_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(root_hwnd, class_buf, len(class_buf))

            rect = wintypes.RECT()
            if not user32.GetWindowRect(root_hwnd, ctypes.byref(rect)):
                rect = None

            return {
                "hwnd": root_hwnd,
                "title": title_buf.value,
                "class_name": class_buf.value,
                "rect": rect,
            }
        except Exception:
            return None

    @staticmethod
    @_with_uiautomation_initialized
    def capture_at_cursor():
        """获取当前鼠标位置的控件信息。

        关键设计: 无论控件识别是否成功，都保证记录:
        - 所属窗口(标题+类名) → 回放时能找到窗口
        - 鼠标位置的窗口内相对坐标 → 自绘界面的点击兜底
        - 鼠标绝对坐标 → 最后防线
        """
        # 坐标是最终兜底，必须在任何可能失败的 UIA 调用之前记录。
        pos = pyautogui.position()
        control = None
        window = None
        try:
            control = auto.ControlFromCursor()
            if control is not None:
                window = ElementCapture._find_top_window(control)
        except Exception:
            # 管理员窗口、部分自绘应用或 UIA 服务异常时会走 Win32 兜底。
            pass

        native = ElementCapture._native_window_at(pos.x, pos.y)
        win_title = ElementCapture._safe_control_value(window, "Name")
        win_class = ElementCapture._safe_control_value(window, "ClassName")
        if native:
            win_title = win_title or native["title"]
            win_class = win_class or native["class_name"]

        # 鼠标位置相对窗口左上角的偏移 —— 自绘界面回放点击的主力坐标。
        # 注意用鼠标实际位置而非控件中心: 自绘界面拿到的"控件"往往就是
        # 整个窗口，控件中心 ≠ 用户想点的地方。
        rel_x = rel_y = None
        if window is not None:
            try:
                wrect = window.BoundingRectangle
                rel_x = pos.x - wrect.left
                rel_y = pos.y - wrect.top
            except Exception:
                pass
        if rel_x is None and native and native["rect"] is not None:
            rel_x = pos.x - native["rect"].left
            rel_y = pos.y - native["rect"].top

        # 微信/Qt/Electron 常把“整个窗口”作为鼠标下控件返回。窗口名不是
        # 按钮选择器；保留它会让回放误点窗口中心，必须强制走相对位置。
        selector_control = control
        try:
            if control.ControlType == auto.ControlType.WindowControl:
                selector_control = None
        except Exception:
            pass

        return {
            "window_title": win_title,
            "win_class": win_class,
            "control_type": ElementCapture._safe_control_value(
                control, "ControlTypeName", "UnknownControl"
            ),
            "name": ElementCapture._safe_control_value(selector_control, "Name"),
            "automation_id": ElementCapture._safe_control_value(
                selector_control, "AutomationId"
            ),
            "class_name": ElementCapture._safe_control_value(
                selector_control, "ClassName"
            ),
            "rel_x": rel_x,
            "rel_y": rel_y,
            "x": pos.x,
            "y": pos.y,
        }

    @staticmethod
    def _find_top_window(control):
        """找到控件所属的顶层窗口。

        v1.6 修复: 自绘界面(微信/Qt/Electron)上 ControlFromCursor 返回的
        往往就是窗口本身 —— 旧版只检查父级链导致返回 None，
        捕获出的步骤 window_title 为空、无兜底坐标，回放必然失败。
        """
        # 1) 控件自身就是窗口
        try:
            if control.ControlType == auto.ControlType.WindowControl:
                return control
        except Exception:
            pass

        # 2) 沿父级链向上找
        current = control
        for _ in range(30):
            try:
                parent = current.GetParentControl()
            except Exception:
                break
            if parent is None:
                break
            if parent.ControlType == auto.ControlType.WindowControl:
                return parent
            current = parent

        # 3) 按进程 ID 在顶层窗口中兜底查找
        try:
            pid = control.ProcessId
            for child in auto.GetRootControl().GetChildren():
                if (child.ProcessId == pid
                        and child.ControlType == auto.ControlType.WindowControl):
                    return child
        except Exception:
            pass
        return None

    @staticmethod
    @_with_uiautomation_initialized
    def capture_cursor_pos():
        """获取当前鼠标坐标（自动绑定所在窗口，记录类名）"""
        pos = pyautogui.position()
        try:
            control = auto.ControlFromCursor()
            if control:
                window = ElementCapture._find_top_window(control)
                if window:
                    win_rect = window.BoundingRectangle
                    return {
                        "window_title": window.Name,
                        "win_class": window.ClassName,
                        "rel_x": pos.x - win_rect.left,
                        "rel_y": pos.y - win_rect.top,
                        "x": pos.x,
                        "y": pos.y,
                    }
        except Exception:
            pass
        native = ElementCapture._native_window_at(pos.x, pos.y)
        if native and native["rect"] is not None:
            rect = native["rect"]
            return {
                "window_title": native["title"],
                "win_class": native["class_name"],
                "rel_x": pos.x - rect.left,
                "rel_y": pos.y - rect.top,
                "x": pos.x,
                "y": pos.y,
            }
        return {"x": pos.x, "y": pos.y}

    @staticmethod
    @_with_uiautomation_initialized
    def list_windows():
        """列出所有可见顶层窗口标题"""
        result = []
        root = auto.GetRootControl()
        for child in root.GetChildren():
            name = child.Name
            if name and name.strip():
                result.append(name)
        return sorted(set(result))


# ==================== 流程执行器 ====================

class FlowRunner:
    """按顺序执行自动化步骤"""

    def __init__(self, on_step=None, on_done=None, on_error=None):
        self.on_step = on_step
        self.on_done = on_done
        self.on_error = on_error
        self._stop = False

    def stop(self):
        self._stop = True

    @_with_uiautomation_initialized
    def run(self, steps):
        self._stop = False
        for i, step in enumerate(steps):
            if self._stop:
                break
            if self.on_step:
                self.on_step(i, step)
            try:
                self._execute(step)
                time.sleep(0.3)
            except Exception as e:
                if self.on_error:
                    self.on_error(i, step, str(e))
                return
        if self.on_done:
            self.on_done()

    def _execute(self, step):
        t, p = step.type, step.params

        if t == "click":
            self._do_click(p)
        elif t == "click_pos":
            self._do_click_pos(p)
        elif t == "input_text":
            self._do_input(p)
        elif t == "hotkey":
            keys = [k.strip().lower() for k in p.get("keys", "").split("+") if k.strip()]
            pyautogui.hotkey(*keys)
        elif t == "wait":
            time.sleep(float(p.get("seconds", 1)))
        elif t == "switch_window":
            self._activate_window(p.get("window_title", ""))
        elif t == "open_url":
            webbrowser.open(p.get("url", ""))

    # ---------- 窗口查找: 标题子串优先，类名兜底 ----------

    def _find_window(self, title, win_class=""):
        """按标题(子串匹配)找窗口，失败则按类名找。

        v1.6 新增: 窗口标题是动态的(浏览器换页面、微信多状态)，
        类名是稳定的(Chrome_WidgetWin_1 / Qt51514QWindowIcon 等)，
        标题失配时用类名兜底找回窗口。
        """
        if title:
            win = auto.WindowControl(searchDepth=1, SubName=title)
            if win.Exists(2):
                return win

        if win_class:
            best, best_score = None, -1
            try:
                for child in auto.GetRootControl().GetChildren():
                    if (child.ClassName == win_class
                            and child.ControlType == auto.ControlType.WindowControl):
                        # 同类名多窗口时，选标题与原标题共同前缀最长的
                        score = 0
                        if title:
                            for a, b in zip(child.Name or "", title):
                                if a != b:
                                    break
                                score += 1
                        if score > best_score:
                            best, best_score = child, score
            except Exception:
                pass
            if best is not None:
                return best
        return None

    def _activate_window(self, title, win_class=""):
        """激活窗口并返回窗口控件"""
        win = self._find_window(title, win_class)
        if win is None:
            raise RuntimeError(f"找不到窗口: {title or win_class}")
        win.SetActive()
        time.sleep(0.5)
        return win

    # ---------- 智能点击: 元素匹配 → 窗口内位置 → 绝对坐标 ----------

    def _do_click(self, p):
        title = p.get("window_title", "")
        win_class = p.get("win_class", "")
        rel_x, rel_y = p.get("rel_x"), p.get("rel_y")
        name = p.get("name", "")
        aid = p.get("automation_id", "")

        # 激活目标窗口（标题失配时自动用类名兜底）
        win = None
        if title or win_class:
            win = self._activate_window(title, win_class)

        # 策略1: 按控件名称/ID 匹配（原生应用有效；自绘界面名称为空自动跳过）
        if win is not None and (name or aid):
            control = self._find_control_in(win, name, aid)
            if control is not None:
                try:
                    control.Click()
                    return
                except Exception:
                    pass  # 匹配到但点击失败，走兜底

        # 策略2: 按窗口内相对位置点击（自绘界面主力方案，窗口挪动不影响）
        if win is not None and rel_x is not None and rel_y is not None:
            try:
                win.Click(x=int(rel_x), y=int(rel_y))
                return
            except Exception:
                pass

        # 策略3: 绝对坐标（最后防线）
        if p.get("x") is not None:
            pyautogui.click(int(p["x"]), int(p["y"]))
            return

        raise RuntimeError(
            f"点击失败: 控件 [{name or aid or '?'}] 未找到"
            + ("，且无备用坐标" if rel_x is None else "，备用位置点击也失败")
        )

    def _find_control_in(self, win, name, aid):
        """在窗口内快速查找控件（不做深度递归，找不到就走位置兜底）"""
        try:
            if aid:
                c = win.Control(AutomationId=aid)
                if c.Exists(0.5):
                    return c
            if name:
                c = win.Control(Name=name)
                if c.Exists(0.5):
                    return c
                c = win.Control(SubName=name)
                if c.Exists(0.5):
                    return c
        except Exception:
            pass
        return None

    # ---------- 坐标点击: 优先窗口内相对坐标 ----------

    def _do_click_pos(self, p):
        title = p.get("window_title", "")
        win_class = p.get("win_class", "")
        rel_x, rel_y = p.get("rel_x"), p.get("rel_y")

        if (title or win_class) and rel_x is not None and rel_y is not None:
            # 窗口内相对坐标: 窗口移动、标题变化后依然点得准
            win = self._activate_window(title, win_class)
            try:
                win.Click(x=int(rel_x), y=int(rel_y))
                return
            except Exception:
                rect = win.BoundingRectangle
                pyautogui.click(rect.left + int(rel_x), rect.top + int(rel_y))
                return

        # 绝对坐标（v1.0 兼容或捕获时未识别到窗口）
        pyautogui.click(int(p.get("x", 0)), int(p.get("y", 0)))

    # ---------- 其他操作 ----------

    def _do_input(self, p):
        text = p.get("text", "")
        win_title = p.get("window_title", "")
        win_class = p.get("win_class", "")
        if win_title or win_class:
            self._activate_window(win_title, win_class)
        pyperclip.copy(text)
        time.sleep(0.2)
        pyautogui.hotkey("ctrl", "v")


# ==================== 流程存取 ====================

def save_flow(steps, name, filepath):
    data = {
        "name": name,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "steps": [s.to_dict() for s in steps],
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_flow(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    steps = [Step.from_dict(s) for s in data.get("steps", [])]
    return data.get("name", "未命名"), steps
