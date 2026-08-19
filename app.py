"""
RPA 工具 GUI - 流程录制、编辑、运行

v1.5: 新增单步测试按钮；捕获反馈增强
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import threading
import time
import ctypes
import os

from engine import Step, STEP_TYPES, PARAM_LABELS, ElementCapture, FlowRunner, save_flow, load_flow


def _is_f9_pressed():
    """检测 F9 键是否被按下 (无需 keyboard 库)"""
    return ctypes.windll.user32.GetAsyncKeyState(0x78) & 0x8000


class RPAApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("流程自动化工具 v1.5")
        self.root.geometry("780x700")
        self.root.minsize(680, 580)

        # 设置默认字体
        self.root.option_add("*Font", ("Microsoft YaHei UI", 10))

        self.steps = []
        self.runner = None
        self._capture_stop = False
        self._build_ui()
        self._refresh_list()

    # ==================== UI 构建 ====================

    def _build_ui(self):
        # --- 工具栏 ---
        tb = ttk.Frame(self.root)
        tb.pack(fill=tk.X, padx=10, pady=(10, 5))

        ttk.Button(tb, text="新建", command=self._new_flow).pack(side=tk.LEFT, padx=2)
        ttk.Button(tb, text="打开", command=self._open_flow).pack(side=tk.LEFT, padx=2)
        ttk.Button(tb, text="保存", command=self._save_flow).pack(side=tk.LEFT, padx=2)
        ttk.Separator(tb, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        self.run_btn = ttk.Button(tb, text="▶  运行", command=self._run_flow)
        self.run_btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(tb, text="■  停止", command=self._stop_flow).pack(side=tk.LEFT, padx=2)
        ttk.Button(tb, text="▶ 测试选中", command=self._test_step).pack(side=tk.LEFT, padx=2)

        # --- 流程名 ---
        nf = ttk.Frame(self.root)
        nf.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(nf, text="流程名称:").pack(side=tk.LEFT)
        self.name_var = tk.StringVar(value="新流程")
        ttk.Entry(nf, textvariable=self.name_var, width=40).pack(side=tk.LEFT, padx=5)

        # --- 步骤列表 ---
        lf = ttk.LabelFrame(self.root, text=" 步骤列表（双击可编辑）", padding=5)
        lf.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.listbox = tk.Listbox(
            lf, font=("Microsoft YaHei UI", 10),
            activestyle="dotbox", selectmode=tk.SINGLE
        )
        sb = ttk.Scrollbar(lf, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.config(yscrollcommand=sb.set)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.bind("<Double-Button-1>", lambda e: self._edit_step())

        # --- 步骤操作按钮 ---
        bf = ttk.Frame(self.root)
        bf.pack(fill=tk.X, padx=10, pady=5)

        r1 = ttk.Frame(bf)
        r1.pack(fill=tk.X, pady=2)
        ttk.Button(r1, text="🎯 捕获点击", command=self._capture_click).pack(side=tk.LEFT, padx=2)
        ttk.Button(r1, text="📍 坐标点击", command=self._capture_pos).pack(side=tk.LEFT, padx=2)
        ttk.Button(r1, text="✎ 编辑", command=self._edit_step).pack(side=tk.LEFT, padx=2)
        ttk.Button(r1, text="✕ 删除", command=self._delete_step).pack(side=tk.LEFT, padx=2)
        ttk.Button(r1, text="↑ 上移", command=lambda: self._move(-1)).pack(side=tk.LEFT, padx=2)
        ttk.Button(r1, text="↓ 下移", command=lambda: self._move(1)).pack(side=tk.LEFT, padx=2)

        r2 = ttk.Frame(bf)
        r2.pack(fill=tk.X, pady=2)
        ttk.Label(r2, text="添加:").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(r2, text="⏱ 等待", command=lambda: self._add("wait")).pack(side=tk.LEFT, padx=2)
        ttk.Button(r2, text="⌨ 输入文字", command=lambda: self._add("input_text")).pack(side=tk.LEFT, padx=2)
        ttk.Button(r2, text="🔗 快捷键", command=lambda: self._add("hotkey")).pack(side=tk.LEFT, padx=2)
        ttk.Button(r2, text="🪟 切换窗口", command=lambda: self._add("switch_window")).pack(side=tk.LEFT, padx=2)
        ttk.Button(r2, text="🌐 打开网址", command=lambda: self._add("open_url")).pack(side=tk.LEFT, padx=2)

        # --- 状态栏 ---
        self.status = tk.StringVar(
            value="就绪  |  捕获点击会同时记录位置兜底，即使控件识别不到也能点中"
        )
        ttk.Label(
            self.root, textvariable=self.status,
            relief=tk.SUNKEN, anchor=tk.W, padding=(5, 3)
        ).pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=(0, 8))

    # ==================== 流程操作 ====================

    def _new_flow(self):
        if self.steps and not messagebox.askyesno("确认", "当前流程未保存，确定新建？"):
            return
        self.steps.clear()
        self.name_var.set("新流程")
        self._refresh_list()
        self.status.set("已创建新流程")

    def _open_flow(self):
        fp = filedialog.askopenfilename(
            filetypes=[("流程文件", "*.json")], defaultextension=".json"
        )
        if not fp:
            return
        try:
            name, self.steps = load_flow(fp)
            self.name_var.set(name)
            self._refresh_list()
            self.status.set(f"已加载: {os.path.basename(fp)}")
        except Exception as e:
            messagebox.showerror("错误", f"加载失败: {e}")

    def _save_flow(self):
        fp = filedialog.asksaveasfilename(
            filetypes=[("流程文件", "*.json")],
            defaultextension=".json",
            initialfile=f"{self.name_var.get()}.json",
        )
        if not fp:
            return
        try:
            save_flow(self.steps, self.name_var.get(), fp)
            self.status.set(f"已保存: {os.path.basename(fp)}")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {e}")

    # ==================== 运行 ====================

    def _run_flow(self):
        if not self.steps:
            messagebox.showwarning("提示", "请先添加步骤")
            return
        self.run_btn.config(state=tk.DISABLED)
        self.runner = FlowRunner(
            on_step=lambda i, s: self.root.after(0, self._on_step, i, s),
            on_done=lambda: self.root.after(0, self._on_done),
            on_error=lambda i, s, e: self.root.after(0, self._on_error, i, s, e),
        )
        threading.Thread(target=self.runner.run, args=(list(self.steps),), daemon=True).start()

    def _stop_flow(self):
        if self.runner:
            self.runner.stop()

    def _test_step(self):
        """只运行选中的那一个步骤，方便调试"""
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showinfo("提示", "请先选中一个步骤")
            return
        idx = sel[0]
        step = self.steps[idx]
        self.status.set(f"🧪 测试步骤 {idx+1}: {step.describe()}")

        def run_single():
            runner = FlowRunner(
                on_done=lambda: self.root.after(
                    0, lambda: self.status.set(f"✅ 步骤 {idx+1} 测试成功")
                ),
                on_error=lambda i, s, e: self.root.after(
                    0, lambda: self.status.set(f"❌ 步骤 {idx+1} 测试失败: {e}")
                ),
            )
            runner.run([step])

        threading.Thread(target=run_single, daemon=True).start()

    def _on_step(self, i, step):
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(i)
        self.listbox.see(i)
        self.status.set(f"执行 {i+1}/{len(self.steps)}: {step.describe()}")

    def _on_done(self):
        self.run_btn.config(state=tk.NORMAL)
        self.listbox.selection_clear(0, tk.END)
        self.status.set("✅ 全部执行完成")

    def _on_error(self, i, step, err):
        self.run_btn.config(state=tk.NORMAL)
        self.status.set(f"❌ 步骤 {i+1} 出错: {err}")
        messagebox.showerror("执行错误", f"步骤 {i+1}: {step.describe()}\n\n{err}")

    # ==================== 捕获 ====================

    def _capture_click(self):
        self.status.set("⏳ 3 秒后开始捕获…把鼠标移到目标控件上，按 F9")
        self._capture_stop = False
        threading.Thread(target=self._capture_thread, daemon=True).start()

    def _capture_thread(self):
        time.sleep(1)
        self.root.after(0, self.root.iconify)
        time.sleep(2)

        self.root.after(0, lambda: self.status.set("🎯 等待按 F9 …"))

        while not self._capture_stop:
            if _is_f9_pressed():
                time.sleep(0.15)
                break
            time.sleep(0.05)

        if self._capture_stop:
            self.root.after(0, self.root.deiconify)
            return

        info = ElementCapture.capture_at_cursor()
        self.root.after(0, self.root.deiconify)

        if info:
            self.steps.append(Step("click", **info))
            self.root.after(0, self._refresh_list)

            label = info["name"] or info["automation_id"] or info["control_type"]
            if info["name"] or info["automation_id"]:
                msg = f"✅ 已捕获: [{label}] @ {info['window_title']}（含位置兜底）"
            else:
                msg = (f"✅ 已捕获位置 ({info['rel_x']},{info['rel_y']}) @ "
                       f"{info['window_title']}（控件无名，将按位置点击）")
            self.root.after(0, lambda: self.status.set(msg))
        else:
            self.root.after(0, lambda: self.status.set("❌ 未捕获到控件，请重试"))

    def _capture_pos(self):
        """捕获鼠标坐标模式"""
        self.status.set("⏳ 3 秒后开始…把鼠标移到目标位置，按 F9 记录坐标")
        self._capture_stop = False
        threading.Thread(target=self._capture_pos_thread, daemon=True).start()

    def _capture_pos_thread(self):
        time.sleep(1)
        self.root.after(0, self.root.iconify)
        time.sleep(2)

        self.root.after(0, lambda: self.status.set("📍 等待按 F9 记录坐标…"))

        while not self._capture_stop:
            if _is_f9_pressed():
                time.sleep(0.15)
                break
            time.sleep(0.05)

        if self._capture_stop:
            self.root.after(0, self.root.deiconify)
            return

        pos = ElementCapture.capture_cursor_pos()
        self.root.after(0, self.root.deiconify)

        self.steps.append(Step("click_pos", **pos))
        self.root.after(0, self._refresh_list)

        if "window_title" in pos:
            msg = (f"✅ 已记录窗口内位置 ({pos['rel_x']},{pos['rel_y']}) @ "
                   f"{pos['window_title']}（窗口移动不影响）")
        else:
            msg = f"✅ 已记录屏幕坐标: ({pos['x']}, {pos['y']})"
        self.root.after(0, lambda: self.status.set(msg))

    # ==================== 步骤编辑 ====================

    def _add(self, stype):
        if stype == "wait":
            v = simpledialog.askfloat("等待", "等待秒数:", initialvalue=2.0, minvalue=0.1)
            if v is not None:
                self.steps.append(Step("wait", seconds=v))

        elif stype == "input_text":
            t = simpledialog.askstring("输入文字", "要输入的文字:")
            if t:
                w = simpledialog.askstring("目标窗口", "窗口标题关键词 (留空=当前窗口):") or ""
                self.steps.append(Step("input_text", text=t, window_title=w))

        elif stype == "hotkey":
            k = simpledialog.askstring("快捷键", "如 ctrl+c / ctrl+v / enter / alt+tab:")
            if k:
                self.steps.append(Step("hotkey", keys=k))

        elif stype == "switch_window":
            windows = ElementCapture.list_windows()
            dlg = WindowPicker(self.root, windows)
            self.root.wait_window(dlg.top)
            if dlg.result:
                self.steps.append(Step("switch_window", window_title=dlg.result))

        elif stype == "open_url":
            u = simpledialog.askstring("打开网址", "URL:")
            if u:
                self.steps.append(Step("open_url", url=u))

        self._refresh_list()

    def _edit_step(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        dlg = StepEditDialog(self.root, self.steps[idx])
        self.root.wait_window(dlg.top)
        if dlg.result:
            self.steps[idx] = dlg.result
            self._refresh_list()

    def _delete_step(self):
        sel = self.listbox.curselection()
        if sel:
            del self.steps[sel[0]]
            self._refresh_list()

    def _move(self, d):
        sel = self.listbox.curselection()
        if not sel:
            return
        i = sel[0]
        j = i + d
        if 0 <= j < len(self.steps):
            self.steps[i], self.steps[j] = self.steps[j], self.steps[i]
            self._refresh_list()
            self.listbox.selection_set(j)

    def _refresh_list(self):
        self.listbox.delete(0, tk.END)
        for i, s in enumerate(self.steps):
            self.listbox.insert(tk.END, f"  {i+1}.  {s.describe()}")

    def run(self):
        self.root.mainloop()


# ==================== 步骤编辑对话框 ====================

class StepEditDialog:
    def __init__(self, parent, step):
        self.result = None
        self.top = tk.Toplevel(parent)
        self.top.title(f"编辑 — {STEP_TYPES.get(step.type, step.type)}")
        self.top.transient(parent)
        self.top.grab_set()
        self.top.resizable(False, False)

        frame = ttk.Frame(self.top, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        self.vars = {}
        row = 0
        for key, val in step.params.items():
            if val is None:
                continue
            label = PARAM_LABELS.get(key, key)
            ttk.Label(frame, text=f"{label}:").grid(row=row, column=0, sticky=tk.W, pady=4)
            var = tk.StringVar(value=str(val))
            ttk.Entry(frame, textvariable=var, width=45).grid(
                row=row, column=1, sticky=tk.EW, pady=4, padx=(10, 0)
            )
            self.vars[key] = var
            row += 1

        bf = ttk.Frame(self.top, padding=(15, 0, 15, 15))
        bf.pack(fill=tk.X)
        ttk.Button(bf, text="确定", command=lambda: self._ok(step)).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bf, text="取消", command=self.top.destroy).pack(side=tk.RIGHT)

    def _ok(self, step):
        params = {}
        for k, v in self.vars.items():
            val = v.get()
            try:
                val = float(val)
                if val == int(val):
                    val = int(val)
            except (ValueError, TypeError):
                pass
            params[k] = val
        self.result = Step(step.type, **params)
        self.top.destroy()


# ==================== 窗口选择器 ====================

class WindowPicker:
    def __init__(self, parent, windows):
        self.result = None
        self.top = tk.Toplevel(parent)
        self.top.title("选择窗口")
        self.top.geometry("420x380")
        self.top.transient(parent)
        self.top.grab_set()

        ttk.Label(self.top, text="选择目标窗口 (双击确认):", padding=(10, 10, 10, 5)).pack(anchor=tk.W)

        self.listbox = tk.Listbox(self.top, font=("Microsoft YaHei UI", 10))
        self.listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        for w in windows:
            self.listbox.insert(tk.END, w)

        self.listbox.bind("<Double-Button-1>", self._pick)

        bf = ttk.Frame(self.top, padding=10)
        bf.pack(fill=tk.X)
        ttk.Button(bf, text="确定", command=self._pick).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bf, text="取消", command=self.top.destroy).pack(side=tk.RIGHT)

    def _pick(self, event=None):
        sel = self.listbox.curselection()
        if sel:
            self.result = self.listbox.get(sel[0])
        self.top.destroy()
