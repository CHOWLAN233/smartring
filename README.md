# SmartRing — 环形应用启动器

受罗技 Action Ring 启发，按下可配置的快捷键（默认 **F12**）在光标周围唤出一圈应用程序快捷方式。移动鼠标选择，松开快捷键（或点击）即可启动。

> ✨ 配合鼠标侧键使用：在 Logitech G Hub / Options 中将侧键映射为 `F12` 即可。

## 功能

- 🔘 **快捷键唤出** — 默认 F12，可自由配置任意组合键（含修饰键 Ctrl/Alt/Shift/Win）
- 🎯 **光标环形菜单** — 应用图标以圆形排列在光标周围，自动提取真实 exe 图标
- 🖱 **鼠标指向选择** — 移动鼠标到对应扇区自动高亮，图标放大 + 标签高亮
- 🚀 **两种触发模式**
  - `hold` — 按住唤出、松开启动（类似原版 Action Ring）
  - `toggle` — 按一下显示、再按一下隐藏
- 🎨 **可自定义外观**
  - 8 种预设主题色 + 自定义色值
  - 圆环外径 / 中心半径 / 图标大小（带 +/− 微调按钮）
  - 浅色 / 深色界面主题
  - **实时预览**：调整参数即时看到效果
- 📝 **图形化设置界面** — 右键托盘图标打开
- 🧙 **首次启动向导** — 5 步引导完成初始配置
- 💼 **系统托盘驻留** — 后台静默运行，单实例保护

## 快速开始

### 方式 1：直接使用 EXE（推荐）

下载 `dist/SmartRing.exe`，双击运行。首次启动自动弹出设置向导。

### 方式 2：Python 源码

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动
pythonw SmartRing.pyw          # 无控制台窗口 (推荐)
python smartring.py            # 带控制台窗口
双击 run.bat                   # 一键启动
```

### 构建 EXE

```bash
双击 build_exe.bat             # 自动安装 PyInstaller → 构建 → 输出 dist\SmartRing.exe
```

## 首次启动向导

| 步骤 | 内容 |
|------|------|
| ① 欢迎 | LOGO + 功能介绍 |
| ② 快捷键 | 点击输入框 → 直接按键盘 → 自动捕获组合键 |
| ③ 应用 | 预填常用应用，可增删，带文件浏览器 |
| ④ 外观 | 主题色 + 浅/深色主题 + 圆环尺寸（带 +/− 微调）+ 实时预览 |
| ⑤ 完成 | 配置摘要 → 保存 → 进入托盘模式 |

后续启动直接进入系统托盘，不再显示向导。

## 配置

所有设置保存在 `config.json`（首次运行自动生成）：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `hotkey` | 快捷键 | `"f12"` |
| `mode` | 触发模式 (`hold` / `toggle`) | `"hold"` |
| `theme` | 界面主题 (`light` / `dark`) | `"dark"` |
| `accent_color` | 主题色 | `"#0078D4"` |
| `ring_radius` | 外环半径 (px) | `190` |
| `center_radius` | 中心半径 (px) | `58` |
| `icon_size` | 图标大小 (px) | `38` |
| `animation_duration` | 动画时长 (ms) | `220` |
| `apps` | 应用列表 | 见默认配置 |

快捷键格式示例：`f12`, `ctrl+f12`, `alt+shift+a`, `ctrl+alt+space`

## 鼠标侧键设置

1. 打开罗技 G Hub / Logitech Options
2. 选择你的鼠标
3. 将侧键映射为键盘按键 `F12`（或你自定义的快捷键）
4. 按下侧键即可唤出 SmartRing

## 依赖

- Python 3.7+
- PyQt5 ≥ 5.15
- pynput ≥ 1.7
- PyInstaller（仅构建 EXE 时需要）

## 仓库

[https://github.com/CHOWLAN233/smartring](https://github.com/CHOWLAN233/smartring)

## License

MIT
