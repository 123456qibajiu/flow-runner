"""
RPA 引擎 - 负责控件识别、步骤执行、流程存取
"""

import time
import json
import webbrowser

import uiautomation as auto
import pyautogui
import pyperclip


# ==================== 步骤类型定义 ====================

STEP_TYPES = {
    "click": "点击控件",
    "click_pos": "坐标点击",
    "input_text": "输入文字",
    "hotkey": "快捷键",
    "wait": "等待",
    "switch_window": "切换窗口",
    "open_url": "打开网址",
}

PARAM_LABELS = {
    "window_title": "窗口标题",
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
            name = p.get("name", "") or p.get("automation_id", "?")
            win = p.get("window_title", "?")
            return f'点击 [{name}] @ {win}'
        elif t == "click_pos":
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
    def capture_at_cursor():
        """获取当前鼠标位置的控件信息"""
        try:
            control = auto.ControlFromCursor()
        except Exception:
            return None
        if control is None:
            return None

        window = ElementCapture._find_top_window(control)
        return {
            "window_title": window.Name if window else "",
            "control_type": control.ControlTypeName,
            "name": control.Name or "",
            "automation_id": control.AutomationId or "",
            "class_name": control.ClassName or "",
        }

    @staticmethod
    def _find_top_window(control):
        """向上遍历找到顶层窗口控件"""
        current = control
        for _ in range(30):
            parent = current.GetParentControl()
            if parent is None:
                break
            if parent.ControlType == auto.ControlType.WindowControl:
                return parent
            current = parent
        return None

    @staticmethod
    def capture_cursor_pos():
        """获取当前鼠标坐标"""
        pos = pyautogui.position()
        return {"x": pos.x, "y": pos.y}

    @staticmethod
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
            pyautogui.click(int(p.get("x", 0)), int(p.get("y", 0)))
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

    def _do_click(self, p):
        title = p.get("window_title", "")
        name = p.get("name", "")
        ctype = p.get("control_type", "")
        aid = p.get("automation_id", "")

        if title:
            self._activate_window(title)

        control = self._find_control(title, ctype, name, aid)
        if control is None:
            raise RuntimeError(f"找不到控件 [{name or aid}] @ {title}")
        control.Click()

    def _activate_window(self, title):
        win = auto.WindowControl(searchDepth=1, SubName=title)
        if not win.Exists(3):
            raise RuntimeError(f"找不到窗口: {title}")
        win.SetActive()
        time.sleep(0.5)

    def _find_control(self, window_title, ctype, name, aid):
        win = auto.WindowControl(searchDepth=1, SubName=window_title)
        if not win.Exists(2):
            return None

        # 策略1: AutomationId 精确匹配
        if aid:
            c = win.Control(AutomationId=aid)
            if c.Exists(1):
                return c

        # 策略2: 名称精确匹配
        if name:
            c = win.Control(Name=name)
            if c.Exists(1):
                return c
            c = win.Control(SubName=name)
            if c.Exists(1):
                return c

        # 策略3: 深度递归搜索
        return self._deep_find(win, ctype, name, aid)

    def _deep_find(self, parent, ctype, name, aid, depth=0):
        if depth > 15:
            return None
        try:
            children = parent.GetChildren()
        except Exception:
            return None
        for child in children:
            try:
                if aid and child.AutomationId == aid:
                    return child
                if name and child.Name == name:
                    return child
            except Exception:
                pass
            r = self._deep_find(child, ctype, name, aid, depth + 1)
            if r:
                return r
        return None

    def _do_input(self, p):
        text = p.get("text", "")
        win_title = p.get("window_title", "")
        if win_title:
            self._activate_window(win_title)
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
