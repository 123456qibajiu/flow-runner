"""
RPA 引擎 - 负责控件识别、步骤执行、流程存取

v1.5: 点击可靠性大幅增强
- 智能点击带回退：先按控件名/ID匹配，失败后按「窗口内相对位置」点击
- 坐标点击自动绑定窗口：窗口挪了位置，点击依然准确
"""

import time
import json
import webbrowser

import uiautomation as auto
import pyautogui
import pyperclip


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
                if p.get("rel_x") is not None:
                    return f'点击 [{name}] @ {win} (含位置兜底)'
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
    def capture_at_cursor():
        """获取当前鼠标位置的控件信息（含窗口内相对位置，用于兜底点击）"""
        try:
            control = auto.ControlFromCursor()
        except Exception:
            return None
        if control is None:
            return None

        window = ElementCapture._find_top_window(control)
        win_title = window.Name if window else ""

        # 计算控件中心相对窗口左上角的位置 —— 这是回放时的兜底坐标
        rel_x = rel_y = None
        if window is not None:
            try:
                rect = control.BoundingRectangle
                win_rect = window.BoundingRectangle
                cx = (rect.left + rect.right) // 2
                cy = (rect.top + rect.bottom) // 2
                rel_x = cx - win_rect.left
                rel_y = cy - win_rect.top
            except Exception:
                pass

        return {
            "window_title": win_title,
            "control_type": control.ControlTypeName,
            "name": control.Name or "",
            "automation_id": control.AutomationId or "",
            "class_name": control.ClassName or "",
            "rel_x": rel_x,
            "rel_y": rel_y,
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
        """获取当前鼠标坐标。若能识别鼠标所在窗口，则记录窗口内相对坐标（窗口移动后依然有效）"""
        pos = pyautogui.position()

        try:
            control = auto.ControlFromCursor()
            if control:
                window = ElementCapture._find_top_window(control)
                if window:
                    win_rect = window.BoundingRectangle
                    return {
                        "window_title": window.Name,
                        "rel_x": pos.x - win_rect.left,
                        "rel_y": pos.y - win_rect.top,
                    }
        except Exception:
            pass

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

    # ---------- 智能点击：控件匹配 → 窗口内位置兜底 ----------

    def _do_click(self, p):
        title = p.get("window_title", "")
        rel_x, rel_y = p.get("rel_x"), p.get("rel_y")
        name = p.get("name", "")
        aid = p.get("automation_id", "")

        # 激活目标窗口
        win = None
        if title:
            win = self._activate_window(title)

        # 策略1: 按控件名称/ID 快速匹配（微信/浏览器等自绘控件通常匹配不到）
        if win is not None and (name or aid):
            control = self._find_control_in(win, name, aid)
            if control is not None:
                try:
                    control.Click()
                    return
                except Exception:
                    pass  # 匹配到了但点击失败，走兜底

        # 策略2: 按窗口内相对位置点击（兜底，窗口挪动不影响准确性）
        if win is not None and rel_x is not None and rel_y is not None:
            try:
                win.Click(x=int(rel_x), y=int(rel_y))
                return
            except Exception:
                pass

        # 策略3: 旧版绝对坐标（兼容 v1.0 流程文件）
        if p.get("x") is not None:
            pyautogui.click(int(p["x"]), int(p["y"]))
            return

        raise RuntimeError(
            f"点击失败: 控件 [{name or aid or '?'}] 未找到"
            + ("，且无窗口内备用位置" if rel_x is None else "，备用位置点击也失败")
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

    # ---------- 坐标点击：优先窗口内相对坐标 ----------

    def _do_click_pos(self, p):
        title = p.get("window_title", "")
        rel_x, rel_y = p.get("rel_x"), p.get("rel_y")

        if title and rel_x is not None and rel_y is not None:
            # 窗口内相对坐标：窗口移动后依然点得准
            win = self._activate_window(title)
            try:
                win.Click(x=int(rel_x), y=int(rel_y))
                return
            except Exception:
                # uiautomation 点击失败，退回 pyautogui 绝对坐标
                rect = win.BoundingRectangle
                pyautogui.click(rect.left + int(rel_x), rect.top + int(rel_y))
                return

        # 绝对坐标（v1.0 兼容或捕获时未识别到窗口）
        pyautogui.click(int(p.get("x", 0)), int(p.get("y", 0)))

    # ---------- 其他操作 ----------

    def _activate_window(self, title):
        """激活窗口并返回窗口控件"""
        win = auto.WindowControl(searchDepth=1, SubName=title)
        if not win.Exists(3):
            raise RuntimeError(f"找不到窗口: {title}")
        win.SetActive()
        time.sleep(0.5)
        return win

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
