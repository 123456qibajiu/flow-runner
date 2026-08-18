# flow-runner

Windows 桌面流程自动化工具 — 录制操作步骤，一键回放。

不是连点器。不是按键精灵。它能识别窗口里的按钮和输入框，按名称定位，窗口挪了也能找到。当然也支持纯坐标模式，简单粗暴。

## 功能

- **控件捕获** — 鼠标移到目标按钮上按 F9，自动识别控件名称/ID，回放时智能匹配
- **坐标点击** — 对于捕获不到的软件（微信、浏览器等），直接记录鼠标坐标
- **步骤编辑** — 添加、删除、排序、编辑每一步操作
- **流程存取** — 流程保存为 JSON 文件，随时加载复用
- **一键运行** — 点一下，自动执行整个流程

## 支持的步骤类型

| 类型 | 说明 |
|------|------|
| 点击控件 | 按控件名称/ID 智能匹配，窗口挪了也能找到 |
| 坐标点击 | 纯坐标 (x, y)，适合自定义渲染的软件 |
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

## 项目结构

```
├── main.py           # 入口
├── app.py            # GUI 界面（tkinter）
├── engine.py         # 核心引擎（控件识别 + 流程执行）
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

## License

MIT
