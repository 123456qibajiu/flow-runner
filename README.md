# flow-runner

Windows 桌面流程自动化工具 — 录制操作步骤，一键回放。

不是连点器。不是按键精灵。它能识别窗口里的按钮和输入框，按名称定位，窗口挪了也能找到。就算控件识别不到（微信、浏览器这类自绘界面），还有位置兜底，照样点得中。

## 功能

- **智能点击** — 捕获时同时记录控件信息和它在窗口内的位置。回放时先按控件名找，找不到就按窗口内位置点，双保险
- **坐标点击** — 记录鼠标位置时自动绑定所在窗口，窗口挪了位置，点击依然准确
- **单步测试** — 选中任意一步单独运行，方便调试
- **步骤编辑** — 添加、删除、排序、编辑每一步操作
- **流程存取** — 流程保存为 JSON 文件，随时加载复用
- **一键运行** — 点一下，自动执行整个流程

## 支持的步骤类型

| 类型 | 说明 |
|------|------|
| 智能点击 | 控件名匹配 + 窗口内位置兜底，双保险 |
| 坐标点击 | 窗口内相对坐标（推荐）或屏幕绝对坐标 |
| 输入文字 | 通过剪贴板粘贴，支持中文 |
| 快捷键 | 如 ctrl+c、ctrl+v、enter、alt+tab |
| 等待 | 等待指定秒数 |
| 切换窗口 | 按窗口标题模糊匹配并激活 |
| 打开网址 | 在默认浏览器中打开 |

## 快速开始

### 环境要求

- Windows 10/11
- Python 3.10+

### 安装

```bash
pip install -r requirements.txt
```

### 运行

```bash
python main.py
```

### 打包成 exe

```bash
pyinstaller --onefile --windowed --name "flow-runner" main.py
```

打包后 exe 在 `dist/` 目录下，双击即用。

## 使用示例

以「从 DeepSeek 复制文章 → 粘贴到微信打卡」为例：

```
1. 切换到 DeepSeek 窗口
2. 等待 1 秒
3. Ctrl+A（全选内容）
4. Ctrl+C（复制）
5. 切换到微信窗口
6. Ctrl+V（粘贴）
7. Enter（发送）
```

这个示例流程已内置在 `flows/example_deepseek_wechat.json`，直接加载即可。

> 💡 调试技巧：录好流程后，先选中某一步点 **▶ 测试选中** 单独验证，
> 每步都通过了再点 **▶ 运行** 跑全流程。

## 项目结构

```
├── main.py           # 入口
├── app.py            # GUI 界面（tkinter）
├── engine.py         # 核心引擎（控件识别 + 位置兜底 + 流程执行）
├── requirements.txt  # 依赖
├── flows/            # 流程文件目录
│   └── example_deepseek_wechat.json
└── build_exe.bat     # 一键打包脚本
```

## 技术栈

- [uiautomation](https://github.com/yinkaisheng/Python-UIAutomation-for-Windows) — Windows UI 控件识别
- [PyAutoGUI](https://pyautogui.readthedocs.io/) — 鼠标键盘模拟
- [pyperclip](https://pypi.org/project/pyperclip/) — 剪贴板操作（支持中文输入）
- tkinter — GUI（Python 内置）

## 版本历史

- **v1.5** — 点击可靠性大幅增强：智能点击增加位置兜底；坐标点击自动绑定窗口；新增单步测试
- **v1.0** — 初始版本：控件捕获、坐标点击、步骤编辑、流程存取、一键运行

## License

MIT
