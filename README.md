# SmartRing — Circular Application Launcher / 环形应用启动器

[English](#english) | [中文](#中文)

---

## English

A circular application launcher — press a configurable hotkey (default **F12**) to summon a ring of app shortcuts around your cursor. Move your mouse to select, release to launch.

> Tip: Map your mouse's side button to `F12` via your mouse driver software for the best experience.

### Features

- **Hotkey Summon** — Default F12, configurable with Ctrl/Alt/Shift/Win modifiers
- **Circular Cursor Menu** — App icons arranged in a ring around the cursor, auto-extracts real .exe icons
- **Mouse Point Selection** — Move to a sector to highlight; icon enlarges + label appears
- **Dual Trigger Mode**
  - `hold` — press & hold to show, release to launch
  - `toggle` — press once to show, press again to hide
- **Auto-Start (Highest Priority)** — Launch with Windows, always ready
- **Customizable Appearance**
  - 8 preset accent colours + custom hex colour
  - Ring radius / hub radius / icon size (with +/- fine-tuning)
  - Custom background colour
  - **Live preview**: see changes in real time
- **Keyboard Visual** — Simulated keyboard in settings highlights captured shortcuts; 30+ conflict warnings
- **GUI Settings Panel** — Right-click tray icon to open
- **First-Run Wizard** — 5-step guided setup
- **System Tray** — Runs silently in background, single-instance protection

### Quick Start

**Option 1: Use EXE (Recommended)**

Download `SmartRing.exe` from [Releases](https://github.com/CHOWLAN233/smartring/releases), double-click to run.

**Option 2: Python Source**

```bash
pip install -r requirements.txt
pythonw SmartRing.pyw          # No console window (recommended)
python smartring.py            # With console window
# Or double-click run.bat
```

### Build EXE

```bash
# Double-click build_exe.bat
# Or manually:
pip install pyinstaller
pyinstaller SmartRing.spec --clean --noconfirm
# Output: dist\SmartRing.exe
```

### Configuration

All settings in `config.json` (auto-generated on first run):

| Key | Description | Default |
|-----|-------------|---------|
| `auto_start` | Launch with Windows (highest priority) | `false` |
| `hotkey` | Keyboard shortcut | `"f12"` |
| `mode` | Trigger mode (`hold` / `toggle`) | `"hold"` |
| `theme` | UI theme (`light` / `dark`) | `"dark"` |
| `accent_color` | Highlight colour | `"#0078D4"` |
| `bg_color` | Ring background colour | `"#1e1e26"` |
| `ring_radius` | Outer ring radius (px) | `190` |
| `center_radius` | Hub radius (px) | `58` |
| `icon_size` | App icon size (px) | `38` |
| `animation_duration` | Fade animation (ms) | `220` |
| `show_labels` | Show app names in ring | `true` |

Hotkey format examples: `f12`, `ctrl+f12`, `alt+shift+a`, `ctrl+alt+space`

### Mouse Side Button Setup

1. Open your mouse's driver/configuration software
2. Select your mouse
3. Map a side button to the keyboard key `F12` (or your custom hotkey)
4. Press the side button to summon SmartRing

### Dependencies

- Python 3.7+
- PyQt5 >= 5.15
- pynput >= 1.7
- PyInstaller (for building EXE only)

### Disclaimer

SmartRing is an independent project and is **not affiliated with, endorsed by, or associated with** Logitech International S.A. or any of its subsidiaries. "Logitech" and "Action Ring" are trademarks of Logitech. All other trademarks are the property of their respective owners. SmartRing is inspired by the circular menu concept but is a completely independent implementation.

---

## 中文

环形应用启动器 — 按下可配置的快捷键（默认 **F12**）在光标周围唤出一圈应用程序快捷方式。移动鼠标选择，松开快捷键（或点击）即可启动。

> 提示：通过鼠标驱动软件将侧键映射为 `F12` 可获得最佳体验。

### 功能特性

- **快捷键唤出** — 默认 F12，可配置 Ctrl/Alt/Shift/Win 组合键
- **光标环形菜单** — 应用图标圆形排列在光标周围，自动提取真实 exe 图标
- **鼠标指向选择** — 移动到对应扇区自动高亮，图标放大 + 标签弹出
- **两种触发模式**
  - `hold` — 按住唤出、松开启动
  - `toggle` — 按一下显示、再按隐藏
- **开机自启（最高优先级）** — 随 Windows 启动，确保随时可用
- **可自定义外观**
  - 8 种预设主题色 + 自定义色值
  - 圆环外径 / 中心半径 / 图标大小（带 +/- 微调）
  - 自定义背景色
  - **实时预览**：调整参数即时看到效果
- **模拟键盘** — 设置面板内置键盘，输入快捷键时高亮对应按键；30+ 冲突提醒
- **图形化设置界面** — 右键托盘图标打开
- **首次启动向导** — 5 步引导完成初始配置
- **系统托盘驻留** — 后台静默运行，单实例保护

### 快速开始

**方式 1：使用 EXE（推荐）**

从 [Releases](https://github.com/CHOWLAN233/smartring/releases) 下载 `SmartRing.exe`，双击运行。

**方式 2：Python 源码**

```bash
pip install -r requirements.txt
pythonw SmartRing.pyw          # 无控制台窗口（推荐）
python smartring.py            # 带控制台窗口
# 或双击 run.bat
```

### 构建 EXE

```bash
# 双击 build_exe.bat
# 或手动：
pip install pyinstaller
pyinstaller SmartRing.spec --clean --noconfirm
# 输出：dist\SmartRing.exe
```

### 配置

所有设置保存在 `config.json`（首次运行自动生成）：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `auto_start` | 开机自启（最高优先级） | `false` |
| `hotkey` | 快捷键 | `"f12"` |
| `mode` | 触发模式 (`hold` / `toggle`) | `"hold"` |
| `theme` | 界面主题 (`light` / `dark`) | `"dark"` |
| `accent_color` | 高亮主题色 | `"#0078D4"` |
| `bg_color` | 圆环背景色 | `"#1e1e26"` |
| `ring_radius` | 外环半径 (px) | `190` |
| `center_radius` | 中心半径 (px) | `58` |
| `icon_size` | 图标大小 (px) | `38` |
| `animation_duration` | 动画时长 (ms) | `220` |
| `show_labels` | 显示应用标签 | `true` |

快捷键格式示例：`f12`、`ctrl+f12`、`alt+shift+a`、`ctrl+alt+space`

### 鼠标侧键设置

1. 打开你的鼠标驱动/配置软件
2. 选择你的鼠标
3. 将侧键映射为键盘按键 `F12`（或你自定义的快捷键）
4. 按下侧键即可唤出 SmartRing

### 依赖

- Python 3.7+
- PyQt5 >= 5.15
- pynput >= 1.7
- PyInstaller（仅构建 EXE 时需要）

### 免责声明

SmartRing 是独立项目，**与 Logitech International S.A. 及其子公司无任何关联、认可或从属关系**。"Logitech" 和 "Action Ring" 是罗技的商标。所有其他商标均为其各自所有者的财产。SmartRing 受环形菜单概念的启发，但为完全独立的实现。

---

## Links / 链接

- Website / 官网：[chowlan233.github.io/smartring](https://chowlan233.github.io/smartring/)
- [Releases / 下载](https://github.com/CHOWLAN233/smartring/releases)
- [License](LICENSE) — MIT
