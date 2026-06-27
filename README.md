# SmartRing — 环形应用启动器

受罗技 Action Ring 启发，按下可配置的快捷键（默认 **F12**）在光标周围唤出一圈应用程序快捷方式。移动鼠标选择，松开快捷键（或点击）即可启动应用。

> ✨ 配合鼠标侧键使用：在 Logitech G Hub / Options 中将侧键映射为 `F12` 即可。

## 功能

- 🔘 **快捷键唤出** — 默认 F12，可自由配置任意组合键
- 🎯 **光标环形菜单** — 应用图标以圆形排列在光标周围
- 🖱 **鼠标指向选择** — 移动鼠标到对应扇区自动高亮
- 🚀 **两种触发模式**
  - `hold` — 按住唤出、松开启动（类似原版 Action Ring）
  - `toggle` — 按一下显示、再按一下隐藏
- 🎨 **可自定义外观** — 主题色、圆环大小、图标大小
- 📝 **图形化设置界面** — 右键托盘图标直接编辑
- 💼 **系统托盘驻留** — 开机自启、后台静默运行

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动（3 种方式任选）
python smartring.py          # 带控制台窗口
pythonw SmartRing.pyw        # 无控制台窗口 (推荐)
双击 run.bat                 # Windows 一键启动
```

程序启动后出现在**系统托盘**中。右键托盘图标 → **设置** 即可自定义。

## 配置

所有设置保存在 `config.json`（首次运行自动生成）：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `hotkey` | 快捷键 | `"f12"` |
| `mode` | 触发模式 | `"hold"` |
| `accent_color` | 主题色 | `"#0078D4"` |
| `ring_radius` | 外环半径 (px) | `190` |
| `center_radius` | 中心半径 (px) | `58` |
| `icon_size` | 图标大小 (px) | `38` |
| `animation_duration` | 动画时长 (ms) | `220` |
| `apps` | 应用列表 | 见默认配置 |

快捷键格式示例：`f12`, `ctrl+f12`, `alt+shift+a`, `ctrl+alt+space`

## 依赖

- Python 3.7+
- PyQt5 ≥ 5.15
- pynput ≥ 1.7

## 鼠标侧键设置

1. 打开罗技 G Hub / Logitech Options
2. 选择你的鼠标
3. 将侧键（前进/后退）映射为键盘按键 `F12`
4. 按下侧键即可唤出 SmartRing

## License

MIT
