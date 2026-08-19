"""
diagnose.py — 控件识别链路诊断脚本（真实窗口实测）

测试对象:
  记事本   = 原生 Win32 控件（UIA 应该能识别名称）
  VS Code  = Electron 自绘界面（与微信/浏览器同类，UIA 通常看不到名称）

输出每项 PASS/FAIL 作为证据。
"""
import subprocess
import sys
import time
import ctypes
import threading

import uiautomation as auto
import pyautogui

sys.path.insert(0, '.')
from engine import ElementCapture, FlowRunner, Step
from hotkeys import wait_for_new_f9_press

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def section(title):
    print("\n" + "=" * 62)
    print(f" {title}")
    print("=" * 62)


def run_step_in_thread(step, timeout=5):
    """按 GUI 的真实方式在后台线程运行一步，并返回 (成功, 详情)。"""
    result = {"done": False, "error": ""}
    runner = FlowRunner(
        on_done=lambda: result.update(done=True),
        on_error=lambda _i, _s, err: result.update(error=err),
    )
    worker = threading.Thread(target=runner.run, args=([step],), daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        return False, "后台线程执行超时"
    if result["error"]:
        return False, result["error"]
    return result["done"], "后台线程 COM 初始化与回放完成"


# 保存现场（鼠标位置、剪贴板），测试结束后恢复
old_pos = pyautogui.position()
try:
    import pyperclip
    old_clip = pyperclip.paste()
except Exception:
    old_clip = None

try:
    # ---------- 阶段 0: 顶层窗口枚举 ----------
    section("阶段 0: 顶层窗口枚举")
    root = auto.GetRootControl()
    wins = [w for w in root.GetChildren() if (w.Name or "").strip()]
    check("枚举顶层窗口", len(wins) > 0, f"共 {len(wins)} 个")
    for w in wins:
        print(f"      · '{w.Name[:46]}'  class={w.ClassName}")

    vscode = next((w for w in wins if "Visual Studio Code" in w.Name), None)
    # 自绘界面样本优先级: 微信(用户实际目标) > VS Code > 任意 Electron 窗口
    selfdraw = next((w for w in wins if w.Name == "微信"), None) or vscode
    if selfdraw is None:
        selfdraw = next((w for w in wins
                         if w.ClassName == "Chrome_WidgetWin_1"
                         and "WorkBuddy" not in w.Name), None)
    check("自绘界面样本可用", selfdraw is not None,
          f"'{selfdraw.Name[:40]}' class={selfdraw.ClassName}" if selfdraw else "跳过该阶段")

    # ---------- 阶段 1: 原生应用(记事本)全链路 ----------
    section("阶段 1: 原生应用全链路（记事本）")

    proc = subprocess.Popen(["notepad.exe"])
    np_win = None
    deadline = time.time() + 6
    while time.time() < deadline:
        for w in auto.GetRootControl().GetChildren():
            title = (w.Name or "").strip()
            if (w.ClassName == "Notepad"
                    and not title.startswith("*")
                    and ("无标题" in title or "Untitled" in title)):
                np_win = w
                break
        if np_win is not None:
            break
        time.sleep(0.3)

    check("启动并找到记事本窗口", np_win is not None,
          f"title='{np_win.Name}' class={np_win.ClassName}" if np_win else "超时未找到")

    if np_win is not None:
        try:
            np_win.SetActive()
            time.sleep(0.6)

            edit = np_win.EditControl()
            if not edit.Exists(1):
                edit = np_win.Control(ControlType=auto.ControlType.DocumentControl)
            edit_found = edit.Exists(0.5)
            check("识别记事本编辑控件", edit_found,
                  f"name='{edit.Name}' type={edit.ControlTypeName}" if edit_found else "未找到")

            # 目标点：编辑区中心（找不到编辑区就用窗口中心）
            if edit_found:
                rect = edit.BoundingRectangle
            else:
                rect = np_win.BoundingRectangle
            cx, cy = (rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2

            # --- DPI 坐标一致性 ---
            pyautogui.moveTo(cx, cy)
            time.sleep(0.25)
            pos = pyautogui.position()
            dpi_ok = abs(pos.x - cx) <= 2 and abs(pos.y - cy) <= 2
            check("DPI 坐标一致性(GetCursorPos vs UIA矩形)", dpi_ok,
                  f"目标({cx},{cy}) 实际({pos.x},{pos.y})"
                  + ("" if dpi_ok else " ← 高分屏缩放导致坐标错位!"))

            # --- 捕获链路（等价于按 F9 后的 capture_at_cursor）---
            info = ElementCapture.capture_at_cursor()
            check("捕获返回完整信息", bool(info and info.get("window_title")),
                  f"name='{info.get('name', '')}' win='{info.get('window_title', '')}' "
                  f"rel=({info.get('rel_x')},{info.get('rel_y')})" if info else "返回 None")
            if info:
                check("捕获记录了窗口内相对位置", info.get("rel_x") is not None,
                      f"rel=({info.get('rel_x')},{info.get('rel_y')})")

            # --- 回放: 元素匹配路径 + 输入落点验证 ---
            if info:
                try:
                    ok_thread, thread_detail = run_step_in_thread(Step("click", **info))
                    if not ok_thread:
                        raise RuntimeError(thread_detail)
                    time.sleep(0.4)
                    import pyperclip
                    pyperclip.copy("FLOW_RUNNER_V18_PROBE")
                    pyautogui.hotkey("ctrl", "v")
                    time.sleep(0.6)
                    focused = auto.GetFocusedControl()
                    text = ""
                    try:
                        text = focused.GetValuePattern().Value
                    except Exception:
                        try:
                            text = focused.GetLegacyIAccessiblePattern().Value
                        except Exception:
                            pass
                    check("后台线程回放(元素路径)+输入落点", "FLOW_RUNNER_V18_PROBE" in (text or ""),
                          f"{thread_detail}; 回读文本: '{(text or '')[:40]}'")
                except Exception as e:
                    check("后台线程回放(元素路径)+输入落点", False, repr(e))

                # --- 回放: 模拟自绘界面（名称全空）→ 位置兜底路径 ---
                fb = dict(info)
                fb["name"] = ""
                fb["automation_id"] = ""
                try:
                    ok_thread, thread_detail = run_step_in_thread(Step("click", **fb))
                    if not ok_thread:
                        raise RuntimeError(thread_detail)
                    time.sleep(0.3)
                    focused = auto.GetFocusedControl()
                    ok_fb = focused.ControlTypeName in ("EditControl", "DocumentControl")
                    check("后台线程回放(位置兜底路径)", ok_fb,
                          f"{thread_detail}; 焦点控件: {focused.ControlTypeName} '{focused.Name}'")
                except Exception as e:
                    check("后台线程回放(位置兜底路径)", False, repr(e))
        finally:
            # 只清理本次测试的空白标签页，不终止可能承载用户其他标签的进程。
            try:
                np_win.SetActive()
                pyautogui.hotkey("ctrl", "a")
                pyautogui.press("backspace")
                time.sleep(0.2)
                np_win.GetWindowPattern().Close()
            except Exception:
                pass

    # ---------- 阶段 2: 自绘界面(微信 / Electron) ----------
    section(f"阶段 2: 自绘界面（{selfdraw.Name[:30] if selfdraw else '无样本'}）")

    if selfdraw is not None:
        try:
            selfdraw.SetActive()
            time.sleep(0.6)
            rect = selfdraw.BoundingRectangle
            cx = (rect.left + rect.right) // 2
            cy = (rect.top + rect.bottom) // 2
            pyautogui.moveTo(cx, cy)
            time.sleep(0.25)
            info = ElementCapture.capture_at_cursor()
            if info:
                no_name = not (info["name"] or info["automation_id"])
                print(f"      捕获结果: name='{info['name']}' aid='{info['automation_id']}' "
                      f"win='{info['window_title']}' rel=({info['rel_x']},{info['rel_y']})")
                check("自绘界面: 捕获到窗口与相对位置",
                      bool(info["window_title"]) and info["rel_x"] is not None,
                      "（名称为空属正常，需依赖位置兜底）" if no_name else "")
                check("自绘界面: 捕获到窗口类名(标题失配兜底)",
                      bool(info.get("win_class")), f"class={info.get('win_class')}")
            else:
                check("自绘界面: 捕获到窗口与相对位置", False, "capture 返回 None")

            # 标题失配场景（模拟浏览器标题变化/微信切换聊天）
            w = auto.WindowControl(searchDepth=1, SubName="此标题肯定不存在xyz")
            check("标题失配时(旧逻辑)找不到窗口", not w.Exists(1),
                  "→ 印证: 窗口标题变化会导致回放直接失败")

            # 类名兜底: 标题变化后仍能找回窗口
            runner = FlowRunner()
            if hasattr(runner, "_find_window"):
                w2 = runner._find_window("此标题肯定不存在xyz", selfdraw.ClassName)
                check("类名兜底找回窗口", w2 is not None,
                      f"按 class={selfdraw.ClassName} 找到 '{w2.Name[:40]}'" if w2 else "未找到")
            else:
                check("类名兜底找回窗口", False, "当前版本无 _find_window")
        finally:
            wb = auto.WindowControl(searchDepth=1, SubName="WorkBuddy")
            if wb.Exists(1):
                wb.SetActive()

    # ---------- 阶段 3: F9 按键轮询检测 ----------
    section("阶段 3: F9 按键轮询检测")

    def _press_f9():
        time.sleep(0.4)
        pyautogui.keyDown("f9")
        time.sleep(0.08)
        pyautogui.keyUp("f9")

    # 先释放可能由上次诊断残留的合成按键，再等待一次全新的按下。
    pyautogui.keyUp("f9")
    time.sleep(0.1)
    threading.Thread(target=_press_f9, daemon=True).start()
    start = time.time()
    detected = wait_for_new_f9_press(
        cancelled=lambda: time.time() - start >= 3,
        poll_interval=0.01,
    )
    check("F9 只响应释放后的新按下动作", detected, f"耗时 {time.time() - start:.2f}s")

finally:
    # 恢复现场
    pyautogui.moveTo(old_pos.x, old_pos.y)
    if old_clip is not None:
        try:
            import pyperclip
            pyperclip.copy(old_clip)
        except Exception:
            pass

# ---------- 汇总 ----------
section("汇总")
total = len(RESULTS)
passed = sum(1 for _, ok, _ in RESULTS if ok)
print(f"  通过 {passed}/{total}")
for name, ok, detail in RESULTS:
    if not ok:
        print(f"  ✗ 失败项 — {name}: {detail}")
