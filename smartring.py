#!/usr/bin/env python3
"""
SmartRing — Circular Application Launcher
Inspired by Logitech Action Ring.

Press a configurable hotkey (default F12) to summon a ring of application
shortcuts around your cursor.  Move the mouse toward an app to select it,
then release the hotkey (or click) to launch.

All settings — hotkey, ring look, app list — live in config.json next to
this script.  Edit it by hand or right-click the tray icon → Settings.

Run without a console window:
    pythonw SmartRing.pyw
Or double-click SmartRing.pyw / run.bat in Explorer.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── PyQt5 ────────────────────────────────────────────────────────────────────
from PyQt5.QtCore import (
    QEasingCurve,
    QFileInfo,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    pyqtSignal,
    QObject,
)
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QCursor,
    QFont,
    QFontMetrics,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFileDialog,
    QFileIconProvider,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
    QStyle,
)

# ── pynput ───────────────────────────────────────────────────────────────────
from pynput import keyboard as pynput_keyboard
from pynput.keyboard import Key, KeyCode


# =============================================================================
# Constants
# =============================================================================

APP_NAME = "SmartRing"
CONFIG_FILENAME = "config.json"

# Built-in default configuration written when no config file exists.
DEFAULT_CONFIG: Dict[str, Any] = {
    "hotkey": "f12",
    "mode": "hold",               # "hold" or "toggle"
    "ring_radius": 190,           # outer radius (px)
    "center_radius": 58,          # centre hub radius (px)
    "icon_size": 38,              # app icon size (px)
    "accent_color": "#0078D4",   # highlight / accent colour
    "bg_color": "#1e1e26",         # ring background base colour
    "theme": "dark",             # "light" or "dark" (wizard always starts light)
    "auto_start": False,         # launch with Windows
    "show_labels": True,         # show app names in the ring
    "animation_duration": 220,    # fade-in / fade-out (ms)
    "apps": [
        {"name": "记事本",    "path": "notepad.exe",                    "args": "", "icon": ""},
        {"name": "计算器",    "path": "calc.exe",                        "args": "", "icon": ""},
        {"name": "文件资源管理器", "path": "explorer.exe",               "args": "", "icon": ""},
        {"name": "命令提示符", "path": "cmd.exe",                        "args": "", "icon": ""},
        {"name": "浏览器",    "path": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", "args": "", "icon": ""},
        {"name": "VS Code",   "path": "C:\\Users\\11606\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe", "args": "", "icon": ""},
    ],
}


# =============================================================================
# Helpers
# =============================================================================

def startup_shortcut_path() -> str:
    """Path to the Windows Startup folder shortcut for SmartRing."""
    startup_dir = os.path.join(
        os.environ.get("APPDATA", ""),
        "Microsoft", "Windows", "Start Menu", "Programs", "Startup",
    )
    return os.path.join(startup_dir, "SmartRing.vbs")


def set_auto_start(enabled: bool) -> bool:
    """
    Create or remove the Windows startup shortcut.
    Returns True on success.
    """
    spath = startup_shortcut_path()
    try:
        if enabled:
            # Determine what to launch
            exe_path = os.path.join(
                os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__)),
                "SmartRing.exe" if getattr(sys, 'frozen', False) else "",
            )
            if getattr(sys, 'frozen', False) and os.path.isfile(exe_path):
                target = exe_path
            else:
                # Launch via pythonw
                script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "SmartRing.pyw")
                target = f'pythonw "{script}"'

            vbs_content = (
                'Set WshShell = CreateObject("WScript.Shell")\r\n'
                f'WshShell.Run "{target}", 0, False\r\n'
            )
            os.makedirs(os.path.dirname(spath), exist_ok=True)
            with open(spath, "w") as f:
                f.write(vbs_content)
        else:
            if os.path.isfile(spath):
                os.remove(spath)
        return True
    except Exception:
        return False


def get_auto_start() -> bool:
    """Check if the startup shortcut exists."""
    return os.path.isfile(startup_shortcut_path())


def config_path() -> str:
    """Path to config.json — always next to the script / exe."""
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller bundle — use the exe directory
        base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, CONFIG_FILENAME)


def parse_hotkey(hotkey_str: str) -> Tuple[set, object]:
    """
    Parse a hotkey string into (modifiers_set, main_key).

    Examples
    --------
    "f12"           → (set(), Key.f12)
    "ctrl+f12"      → ({Key.ctrl}, Key.f12)
    "ctrl+alt+a"    → ({Key.ctrl, Key.alt}, KeyCode.from_char('a'))
    """
    parts = [p.strip() for p in hotkey_str.lower().split("+")]
    modifiers: set = set()
    main_key = None

    MOD_MAP = {
        "ctrl": Key.ctrl, "control": Key.ctrl,
        "alt": Key.alt, "menu": Key.alt,
        "shift": Key.shift,
        "win": Key.cmd, "cmd": Key.cmd, "windows": Key.cmd,
    }

    FN_MAP = {f"f{i}": getattr(Key, f"f{i}") for i in range(1, 13)}
    SPECIAL_MAP = {
        "space": Key.space, "enter": Key.enter, "return": Key.enter,
        "tab": Key.tab, "esc": Key.esc, "escape": Key.esc,
        "backspace": Key.backspace, "delete": Key.delete,
        "insert": Key.insert, "home": Key.home, "end": Key.end,
        "pageup": Key.page_up, "pagedown": Key.page_down,
        "up": Key.up, "down": Key.down, "left": Key.left, "right": Key.right,
        "printscreen": Key.print_screen, "scrolllock": Key.scroll_lock,
        "pause": Key.pause, "capslock": Key.caps_lock,
    }

    for part in parts:
        if part in MOD_MAP:
            modifiers.add(MOD_MAP[part])
        elif part in FN_MAP:
            main_key = FN_MAP[part]
        elif part in SPECIAL_MAP:
            main_key = SPECIAL_MAP[part]
        elif len(part) == 1:
            main_key = KeyCode.from_char(part)
        else:
            raise ValueError(f"Unrecognised key: '{part}' in hotkey '{hotkey_str}'")

    if main_key is None:
        raise ValueError(f"No main key found in hotkey '{hotkey_str}'")

    return modifiers, main_key


def resolve_app_path(app_path: str) -> str:
    """
    Resolve a possibly-short app name (e.g. 'notepad.exe') to a full path.
    Returns the original string if no full path can be found.
    """
    # Already a full path?
    if os.path.isfile(app_path):
        return os.path.abspath(app_path)

    # Try shutil.which (searches PATH and common locations)
    resolved = shutil.which(app_path)
    if resolved and os.path.isfile(resolved):
        return resolved

    # Try common Windows system directories
    if sys.platform == "win32":
        windir = os.environ.get("SystemRoot", "C:\\Windows")
        candidates = [
            os.path.join(windir, app_path),
            os.path.join(windir, "System32", app_path),
            os.path.join(windir, "SysWOW64", app_path),
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c

        # Try Program Files
        for pf in ["ProgramFiles", "ProgramFiles(x86)", "ProgramW6432",
                    "LocalAppData", "AppData"]:
            base = os.environ.get(pf)
            if base:
                c = os.path.join(base, app_path)
                if os.path.isfile(c):
                    return c

    return app_path


def extract_icon(exe_path: str, size: int = 48) -> QIcon:
    """
    Extract the system icon for an executable on Windows.
    Resolves short names to full paths before extraction.
    Returns an empty QIcon on failure (caller should use fallback).
    """
    # Resolve to full path first
    full_path = resolve_app_path(exe_path)

    # Method 1: QFileIconProvider (works for most .exe / .lnk)
    try:
        provider = QFileIconProvider()
        info = QFileInfo(full_path)
        if info.exists():
            icon = provider.icon(info)
            if not icon.isNull():
                return icon
    except Exception:
        pass

    # Method 2: try the original path as fallback
    if full_path != exe_path:
        try:
            info2 = QFileInfo(exe_path)
            if info2.exists():
                icon = provider.icon(info2)
                if not icon.isNull():
                    return icon
        except Exception:
            pass

    return QIcon()


def hex_to_qcolor(hex_str: str, alpha: int = 255) -> QColor:
    """Convert '#RRGGBB' or '#RRGGBBAA' to QColor."""
    h = hex_str.lstrip("#")
    if len(h) == 6:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return QColor(r, g, b, alpha)
    elif len(h) == 8:
        r, g, b, a = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16)
        return QColor(r, g, b, a)
    return QColor("#0078D4")


def qcolor_to_hex(c: QColor) -> str:
    """Convert QColor to '#RRGGBB'."""
    return f"#{c.red():02X}{c.green():02X}{c.blue():02X}"


# =============================================================================
# KeyCaptureLineEdit  —  capture real keystrokes for hotkey config
# =============================================================================

class KeyCaptureLineEdit(QLineEdit):
    """
    A line-edit that captures an actual key combination when focused.
    Click / focus → shows hint → press your hotkey → displays friendly name.
    """

    MOD_NAMES = {
        Key.ctrl: "Ctrl", Key.ctrl_l: "Ctrl", Key.ctrl_r: "Ctrl",
        Key.alt: "Alt", Key.alt_l: "Alt", Key.alt_r: "Alt",
        Key.shift: "Shift", Key.shift_l: "Shift", Key.shift_r: "Shift",
        Key.cmd: "Win", Key.cmd_l: "Win", Key.cmd_r: "Win",
    }

    KEY_NAMES = {
        Key.space: "Space", Key.enter: "Enter", Key.tab: "Tab",
        Key.esc: "Esc", Key.backspace: "Backspace", Key.delete: "Delete",
        Key.insert: "Insert", Key.home: "Home", Key.end: "End",
        Key.page_up: "PageUp", Key.page_down: "PageDown",
        Key.up: "Up", Key.down: "Down", Key.left: "Left", Key.right: "Right",
        Key.print_screen: "PrintScreen", Key.scroll_lock: "ScrollLock",
        Key.pause: "Pause", Key.caps_lock: "CapsLock",
    }
    for i in range(1, 13):
        KEY_NAMES[getattr(Key, f"f{i}")] = f"F{i}"

    key_captured = pyqtSignal(str)   # emits the hotkey string like "ctrl+f12"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mods: set = set()
        self._main_key = None
        self._capturing = False
        self.setReadOnly(True)
        self.setPlaceholderText("点击此处，然后按下快捷键…")
        self.setStyleSheet(
            "QLineEdit { background-color: #f8f8fa; border: 2px dashed #ccc; "
            "border-radius: 6px; padding: 10px 14px; color: #999; font-size: 15px; }"
            "QLineEdit:focus { border-color: #0078D4; color: #333; }"
        )
        self._listener: Optional[pynput_keyboard.Listener] = None

    def mousePressEvent(self, event) -> None:
        if not self._capturing:
            self._start_capture()
        super().mousePressEvent(event)

    def focusInEvent(self, event) -> None:
        if not self._capturing:
            self._start_capture()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self._stop_capture()
        super().focusOutEvent(event)

    def _start_capture(self) -> None:
        self._capturing = True
        self._mods.clear()
        self._main_key = None
        self.setText("…")
        self.setStyleSheet(
            "QLineEdit { background-color: #e8f0fa; border: 2px solid #0078D4; "
            "border-radius: 6px; padding: 10px 14px; color: #0078D4; font-size: 15px; }"
        )
        try:
            self._listener = pynput_keyboard.Listener(
                on_press=self._on_key_press,
            )
            self._listener.start()
        except Exception:
            pass

    def _stop_capture(self) -> None:
        self._capturing = False
        try:
            if self._listener:
                self._listener.stop()
                self._listener = None
        except Exception:
            pass
        self.setStyleSheet(
            "QLineEdit { background-color: #f8f8fa; border: 2px dashed #ccc; "
            "border-radius: 6px; padding: 10px 14px; color: #999; font-size: 15px; }"
            "QLineEdit:focus { border-color: #0078D4; color: #333; }"
        )

    def _on_key_press(self, key) -> None:
        if not self._capturing:
            return

        # Track modifiers
        if key in (Key.ctrl_l, Key.ctrl_r):
            self._mods.add(Key.ctrl)
        elif key in (Key.alt_l, Key.alt_r):
            self._mods.add(Key.alt)
        elif key in (Key.shift_l, Key.shift_r):
            self._mods.add(Key.shift)
        elif key in (Key.cmd_l, Key.cmd_r):
            self._mods.add(Key.cmd)
        else:
            self._main_key = key
            self._build_result()

    def _build_result(self) -> None:
        if self._main_key is None:
            return

        parts = []
        # Modifiers sorted consistently
        for mod in sorted(self._mods, key=lambda k: str(k)):
            if mod in self.MOD_NAMES:
                parts.append(self.MOD_NAMES[mod])

        if self._main_key in self.KEY_NAMES:
            parts.append(self.KEY_NAMES[self._main_key])
        elif hasattr(self._main_key, 'char') and self._main_key.char:
            parts.append(self._main_key.char.upper())
        else:
            parts.append(str(self._main_key).replace("Key.", ""))

        hotkey_str = "+".join(parts)
        hotkey_cfg = "+".join(p.lower() for p in parts)

        self.setText(hotkey_str)
        self.key_captured.emit(hotkey_cfg)
        self._stop_capture()

    def set_hotkey(self, cfg_string: str) -> None:
        """Set from config string like 'ctrl+f12'."""
        # Reverse the parse to get a friendly display string
        parts = cfg_string.lower().split("+")
        display = "+".join(p.capitalize() if len(p) > 1 else p.upper() for p in parts)
        # Better: map known keys
        friendly = []
        for p in parts:
            p = p.strip()
            if p in ("ctrl", "control"):
                friendly.append("Ctrl")
            elif p in ("alt", "menu"):
                friendly.append("Alt")
            elif p in ("shift",):
                friendly.append("Shift")
            elif p in ("win", "cmd", "windows"):
                friendly.append("Win")
            elif p.startswith("f") and p[1:].isdigit():
                friendly.append(p.upper())
            elif len(p) == 1:
                friendly.append(p.upper())
            else:
                friendly.append(p.capitalize())
        self.setText("+".join(friendly))


# =============================================================================
# ConfigManager
# =============================================================================

class ConfigManager:
    """Load / save / validate config.json."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.data: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as fh:
                    self.data = json.load(fh)
            except (json.JSONDecodeError, OSError) as exc:
                print(f"[SmartRing] Failed to load config: {exc} — using defaults")
                self.data = dict(DEFAULT_CONFIG)
        else:
            self.data = dict(DEFAULT_CONFIG)
            self.save()

        # Merge missing keys
        changed = False
        for key, value in DEFAULT_CONFIG.items():
            if key not in self.data:
                self.data[key] = value
                changed = True
        if changed:
            self.save()

    def save(self) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, indent=2, ensure_ascii=False)
        except OSError as exc:
            print(f"[SmartRing] Failed to save config: {exc}")

    # ── typed accessors ─────────────────────────────────────────────────

    @property
    def hotkey(self) -> str:
        return str(self.data.get("hotkey", "f12"))

    @property
    def mode(self) -> str:
        mode = self.data.get("mode", "hold")
        return mode if mode in ("hold", "toggle") else "hold"

    @property
    def ring_radius(self) -> int:
        return int(self.data.get("ring_radius", 190))

    @property
    def center_radius(self) -> int:
        return int(self.data.get("center_radius", 58))

    @property
    def icon_size(self) -> int:
        return int(self.data.get("icon_size", 38))

    @property
    def accent_color(self) -> str:
        return str(self.data.get("accent_color", "#0078D4"))

    @property
    def bg_color(self) -> str:
        return str(self.data.get("bg_color", "#1e1e26"))

    @property
    def theme(self) -> str:
        t = self.data.get("theme", "dark")
        return t if t in ("light", "dark") else "dark"

    @property
    def auto_start(self) -> bool:
        return bool(self.data.get("auto_start", False))

    @property
    def show_labels(self) -> bool:
        return bool(self.data.get("show_labels", True))

    @property
    def animation_duration(self) -> int:
        return int(self.data.get("animation_duration", 220))

    @property
    def apps(self) -> List[Dict[str, str]]:
        return list(self.data.get("apps", DEFAULT_CONFIG["apps"]))


# =============================================================================
# RingOverlay  —  the circular pop-up
# =============================================================================

class RingOverlay(QWidget):
    """
    Frameless, transparent, always-on-top window that paints a radial
    application ring and tracks the mouse to highlight / select items.

    Visual design: dark glass-like background with a configurable accent
    colour for highlights.  Icons are rendered with soft shadows; labels
    use crisp anti-aliased text.
    """

    app_launched = pyqtSignal(int)
    dismissed = pyqtSignal()

    def __init__(
        self,
        apps: List[Dict[str, str]],
        ring_radius: int = 190,
        center_radius: int = 58,
        icon_size: int = 38,
        accent_color: str = "#0078D4",
        bg_color: str = "#1e1e26",
        animation_duration: int = 220,
        show_labels: bool = True,
        preview_mode: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._apps = apps
        self._ring_r = ring_radius
        self._center_r = center_radius
        self._icon_sz = icon_size
        self._accent = hex_to_qcolor(accent_color)
        self._bg = hex_to_qcolor(bg_color)
        self._anim_ms = animation_duration
        self._show_labels = show_labels
        self._preview_mode = preview_mode
        self._highlighted: int = -1
        self._anim_highlight: float = -1.0
        self._launched = False
        self._hiding = False
        self._label_padding = 24

        # Cached bitmaps
        self._icons: List[QIcon] = []
        self._cached_pixmaps: List[Optional[QPixmap]] = []

        self._widget_size = 2 * (self._ring_r + self._label_padding)
        self.resize(self._widget_size, self._widget_size)

        self._setup_window()
        self._preload_icons()

        # Smooth highlight transition animation
        self._highlight_anim = QVariantAnimation(self)
        self._highlight_anim.setDuration(150)
        self._highlight_anim.valueChanged.connect(self._on_highlight_anim)
        self._highlight_anim.setStartValue(-1.0)
        self._highlight_anim.setEndValue(-1.0)

    # ── window setup ─────────────────────────────────────────────────────

    def _setup_window(self) -> None:
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAutoFillBackground(False)
        self.setWindowTitle(APP_NAME)
        self.setMouseTracking(True)

        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.setDuration(self._anim_ms)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._mouse_timer = QTimer(self)
        self._mouse_timer.timeout.connect(self._poll_global_mouse)
        self._mouse_timer.setInterval(20)

    # ── icons ────────────────────────────────────────────────────────────

    def _preload_icons(self) -> None:
        self._icons.clear()
        self._cached_pixmaps.clear()
        for app in self._apps:
            icon = QIcon()
            icon_path = app.get("icon", "")
            exe_path = app.get("path", "")

            # Try user-specified icon file (with and without path resolution)
            if icon_path:
                resolved = resolve_app_path(icon_path)
                if os.path.isfile(resolved):
                    icon = QIcon(resolved)

            # If no icon yet, try extracting from the executable
            if icon.isNull() and exe_path:
                icon = extract_icon(exe_path)

            self._icons.append(icon)
            self._cached_pixmaps.append(None)

    def _app_icon_pixmap(self, index: int) -> QPixmap:
        if 0 <= index < len(self._cached_pixmaps):
            cached = self._cached_pixmaps[index]
            if cached is not None:
                return cached

        sz = self._icon_sz
        icon = self._icons[index] if index < len(self._icons) else QIcon()
        if icon.isNull():
            pix = self._letter_icon(index, sz)
        else:
            pix = icon.pixmap(sz, sz)
            if pix.isNull():
                pix = self._letter_icon(index, sz)

        if 0 <= index < len(self._cached_pixmaps):
            self._cached_pixmaps[index] = pix
        return pix

    def _letter_icon(self, index: int, size: int) -> QPixmap:
        name = self._apps[index]["name"] if index < len(self._apps) else "?"
        letter = name[0].upper() if name else "?"

        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)

        # Colour circle — use evenly-spaced hues
        hues = [210, 120, 0, 280, 45, 170, 340, 30, 190, 260, 80, 310]
        hue = hues[index % len(hues)]
        bg = QColor()
        bg.setHsv(hue, 170, 225)
        painter.setBrush(QBrush(bg))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(2, 2, size - 4, size - 4, 8, 8)

        # Letter
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Microsoft YaHei", int(size * 0.42), QFont.Bold)
        painter.setFont(font)
        painter.drawText(QRect(0, 0, size, size), Qt.AlignCenter, letter)
        painter.end()
        return pix

    def _shadow_icon(self, src: QPixmap) -> QPixmap:
        """Add a subtle drop-shadow beneath the icon."""
        shadow_offset = 3
        out = QPixmap(src.width() + shadow_offset * 2, src.height() + shadow_offset * 2)
        out.fill(Qt.transparent)
        painter = QPainter(out)
        painter.setRenderHint(QPainter.Antialiasing)

        # Shadow
        shadow = QColor(0, 0, 0, 80)
        painter.setBrush(QBrush(shadow))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(
            shadow_offset + 1, shadow_offset + 1,
            src.width() - 2, src.height() - 2, 6, 6,
        )

        # Original
        painter.drawPixmap(0, 0, src)
        painter.end()
        return out

    # ── show / hide ──────────────────────────────────────────────────────

    def show_at(self, global_pos: QPoint) -> None:
        if not self._apps:
            return

        self._launched = False
        self._hiding = False
        self._highlighted = -1
        self._anim_highlight = -1.0

        screen = QApplication.screenAt(global_pos)
        if screen is None:
            screen = QApplication.primaryScreen()
        geom: QRect = screen.availableGeometry()

        half = self._widget_size // 2
        x = global_pos.x() - half
        y = global_pos.y() - half

        if x < geom.left():
            x = geom.left()
        if y < geom.top():
            y = geom.top()
        if x + self._widget_size > geom.right():
            x = geom.right() - self._widget_size
        if y + self._widget_size > geom.bottom():
            y = geom.bottom() - self._widget_size

        self.move(x, y)
        self._ring_center = QPoint(global_pos.x() - x, global_pos.y() - y)

        self.setWindowOpacity(0.0)
        super().show()
        self._mouse_timer.start()
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()

    def hide_ring(self) -> None:
        if self._hiding:
            return
        self._hiding = True
        self._mouse_timer.stop()
        try:
            self._fade_anim.finished.disconnect(self._on_fade_out_done)
        except Exception:
            pass
        self._fade_anim.setStartValue(self.windowOpacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.finished.connect(self._on_fade_out_done)
        self._fade_anim.start()

    def _on_fade_out_done(self) -> None:
        self._hiding = False
        try:
            self._fade_anim.finished.disconnect(self._on_fade_out_done)
        except Exception:
            pass
        super().hide()
        self._mouse_timer.stop()
        if not self._launched:
            self.dismissed.emit()

    def _poll_global_mouse(self) -> None:
        local = self.mapFromGlobal(QCursor.pos())
        self._update_highlight(local)

    # ── geometry helpers ─────────────────────────────────────────────────

    def _app_angle(self, index: int) -> float:
        n = len(self._apps)
        if n == 0:
            return 0.0
        return 2.0 * math.pi * index / n - math.pi / 2.0

    def _app_position(self, index: int, radius: float) -> QPoint:
        a = self._app_angle(index)
        return QPoint(
            int(self._ring_center.x() + radius * math.cos(a)),
            int(self._ring_center.y() + radius * math.sin(a)),
        )

    def _mouse_angle(self, pos: QPoint) -> Optional[float]:
        dx = pos.x() - self._ring_center.x()
        dy = pos.y() - self._ring_center.y()
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 10:
            return None
        return math.atan2(dy, dx)

    def _segment_for_angle(self, angle: float) -> int:
        n = len(self._apps)
        if n == 0:
            return -1
        # Normalise to [0, 2π) and rotate so 0 = top
        a = angle % (2.0 * math.pi)
        a = (a + math.pi / 2.0) % (2.0 * math.pi)
        # Offset by half a segment so boundaries align with visual dividers
        a = (a + math.pi / n) % (2.0 * math.pi)
        return int(a / (2.0 * math.pi / n)) % n

    def _update_highlight(self, mouse_pos: QPoint) -> None:
        ang = self._mouse_angle(mouse_pos)
        old = self._highlighted

        if ang is None:
            self._highlighted = -1
        else:
            seg = self._segment_for_angle(ang)
            dx = mouse_pos.x() - self._ring_center.x()
            dy = mouse_pos.y() - self._ring_center.y()
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < self._center_r:
                self._highlighted = -1
            elif dist > self._ring_r + 35:
                self._highlighted = -1
            else:
                self._highlighted = seg

        if old != self._highlighted:
            self._anim_highlight = float(self._highlighted)
            self.update()

    def _on_highlight_anim(self, value) -> None:
        self._anim_highlight = value
        self.update()

    # ── painting ─────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:
        if not hasattr(self, '_ring_center'):
            return  # not yet positioned — skip painting
        painter = QPainter(self)
        try:
            self._do_paint(painter)
        except Exception as exc:
            import traceback
            print(f"[SmartRing] Paint error: {exc}", file=sys.stderr)
            traceback.print_exc()
        finally:
            painter.end()

    def _do_paint(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing)
        cx, cy = self._ring_center.x(), self._ring_center.y()
        n = len(self._apps)
        if n == 0:
            return

        acc = self._accent
        bg = self._bg

        # ── 1. Outer soft halo ───────────────────────────────────────
        halo = QRadialGradient(cx, cy, self._ring_r + 80)
        halo.setColorAt(0.0, QColor(
            max(0, bg.red() - 20), max(0, bg.green() - 20),
            max(0, bg.blue() - 20), 45))
        halo.setColorAt(0.8, QColor(
            max(0, bg.red() - 25), max(0, bg.green() - 25),
            max(0, bg.blue() - 25), 18))
        halo.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(halo))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPoint(cx, cy), self._ring_r + 80, self._ring_r + 80)

        # ── 2. Ring body ─────────────────────────────────────────────
        ring_body = QPainterPath()
        ring_body.addEllipse(QPoint(cx, cy), self._ring_r, self._ring_r)
        hub = QPainterPath()
        hub.addEllipse(QPoint(cx, cy), self._center_r, self._center_r)
        ring_only = ring_body.subtracted(hub)

        # Ring gradient — based on user-selected background colour
        ring_grad = QRadialGradient(cx, cy, self._ring_r)
        ring_grad.setColorAt(0.0, QColor(
            min(255, bg.red() + 35), min(255, bg.green() + 35),
            min(255, bg.blue() + 35), 238))
        ring_grad.setColorAt(0.55, QColor(
            min(255, bg.red() + 15), min(255, bg.green() + 15),
            min(255, bg.blue() + 15), 232))
        ring_grad.setColorAt(0.85, QColor(
            bg.red(), bg.green(), bg.blue(), 228))
        ring_grad.setColorAt(1.0, QColor(
            max(0, bg.red() - 12), max(0, bg.green() - 12),
            max(0, bg.blue() - 12), 218))
        painter.fillPath(ring_only, QBrush(ring_grad))

        # Subtle inner border on ring
        painter.setPen(QPen(QColor(255, 255, 255, 12), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPoint(cx, cy), self._ring_r, self._ring_r)
        painter.drawEllipse(QPoint(cx, cy), self._center_r, self._center_r)

        # ── 3. Highlighted segment ───────────────────────────────────
        hi = self._highlighted
        if hi < 0 and self._anim_highlight >= 0:
            # Use animated highlight for smooth transitions
            hi = int(round(self._anim_highlight))

        # (no wedge fill — selection indicated by icon size + label only)

        # ── 4. Segment dividers ──────────────────────────────────────
        painter.setPen(QPen(QColor(255, 255, 255, 20), 1))
        for i in range(n):
            a = self._app_angle(i) - math.pi / n
            ex = int(cx + self._ring_r * math.cos(a))
            ey = int(cy + self._ring_r * math.sin(a))
            ix = int(cx + self._center_r * math.cos(a))
            iy = int(cy + self._center_r * math.sin(a))
            painter.drawLine(ix, iy, ex, ey)

        # ── 5. Centre hub ────────────────────────────────────────────
        hub_grad = QRadialGradient(cx, cy, self._center_r)
        hub_grad.setColorAt(0.0, QColor(
            min(255, bg.red() + 48), min(255, bg.green() + 48),
            min(255, bg.blue() + 48), 248))
        hub_grad.setColorAt(1.0, QColor(
            min(255, bg.red() + 18), min(255, bg.green() + 18),
            min(255, bg.blue() + 18), 242))
        painter.setBrush(QBrush(hub_grad))
        painter.setPen(QPen(QColor(255, 255, 255, 15), 1))
        painter.drawEllipse(QPoint(cx, cy), self._center_r, self._center_r)

        # Centre text
        painter.setPen(QColor(220, 220, 225))
        if getattr(self, '_preview_mode', False):
            font = QFont("Microsoft YaHei", 8, QFont.Bold)
            painter.setFont(font)
            painter.drawText(
                QRect(cx - self._center_r, cy - 14, self._center_r * 2, 12),
                Qt.AlignCenter, "预览模式",
            )
            font2 = QFont("Microsoft YaHei", 6)
            painter.setFont(font2)
            painter.setPen(QColor(160, 160, 170))
            painter.drawText(
                QRect(cx - self._center_r, cy + 2, self._center_r * 2, 12),
                Qt.AlignCenter, "点击空白或 Esc 关闭",
            )
        else:
            font = QFont("Microsoft YaHei", 10, QFont.Bold)
            painter.setFont(font)
            painter.drawText(
                QRect(cx - self._center_r, cy - 8, self._center_r * 2, 16),
                Qt.AlignCenter, APP_NAME,
            )

        # ── 6. App icons & labels ────────────────────────────────────
        icon_r = (self._ring_r + self._center_r) // 2
        label_r = self._ring_r - 14

        for i in range(n):
            is_hi = i == hi

            # ── Icon ────────────────────────────────────────────────
            ipos = self._app_position(i, icon_r)
            pix = self._app_icon_pixmap(i)
            if not pix.isNull():
                pw, ph = pix.width(), pix.height()

                if is_hi:
                    # Selected: slightly enlarged
                    scale = 1.15
                    sw, sh = int(pw * scale), int(ph * scale)
                    scaled = pix.scaled(sw, sh, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    painter.drawPixmap(
                        ipos.x() - sw // 2, ipos.y() - sh // 2, sw, sh, scaled,
                    )
                else:
                    # Not selected: normal size, full opacity — no change
                    painter.drawPixmap(
                        ipos.x() - pw // 2, ipos.y() - ph // 2, pw, ph, pix,
                    )

            # ── Label ────────────────────────────────────────────────
            lpos = self._app_position(i, label_r)
            name = self._apps[i]["name"]

            if getattr(self, '_show_labels', True):
                if is_hi:
                    # Selected: bold + subtle pill + bright text (no accent colour)
                    label_font = QFont("Microsoft YaHei", 10, QFont.Bold)
                    painter.setFont(label_font)
                    fm = QFontMetrics(label_font)
                    text_w = fm.horizontalAdvance(name)
                    th = fm.height()

                    pill_w, pill_h = text_w + 18, th + 6
                    pill_rect = QRect(lpos.x() - pill_w // 2, lpos.y() - pill_h // 2, pill_w, pill_h)
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QBrush(QColor(60, 60, 68, 220)))
                    painter.drawRoundedRect(pill_rect, 10, 10)
                    painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawRoundedRect(pill_rect, 10, 10)
                    painter.setPen(QColor(255, 255, 255))
                else:
                    label_font = QFont("Microsoft YaHei", 9, QFont.Normal)
                    painter.setFont(label_font)
                    fm = QFontMetrics(label_font)
                    text_w = fm.horizontalAdvance(name)
                    th = fm.height()
                    painter.setPen(QColor(210, 210, 215))

                painter.drawText(
                    QRect(lpos.x() - text_w // 2, lpos.y() - th // 2, text_w, th),
                    Qt.AlignCenter, name,
                )

    # ── events ───────────────────────────────────────────────────────────

    def mouseMoveEvent(self, event) -> None:
        self._update_highlight(event.pos())
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._highlighted >= 0:
            if getattr(self, '_preview_mode', False):
                # Preview mode: clicking an app icon does nothing
                pass
            else:
                self._launched = True
                self.app_launched.emit(self._highlighted)
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.hide_ring()
        super().keyPressEvent(event)


# =============================================================================
# _KeyboardVisual  —  simulated keyboard reference for hotkey config
# =============================================================================

class _KeyboardVisual(QWidget):
    """Shows a simplified keyboard layout highlighting the captured hotkey."""

    # Keys to display, grouped by row — each row is a list of (label, width_mult) tuples
    _KEYBOARD = [
        # Row 0: function row — smaller keys, extra gap between groups
        [
            ("Esc", 1.0), ("F1", 1.0), ("F2", 1.0), ("F3", 1.0), ("F4", 1.0),
            ("", 0.5), ("F5", 1.0), ("F6", 1.0), ("F7", 1.0), ("F8", 1.0),
            ("", 0.5), ("F9", 1.0), ("F10", 1.0), ("F11", 1.0), ("F12", 1.0),
            ("", 0.5), ("PrtSc", 1.0), ("ScrLk", 1.0), ("Pause", 1.0),
        ],
        # Row 1: number row
        [
            ("~\n`", 1.0), ("!\n1", 1.0), ("@\n2", 1.0), ("#\n3", 1.0),
            ("$\n4", 1.0), ("%\n5", 1.0), ("^\n6", 1.0), ("&\n7", 1.0),
            ("*\n8", 1.0), ("(\n9", 1.0), (")\n0", 1.0), ("_\n-", 1.0),
            ("+\n=", 1.0), ("Bksp", 2.2),
        ],
        # Row 2: QWERTY top
        [
            ("Tab", 1.5), ("Q", 1.0), ("W", 1.0), ("E", 1.0), ("R", 1.0),
            ("T", 1.0), ("Y", 1.0), ("U", 1.0), ("I", 1.0), ("O", 1.0),
            ("P", 1.0), ("{\n[", 1.0), ("}\n]", 1.0), ("|\n\\", 1.5),
        ],
        # Row 3: home row
        [
            ("Caps", 1.8), ("A", 1.0), ("S", 1.0), ("D", 1.0), ("F", 1.0),
            ("G", 1.0), ("H", 1.0), ("J", 1.0), ("K", 1.0), ("L", 1.0),
            (":\n;", 1.0), ("\"\n'", 1.0), ("Enter", 2.3),
        ],
        # Row 4: shift row
        [
            ("Shift", 2.4), ("Z", 1.0), ("X", 1.0), ("C", 1.0), ("V", 1.0),
            ("B", 1.0), ("N", 1.0), ("M", 1.0), ("<\n,", 1.0), (">\n.", 1.0),
            ("?\n/", 1.0), ("Shift", 2.7),
        ],
        # Row 5: bottom modifiers
        [
            ("Ctrl", 1.4), ("Win", 1.2), ("Alt", 1.2), ("", 5.5),
            ("Alt", 1.2), ("Win", 1.2), ("Menu", 1.2), ("Ctrl", 1.4),
        ],
    ]

    MOD_KEYS = {"Ctrl", "Alt", "Shift", "Win", "Menu"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._highlighted_keys: set = set()
        self.setFixedHeight(168)
        self.setMinimumWidth(420)
        self.setMouseTracking(True)

    def set_hotkey(self, hotkey_str: str) -> None:
        """Highlight keys based on hotkey string like 'ctrl+f12'."""
        self._highlighted_keys.clear()
        for part in hotkey_str.lower().split("+"):
            part = part.strip()
            if part in ("ctrl", "control"):
                self._highlighted_keys.add("Ctrl")
            elif part in ("alt", "menu"):
                self._highlighted_keys.add("Alt")
            elif part in ("shift",):
                self._highlighted_keys.add("Shift")
            elif part in ("win", "cmd", "windows"):
                self._highlighted_keys.add("Win")
            elif part.startswith("f") and part[1:].isdigit():
                self._highlighted_keys.add(part.upper())
            elif len(part) == 1:
                self._highlighted_keys.add(part.upper())
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        unit_w = 40   # base key width in px
        key_h = 23
        gap = 2
        fn_key_h = 20
        fn_unit_w = 32
        top_margin = 2

        for row_idx, row_data in enumerate(self._KEYBOARD):
            is_fn_row = row_idx == 0
            ukw = fn_unit_w if is_fn_row else unit_w
            kh = fn_key_h if is_fn_row else key_h

            # Calculate total width for this row
            total_w = sum(wm * ukw + gap for _, wm in row_data) - gap
            x = (w - total_w) // 2  # center every row
            y = top_margin + sum(
                (fn_key_h if ri == 0 else key_h) + gap
                for ri in range(row_idx)
            )

            for label, width_mult in row_data:
                if not label:
                    # Spacer
                    x += int(width_mult * ukw)
                    continue

                kw = int(width_mult * ukw)
                rect = QRect(int(x), int(y), kw - gap, kh)

                is_hi = label in self._highlighted_keys
                is_mod = label in self.MOD_KEYS

                if is_hi:
                    painter.setBrush(QBrush(QColor("#0078D4")))
                    painter.setPen(QPen(QColor("#50a0ff"), 1.2))
                elif is_mod:
                    painter.setBrush(QBrush(QColor(56, 56, 62)))
                    painter.setPen(QPen(QColor(85, 85, 93), 1))
                else:
                    painter.setBrush(QBrush(QColor(46, 46, 52)))
                    painter.setPen(QPen(QColor(68, 68, 74), 1))

                painter.drawRoundedRect(rect, 3, 3)

                # Label
                if is_hi:
                    painter.setPen(QColor(255, 255, 255))
                else:
                    painter.setPen(QColor(175, 175, 180))
                fz = 6 if is_fn_row else 7
                font = QFont("Microsoft YaHei", fz)
                painter.setFont(font)
                display = label.split("\n")[0]
                painter.drawText(rect, Qt.AlignCenter, display)

                x += kw

        painter.end()


# =============================================================================
# PreviewBackdrop  —  popup window that hosts the ring for preview
# =============================================================================

class PreviewBackdrop(QWidget):
    """Centered popup window with dark background that hosts the ring preview."""

    dismissed = pyqtSignal()

    def __init__(self, ring: RingOverlay, ring_radius: int, parent=None):
        super().__init__(parent)
        self._ring = ring
        self._ring_r = ring_radius
        self._closing = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Dialog
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setWindowTitle(f"{APP_NAME} — 预览")

        # Size to fit the ring
        padding = 100
        win_size = 2 * (self._ring_r + padding)
        self.setFixedSize(win_size, win_size + 36)  # extra height for title bar

        # Center on primary screen
        screen_center = QApplication.primaryScreen().geometry().center()
        self.move(screen_center.x() - win_size // 2,
                   screen_center.y() - (win_size + 36) // 2)

        # Dark background
        self.setStyleSheet(
            "QWidget#previewBackdrop { background-color: #1a1a20; "
            "border: 1px solid #3a3a42; border-radius: 12px; }"
        )
        self.setObjectName("previewBackdrop")

        # ── Custom title bar ──────────────────────────────────────────
        title_bar = QWidget(self)
        title_bar.setFixedHeight(36)
        title_bar.setStyleSheet("background: transparent; border: none;")
        title_bar.move(0, 0)
        title_bar.setFixedWidth(win_size)

        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(16, 0, 8, 0)
        tb_layout.setSpacing(0)

        title_lbl = QLabel(f"{APP_NAME} — 预览")
        title_lbl.setStyleSheet("color: #ccc; font-size: 13px; font-weight: bold; background: transparent;")
        tb_layout.addWidget(title_lbl)
        tb_layout.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #999; border: none; "
            "font-size: 16px; font-weight: bold; border-radius: 6px; }"
            "QPushButton:hover { background-color: #c42b1c; color: white; }"
        )
        close_btn.clicked.connect(self._dismiss)
        tb_layout.addWidget(close_btn)

        # ── Ring positioning ──────────────────────────────────────────
        # Ring appears below the title bar
        ring_cx = win_size // 2
        ring_cy = 36 + (win_size // 2)  # offset by title bar height
        self._ring_center = QPoint(ring_cx, ring_cy)

        # Connect ring signals
        self._ring.dismissed.connect(self._on_ring_dismissed)
        self._ring.app_launched.connect(lambda _idx: self._on_ring_dismissed())

        self.setFocusPolicy(Qt.StrongFocus)

        # Fade in
        self.setWindowOpacity(0.0)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(200)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()

        self.show()
        self.setFocus()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Hint text at bottom (inside the ring area)
        painter.setPen(QColor(140, 140, 148, 130))
        font = QFont("Microsoft YaHei", 11)
        painter.setFont(font)
        painter.drawText(
            self.rect().adjusted(0, 0, 0, -18),
            Qt.AlignHCenter | Qt.AlignBottom,
            "按 Esc 或点击右上角 ✕ 关闭预览",
        )
        painter.end()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self._dismiss()
        else:
            super().keyPressEvent(event)

    def _on_ring_dismissed(self) -> None:
        """Called when the ring itself is dismissed."""
        if not self._closing:
            self._dismiss()

    def _dismiss(self) -> None:
        """Hide ring and close backdrop."""
        if self._closing:
            return
        self._closing = True
        if self._ring:
            try:
                if self._ring.isVisible():
                    self._ring.hide_ring()
            except RuntimeError:
                pass
        self._do_close()

    def _do_close(self) -> None:
        if self._ring:
            try:
                self._ring.deleteLater()
            except RuntimeError:
                pass
            self._ring = None
        self.dismissed.emit()
        self.close()
        self.deleteLater()


# =============================================================================
# SettingsDialog  —  modern design
# =============================================================================

class SettingsDialog(QWidget):
    """Modern settings window with card-based layout."""

    config_saved = pyqtSignal()

    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self._config = config
        self._app_rows: List[Tuple[QLineEdit, QLineEdit, QLineEdit]] = []
        self._accent_color = hex_to_qcolor(config.accent_color)
        self._preview_backdrop = None
        self._setup_ui()
        self._load()

    # ── UI construction ────────────────────────────────────────────────

    def _make_card(self, title: str) -> Tuple[QFrame, QVBoxLayout]:
        """Create a styled card frame with a visible title.

        Returns (card_frame, content_layout) — add widgets to content_layout.
        """
        card = QFrame()
        card.setStyleSheet(
            "QFrame#card { background-color: #222228; border: 1px solid #3a3a42; "
            "border-radius: 10px; }"
        )
        card.setObjectName("card")
        outer = QVBoxLayout(card)
        outer.setContentsMargins(16, 12, 16, 14)
        outer.setSpacing(8)

        # Card title
        title_lbl = QLabel(f"<b style='color:#f0f0f0; font-size:14px;'>{title}</b>")
        outer.addWidget(title_lbl)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("QFrame { color: #3a3a42; }")
        outer.addWidget(sep)

        # Content area — caller adds widgets here
        content = QVBoxLayout()
        content.setSpacing(8)
        outer.addLayout(content)

        return card, content

    def _setup_ui(self) -> None:
        self.setWindowTitle(f"{APP_NAME} — 设置")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumSize(820, 680)
        self.resize(860, 720)

        # Main layout
        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(24, 16, 24, 16)

        # Title
        title = QLabel(f"<h2 style='color:#e0e0e0;'>{APP_NAME} 设置</h2>")
        outer.addWidget(title)
        outer.addSpacing(12)

        # Scroll area for all content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        clayout = QVBoxLayout(content)
        clayout.setSpacing(12)
        clayout.setContentsMargins(0, 0, 0, 0)

        # ═══════════════════════════════════════════════════════════════
        # Card 0: Auto-start (highest priority)
        # ═══════════════════════════════════════════════════════════════
        card0, c0 = self._make_card("开机自启 — 最高优先级")

        auto_row = QHBoxLayout()
        self._auto_start_cb = QCheckBox("随 Windows 自动启动 SmartRing")
        self._auto_start_cb.setToolTip(
            "勾选后 SmartRing 会在 Windows 启动时自动运行。\n"
            "此设置为最高优先级，建议保持开启以确保随时可用。"
        )
        self._auto_start_cb.setStyleSheet(
            "QCheckBox { font-size: 15px; font-weight: bold; color: #f0f0f0; spacing: 10px; }"
            "QCheckBox::indicator { width: 22px; height: 22px; }"
        )
        auto_row.addWidget(self._auto_start_cb)
        auto_row.addStretch()
        c0.addLayout(auto_row)

        auto_desc = QLabel(
            "启动项注册在 Windows 启动文件夹中，可通过任务管理器的「启动」选项卡管理。"
        )
        auto_desc.setStyleSheet("color: #999; font-size: 11px; padding-left: 32px;")
        auto_desc.setWordWrap(True)
        c0.addWidget(auto_desc)

        clayout.addWidget(card0)

        # ═══════════════════════════════════════════════════════════════
        # Card 1: Hotkey & Trigger Mode
        # ═══════════════════════════════════════════════════════════════
        card1, c1 = self._make_card("快捷键与触发模式")

        # Row 1: hotkey input (full width)
        hk_row = QHBoxLayout()
        hk_row.addWidget(QLabel("快捷键组合:"))
        self._hotkey_edit = QLineEdit()
        self._hotkey_edit.setPlaceholderText("例如: f12  /  ctrl+f12  /  alt+shift+a")
        self._hotkey_edit.setStyleSheet(
            "QLineEdit { font-family: 'Consolas', 'Courier New', monospace; font-size: 14px; }"
        )
        self._hotkey_edit.textChanged.connect(
            lambda t: self._keyboard_widget.set_hotkey(t)
        )
        hk_row.addWidget(self._hotkey_edit, stretch=1)
        c1.addLayout(hk_row)

        # Row 2: visual keyboard (full width)
        self._keyboard_widget = _KeyboardVisual()
        c1.addWidget(self._keyboard_widget)

        # Row 3: trigger mode + show labels (below keyboard)
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(16)

        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("触发模式:"))
        self._mode_combo = QComboBox()
        self._mode_combo.addItem("Hold — 按住唤出，松开启动", "hold")
        self._mode_combo.addItem("Toggle — 按一下显示，再按隐藏", "toggle")
        self._mode_combo.setMinimumWidth(240)
        self._mode_combo.setStyleSheet(
            "QComboBox { background: #1e1e22; border: 1px solid #444; border-radius: 4px; "
            "padding: 6px 10px; color: #e0e0e0; font-size: 13px; }"
            "QComboBox:hover { border-color: #0078D4; }"
            "QComboBox QAbstractItemView { background: #2b2b30; color: #e0e0e0; "
            "selection-background-color: #0078D4; border: 1px solid #444; }"
        )
        mode_layout.addWidget(self._mode_combo)
        bottom_row.addLayout(mode_layout)

        bottom_row.addSpacing(20)

        self._show_labels_cb = QCheckBox("在圆环中显示应用名称")
        self._show_labels_cb.setToolTip("取消勾选则圆环中只显示图标，不显示应用名")
        self._show_labels_cb.setStyleSheet("QCheckBox { color: #d0d0d5; font-size: 13px; }")
        bottom_row.addWidget(self._show_labels_cb)

        bottom_row.addStretch()
        c1.addLayout(bottom_row)

        clayout.addWidget(card1)

        # ═══════════════════════════════════════════════════════════════
        # Card 2: Appearance
        # ═══════════════════════════════════════════════════════════════
        card2, c2 = self._make_card("外观设置")

        app_row = QHBoxLayout()
        app_row.setSpacing(20)

        # LEFT — live ring preview (larger)
        preview_container = QFrame()
        preview_container.setStyleSheet("QFrame { background: #1a1a1e; border-radius: 8px; }")
        preview_layout = QVBoxLayout(preview_container)
        self._settings_preview = RingPreview(
            ring_radius=self._config.ring_radius,
            center_radius=self._config.center_radius,
            icon_size=self._config.icon_size,
            accent_color=self._config.accent_color,
            bg_color=self._config.bg_color,
        )
        preview_layout.addWidget(self._settings_preview, alignment=Qt.AlignCenter)
        app_row.addWidget(preview_container)

        # RIGHT — controls
        ctrls = QVBoxLayout()
        ctrls.setSpacing(10)

        # Accent colour
        color_label = QLabel("主题色 (高亮):")
        color_label.setStyleSheet("font-weight: bold; color: #ccc;")
        ctrls.addWidget(color_label)
        color_row = QHBoxLayout()
        self._color_swatch = QLabel()
        self._color_swatch.setFixedSize(28, 28)
        self._color_swatch.setStyleSheet(
            f"background-color: {self._config.accent_color}; "
            "border-radius: 6px; border: 2px solid #555;"
        )
        color_row.addWidget(self._color_swatch)
        self._color_edit = QLineEdit(self._config.accent_color)
        self._color_edit.setMaximumWidth(78)
        self._color_edit.textChanged.connect(self._on_color_text_changed)
        color_row.addWidget(self._color_edit)
        pick_btn = QPushButton("...")
        pick_btn.setMaximumWidth(30)
        pick_btn.clicked.connect(self._pick_color)
        color_row.addWidget(pick_btn)
        color_row.addStretch()
        ctrls.addLayout(color_row)

        # Background colour
        bg_label = QLabel("背景色:")
        bg_label.setStyleSheet("font-weight: bold; color: #ccc;")
        ctrls.addWidget(bg_label)
        bg_color_row = QHBoxLayout()
        self._bg_swatch = QLabel()
        self._bg_swatch.setFixedSize(28, 28)
        self._bg_swatch.setStyleSheet(
            f"background-color: {self._config.bg_color}; "
            "border-radius: 6px; border: 2px solid #555;"
        )
        bg_color_row.addWidget(self._bg_swatch)
        self._bg_edit = QLineEdit(self._config.bg_color)
        self._bg_edit.setMaximumWidth(78)
        self._bg_edit.textChanged.connect(self._on_bg_color_text_changed)
        bg_color_row.addWidget(self._bg_edit)
        bg_pick_btn = QPushButton("...")
        bg_pick_btn.setMaximumWidth(30)
        bg_pick_btn.clicked.connect(self._pick_bg_color)
        bg_color_row.addWidget(bg_pick_btn)
        bg_color_row.addStretch()
        ctrls.addLayout(bg_color_row)

        ctrls.addSpacing(2)

        # Size controls
        def _settings_update_preview(*args):
            rr = self._ring_spin.value()
            cr = self._center_spin.value()
            sz = self._icon_spin.value()
            acc = self._color_edit.text().strip() or "#0078D4"

            max_center = max(20, rr - 20)
            self._center_spin.setMaximum(max_center)
            max_icon = max(16, rr - self._center_spin.value())
            self._icon_spin.setMaximum(max_icon)

            if hasattr(self, '_settings_preview'):
                bg = self._bg_edit.text().strip() or "#1e1e26"
                self._settings_preview.set_params(rr, cr, sz, acc, bg)

        size_label = QLabel("圆环尺寸:")
        size_label.setStyleSheet("font-weight: bold; color: #ccc;")
        ctrls.addWidget(size_label)

        size_grid = QGridLayout()
        size_grid.setSpacing(8)
        size_grid.addWidget(QLabel("外环半径:"), 0, 0)
        self._ring_spin = SpinBox(value=self._config.ring_radius, min_val=80, max_val=500, step=5)
        self._ring_spin.set_theme("dark")
        self._ring_spin.textChanged.connect(_settings_update_preview)
        size_grid.addWidget(self._ring_spin, 0, 1)
        size_grid.addWidget(QLabel("px"), 0, 2)

        size_grid.addWidget(QLabel("中心半径:"), 1, 0)
        self._center_spin = SpinBox(value=self._config.center_radius, min_val=20, max_val=250, step=2)
        self._center_spin.set_theme("dark")
        self._center_spin.textChanged.connect(_settings_update_preview)
        size_grid.addWidget(self._center_spin, 1, 1)
        size_grid.addWidget(QLabel("px"), 1, 2)

        size_grid.addWidget(QLabel("图标大小:"), 2, 0)
        self._icon_spin = SpinBox(value=self._config.icon_size, min_val=16, max_val=96, step=2)
        self._icon_spin.set_theme("dark")
        self._icon_spin.textChanged.connect(_settings_update_preview)
        size_grid.addWidget(self._icon_spin, 2, 1)
        size_grid.addWidget(QLabel("px"), 2, 2)

        size_grid.addWidget(QLabel("动画时长:"), 3, 0)
        self._anim_edit = QLineEdit(str(self._config.animation_duration))
        self._anim_edit.setMaximumWidth(60)
        size_grid.addWidget(self._anim_edit, 3, 1)
        size_grid.addWidget(QLabel("ms"), 3, 2)

        ctrls.addLayout(size_grid)
        ctrls.addStretch()
        app_row.addLayout(ctrls)

        c2.addLayout(app_row)
        clayout.addWidget(card2)

        # ═══════════════════════════════════════════════════════════════
        # Card 3: App list (expanded)
        # ═══════════════════════════════════════════════════════════════
        card3, c3 = self._make_card("应用程序列表")

        # Header
        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("名称、路径 — 支持 .exe / .lnk 或任意文件"))
        hdr.addStretch()
        add_btn = QPushButton("+ 添加应用")
        add_btn.setStyleSheet(
            "QPushButton { background-color: #1a6d34; color: white; "
            "border-radius: 4px; padding: 6px 16px; font-weight: bold; }"
            "QPushButton:hover { background-color: #228b41; }"
        )
        add_btn.clicked.connect(lambda: self._add_app_row())
        hdr.addWidget(add_btn)
        c3.addLayout(hdr)

        # Scrollable app rows — generous height, no cap
        app_scroll = QScrollArea()
        app_scroll.setWidgetResizable(True)
        app_scroll.setFrameShape(QFrame.NoFrame)
        app_scroll.setMinimumHeight(200)
        app_scroll.setStyleSheet("QScrollArea { background: #1e1e22; border-radius: 6px; }")
        self._app_container = QWidget()
        self._app_container.setStyleSheet("background: transparent;")
        self._app_layout = QVBoxLayout(self._app_container)
        self._app_layout.setSpacing(5)
        self._app_layout.setContentsMargins(6, 6, 6, 6)
        self._app_layout.addStretch()
        app_scroll.setWidget(self._app_container)
        c3.addWidget(app_scroll, stretch=1)

        clayout.addWidget(card3, stretch=2)

        scroll.setWidget(content)
        outer.addWidget(scroll, stretch=1)

        # ═══════════════════════════════════════════════════════════════
        # Bottom buttons
        # ═══════════════════════════════════════════════════════════════
        outer.addSpacing(10)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch()

        preview_btn = QPushButton("预览圆环")
        preview_btn.setStyleSheet(
            "QPushButton { background-color: #555560; color: #e0e0e0; "
            "border-radius: 6px; padding: 8px 20px; font-size: 13px; min-width: 100px; }"
            "QPushButton:hover { background-color: #666670; }"
        )
        preview_btn.clicked.connect(self._preview_ring_live)
        btn_row.addWidget(preview_btn)

        save_btn = QPushButton("保存设置")
        save_btn.setDefault(True)
        save_btn.setStyleSheet(
            "QPushButton { background-color: #0078D4; color: white; "
            "border-radius: 6px; padding: 8px 20px; font-size: 13px; "
            "font-weight: bold; min-width: 100px; }"
            "QPushButton:hover { background-color: #1084d8; }"
        )
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet(
            "QPushButton { background-color: #3a3a40; color: #d0d0d5; "
            "border-radius: 6px; padding: 8px 20px; font-size: 13px; min-width: 100px; }"
            "QPushButton:hover { background-color: #4a4a50; }"
        )
        cancel_btn.clicked.connect(self.close)
        btn_row.addWidget(cancel_btn)

        outer.addLayout(btn_row)

        # Apply dark theme
        self.setStyleSheet("""
            QWidget {
                background-color: #2b2b30;
                color: #d0d0d5;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                font-size: 13px;
            }
            QLineEdit {
                background-color: #1e1e22;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 5px 8px;
                color: #e0e0e0;
                selection-background-color: #0078D4;
            }
            QLineEdit:focus {
                border-color: #0078D4;
            }
            QPushButton {
                background-color: #3a3a40;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 5px 14px;
                color: #d0d0d5;
            }
            QPushButton:hover {
                background-color: #4a4a50;
            }
            QScrollArea {
                border: none;
            }
            QScrollBar:vertical {
                background: #1e1e22;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #555;
                border-radius: 4px;
                min-height: 30px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QComboBox {
                background-color: #1e1e22;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 5px 8px;
                color: #e0e0e0;
            }
        """)

    def _add_app_row(self, name: str = "", path: str = "", args: str = "") -> None:
        row_widget = QWidget()
        row_widget.setStyleSheet("background: transparent;")
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(6)

        idx_label = QLabel(f"  {len(self._app_rows) + 1}.")
        idx_label.setFixedWidth(28)
        row.addWidget(idx_label)

        name_edit = QLineEdit(name)
        name_edit.setPlaceholderText("应用名称")
        name_edit.setMaximumWidth(130)
        row.addWidget(name_edit)

        path_edit = QLineEdit(path)
        path_edit.setPlaceholderText("程序路径 (.exe / .lnk)")
        row.addWidget(path_edit, stretch=1)

        browse_btn = QPushButton("浏览...")
        browse_btn.setMaximumWidth(60)
        browse_btn.clicked.connect(lambda checked, pe=path_edit: self._browse_file(pe))
        row.addWidget(browse_btn)

        args_edit = QLineEdit(args)
        args_edit.setPlaceholderText("启动参数 (可选)")
        args_edit.setMaximumWidth(120)
        row.addWidget(args_edit)

        del_btn = QPushButton("✕")
        del_btn.setFixedWidth(28)
        del_btn.setStyleSheet(
            "QPushButton { background-color: #5a1a1a; border: 1px solid #6a2a2a; "
            "border-radius: 4px; color: #ff8888; font-weight: bold; }"
            "QPushButton:hover { background-color: #7a2a2a; }"
        )
        del_btn.clicked.connect(lambda: self._del_app_row(row_widget))
        row.addWidget(del_btn)

        # Insert before the stretch
        self._app_layout.insertWidget(self._app_layout.count() - 1, row_widget)
        self._app_rows.append((name_edit, path_edit, args_edit))

    def _del_app_row(self, row_widget: QWidget) -> None:
        # Find and remove the corresponding entry
        layout = row_widget.layout()
        if layout:
            name_e = layout.itemAt(1).widget()
            for i, (ne, pe, ae) in enumerate(self._app_rows):
                if ne is name_e:
                    self._app_rows.pop(i)
                    break
        self._app_layout.removeWidget(row_widget)
        row_widget.deleteLater()

    def _browse_file(self, line_edit: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择应用程序",
            "C:\\",
            "可执行程序 (*.exe *.lnk);;EXE 程序 (*.exe);;快捷方式 (*.lnk);;所有文件 (*.*)",
        )
        if path:
            line_edit.setText(path)

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(self._accent_color, self, "选择主题色")
        if color.isValid():
            self._accent_color = color
            self._color_swatch.setStyleSheet(
                f"background-color: {color.name()}; "
                "border-radius: 6px; border: 1px solid #555;"
            )
            self._color_edit.setText(color.name().upper())
            self._update_settings_preview()

    def _pick_bg_color(self) -> None:
        color = QColorDialog.getColor(
            hex_to_qcolor(self._bg_edit.text() or "#1e1e26"), self, "选择背景色"
        )
        if color.isValid():
            self._bg_swatch.setStyleSheet(
                f"background-color: {color.name()}; "
                "border-radius: 6px; border: 1px solid #555;"
            )
            self._bg_edit.setText(color.name().upper())
            self._update_settings_preview()

    def _on_color_text_changed(self, text: str) -> None:
        try:
            c = hex_to_qcolor(text)
            self._accent_color = c
            self._color_swatch.setStyleSheet(
                f"background-color: {text}; "
                "border-radius: 6px; border: 1px solid #555;"
            )
        except Exception:
            pass
        self._update_settings_preview()

    def _on_bg_color_text_changed(self, text: str) -> None:
        try:
            c = hex_to_qcolor(text)
            self._bg_swatch.setStyleSheet(
                f"background-color: {text}; "
                "border-radius: 6px; border: 1px solid #555;"
            )
        except Exception:
            pass
        self._update_settings_preview()

    def _update_settings_preview(self) -> None:
        """Push current inputs to the live ring preview."""
        if not hasattr(self, '_settings_preview'):
            return
        rr = self._ring_spin.value()
        cr = self._center_spin.value()
        sz = self._icon_spin.value()
        acc = self._color_edit.text().strip() or "#0078D4"
        bg = self._bg_edit.text().strip() or "#1e1e26"
        self._settings_preview.set_params(rr, cr, sz, acc, bg)

    def _load(self) -> None:
        self._hotkey_edit.setText(self._config.hotkey)
        # Set combo box to match current mode
        mode_idx = self._mode_combo.findData(self._config.mode)
        if mode_idx >= 0:
            self._mode_combo.setCurrentIndex(mode_idx)
        self._auto_start_cb.setChecked(self._config.auto_start)
        self._show_labels_cb.setChecked(self._config.show_labels)
        self._ring_spin.setText(str(self._config.ring_radius))
        self._center_spin.setText(str(self._config.center_radius))
        self._icon_spin.setText(str(self._config.icon_size))
        self._anim_edit.setText(str(self._config.animation_duration))
        self._color_edit.setText(self._config.accent_color)
        self._bg_edit.setText(self._config.bg_color)
        # Update keyboard visual
        if hasattr(self, '_keyboard_widget'):
            self._keyboard_widget.set_hotkey(self._config.hotkey)

        for app in self._config.apps:
            self._add_app_row(app.get("name", ""), app.get("path", ""), app.get("args", ""))

    def _save(self) -> None:
        hotkey = self._hotkey_edit.text().strip()
        if not hotkey:
            QMessageBox.warning(self, "错误", "快捷键不能为空")
            return

        try:
            parse_hotkey(hotkey)
        except ValueError as e:
            QMessageBox.warning(self, "快捷键格式错误", str(e))
            return

        ring_r = self._ring_spin.value()
        center_r = self._center_spin.value()
        icon_sz = self._icon_spin.value()

        # ── Size validation ─────────────────────────────────────────
        if center_r >= ring_r:
            QMessageBox.warning(
                self, "尺寸不合理",
                f"中心半径 ({center_r}px) 必须小于外环半径 ({ring_r}px)。\n\n"
                "请调整后再保存。"
            )
            return

        segment_width = ring_r - center_r
        if icon_sz > segment_width:
            QMessageBox.warning(
                self, "尺寸不合理",
                f"图标大小 ({icon_sz}px) 超过了圆环段宽度 ({segment_width}px)。\n\n"
                f"圆环段宽度 = 外环半径({ring_r}px) - 中心半径({center_r}px) = {segment_width}px\n"
                "图标无法放入圆环段内，请减小图标大小或增大圆环段宽度。"
            )
            return

        if icon_sz < 12:
            QMessageBox.warning(
                self, "尺寸不合理",
                f"图标大小 ({icon_sz}px) 过小，无法正常显示。\n请至少设为 12px。"
            )
            return

        self._config.data["hotkey"] = hotkey
        self._config.data["mode"] = self._mode_combo.currentData() or "hold"
        self._config.data["accent_color"] = self._color_edit.text().strip()
        self._config.data["bg_color"] = self._bg_edit.text().strip() or "#1e1e26"
        self._config.data["auto_start"] = self._auto_start_cb.isChecked()
        self._config.data["show_labels"] = self._show_labels_cb.isChecked()

        self._config.data["ring_radius"] = ring_r
        self._config.data["center_radius"] = center_r
        self._config.data["icon_size"] = icon_sz
        try:
            self._config.data["animation_duration"] = int(self._anim_edit.text() or "220")
        except ValueError:
            self._config.data["animation_duration"] = 220

        apps = []
        for name_e, path_e, args_e in self._app_rows:
            name = name_e.text().strip()
            path = path_e.text().strip()
            if name and path:
                apps.append({
                    "name": name,
                    "path": path,
                    "args": args_e.text().strip(),
                    "icon": "",
                })
        self._config.data["apps"] = apps
        self._config.save()

        # Apply auto-start setting
        auto_start = self._auto_start_cb.isChecked()
        set_auto_start(auto_start)

        self.config_saved.emit()

        # Ask whether to preview the ring live
        reply = QMessageBox.question(
            self, "保存成功",
            "配置已保存，快捷键已重新加载。\n\n是否立即预览环形菜单效果？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply == QMessageBox.Yes:
            self._preview_ring_live(then_close=True)
        else:
            self.close()

    def _preview_ring_live(self, then_close: bool = False) -> None:
        """Show the real ring overlay in a centered popup window for preview.

        If then_close is True, close settings when the preview is dismissed
        (used after save). Otherwise re-show settings (used from preview button).
        """
        self.hide()

        apps = []
        for name_e, path_e, args_e in self._app_rows:
            n = name_e.text().strip()
            p = path_e.text().strip()
            if n and p:
                apps.append({"name": n, "path": p, "args": args_e.text().strip(), "icon": ""})
        if not apps:
            apps = self._config.apps

        ring_r = self._ring_spin.value()
        center_r = self._center_spin.value()
        icon_sz = self._icon_spin.value()
        try:
            anim_ms = int(self._anim_edit.text() or "220")
        except ValueError:
            anim_ms = 220
        accent = self._color_edit.text().strip() or "#0078D4"
        bg = self._bg_edit.text().strip() or "#1e1e26"
        show_labels = self._show_labels_cb.isChecked()

        preview_ring = RingOverlay(
            apps=apps,
            ring_radius=ring_r,
            center_radius=center_r,
            icon_size=icon_sz,
            accent_color=accent,
            bg_color=bg,
            animation_duration=anim_ms,
            show_labels=show_labels,
            preview_mode=True,
        )

        # Create backdrop popup, then position ring inside it
        self._preview_backdrop = PreviewBackdrop(preview_ring, ring_r)
        if then_close:
            # From save → close everything when dismissed
            self._preview_backdrop.dismissed.connect(self.close)
        else:
            # From preview button → re-show settings when dismissed
            self._preview_backdrop.dismissed.connect(self._on_preview_dismissed)

        # Position ring at the backdrop's internal ring center
        ring_global = self._preview_backdrop.mapToGlobal(
            self._preview_backdrop._ring_center
        )
        preview_ring.show_at(ring_global)

    def _on_preview_dismissed(self) -> None:
        """Re-show settings dialog after preview backdrop is dismissed."""
        self.show()
        self.raise_()
        self.activateWindow()
        if hasattr(self, '_preview_backdrop') and self._preview_backdrop:
            self._preview_backdrop = None


# =============================================================================
# SpinBox  —  tiny numeric input with +/- buttons for fine-tuning
# =============================================================================

class SpinBox(QWidget):
    """Number input with + / − buttons, emits textChanged like QLineEdit."""
    textChanged = pyqtSignal(str)

    def __init__(
        self, value: int = 190, min_val: int = 30, max_val: int = 800,
        step: int = 5, suffix: str = "", parent=None,
    ):
        super().__init__(parent)
        self._min = min_val
        self._max = max_val
        self._step = step
        self._suffix = suffix
        self._val = value

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)

        # Minus button
        minus = QPushButton("−")
        minus.setFixedSize(24, 24)
        minus.setStyleSheet(
            "QPushButton { background: #ddd; border: 1px solid #bbb; "
            "border-radius: 3px; font-weight: bold; font-size: 14px; color: #333; }"
            "QPushButton:hover { background: #ccc; }"
        )
        minus.clicked.connect(self._decrement)
        layout.addWidget(minus)

        # Number display
        self._edit = QLineEdit(str(value))
        self._edit.setFixedWidth(52)
        self._edit.setAlignment(Qt.AlignCenter)
        self._edit.setStyleSheet(
            "QLineEdit { background: white; border: 1px solid #ccc; "
            "border-radius: 3px; padding: 2px 4px; font-size: 13px; color: #222; }"
        )
        self._edit.textChanged.connect(self._on_text)
        layout.addWidget(self._edit)

        # Suffix label
        if suffix:
            lbl = QLabel(suffix)
            lbl.setStyleSheet("color: #555; font-size: 13px;")
            layout.addWidget(lbl)

        # Plus button
        plus = QPushButton("+")
        plus.setFixedSize(24, 24)
        plus.setStyleSheet(
            "QPushButton { background: #ddd; border: 1px solid #bbb; "
            "border-radius: 3px; font-weight: bold; font-size: 14px; color: #333; }"
            "QPushButton:hover { background: #ccc; }"
        )
        plus.clicked.connect(self._increment)
        layout.addWidget(plus)

        self._minus_btn = minus
        self._plus_btn = plus

    def _increment(self) -> None:
        self._val = min(self._max, self._val + self._step)
        self._edit.blockSignals(True)
        self._edit.setText(str(self._val))
        self._edit.blockSignals(False)
        self.textChanged.emit(str(self._val))

    def _decrement(self) -> None:
        self._val = max(self._min, self._val - self._step)
        self._edit.blockSignals(True)
        self._edit.setText(str(self._val))
        self._edit.blockSignals(False)
        self.textChanged.emit(str(self._val))

    def _on_text(self, text: str) -> None:
        try:
            v = int(text)
            if self._min <= v <= self._max:
                self._val = v
                self.textChanged.emit(text)
        except ValueError:
            pass  # ignore invalid input, keep old value

    def text(self) -> str:
        return self._edit.text()

    def setText(self, text: str) -> None:
        self._edit.blockSignals(True)
        self._edit.setText(text)
        self._edit.blockSignals(False)
        try:
            self._val = int(text)
        except ValueError:
            pass

    def value(self) -> int:
        return self._val

    def setMaximum(self, max_val: int) -> None:
        """Dynamically change the maximum allowed value."""
        self._max = max_val
        if self._val > self._max:
            self._val = self._max
            self._edit.blockSignals(True)
            self._edit.setText(str(self._val))
            self._edit.blockSignals(False)

    def setMinimum(self, min_val: int) -> None:
        """Dynamically change the minimum allowed value."""
        self._min = min_val
        if self._val < self._min:
            self._val = self._min
            self._edit.blockSignals(True)
            self._edit.setText(str(self._val))
            self._edit.blockSignals(False)

    def set_theme(self, theme: str) -> None:
        """Switch button/input colours for light vs dark theme."""
        if theme == "dark":
            btn_style = (
                "QPushButton { background: #3a3a44; border: 1px solid #555; "
                "border-radius: 3px; font-weight: bold; font-size: 14px; color: #ccc; }"
                "QPushButton:hover { background: #4a4a54; }"
            )
            edit_style = (
                "QLineEdit { background: #1e1e22; border: 1px solid #555; "
                "border-radius: 3px; padding: 2px 4px; font-size: 13px; color: #e0e0e0; }"
            )
        else:
            btn_style = (
                "QPushButton { background: #e8e8ec; border: 1px solid #bbb; "
                "border-radius: 3px; font-weight: bold; font-size: 14px; color: #333; }"
                "QPushButton:hover { background: #ddd; }"
            )
            edit_style = (
                "QLineEdit { background: white; border: 1px solid #ccc; "
                "border-radius: 3px; padding: 2px 4px; font-size: 13px; color: #222; }"
            )
        self._minus_btn.setStyleSheet(btn_style)
        self._plus_btn.setStyleSheet(btn_style)
        self._edit.setStyleSheet(edit_style)


# =============================================================================
# RingPreview  —  tiny live-preview of the ring for the wizard
# =============================================================================

class RingPreview(QWidget):
    """Miniature ring painter that updates in real-time as settings change."""

    def __init__(
        self,
        ring_radius: int = 190,
        center_radius: int = 58,
        icon_size: int = 38,
        accent_color: str = "#0078D4",
        bg_color: str = "#1e1e26",
        parent=None,
    ):
        super().__init__(parent)
        self.ring_r = ring_radius
        self.center_r = center_radius
        self.icon_sz = icon_size
        self.accent = accent_color
        self.bg = bg_color
        self.setFixedSize(220, 220)
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2

        # Scale factor: fit the ring in the widget
        margin = 16
        available = (min(w, h) - margin * 2) / 2
        scale = available / (self.ring_r + 24) if self.ring_r > 0 else 1.0

        r_outer = self.ring_r * scale
        r_inner = self.center_r * scale
        r_icon = (r_outer + r_inner) / 2

        acc = hex_to_qcolor(self.accent)
        bg = hex_to_qcolor(self.bg)

        # ── soft backdrop ───────────────────────────────────────────
        halo = QRadialGradient(cx, cy, r_outer + 16)
        halo.setColorAt(0.0, QColor(
            max(0, bg.red() - 20), max(0, bg.green() - 20),
            max(0, bg.blue() - 20), 55))
        halo.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(halo))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPoint(int(cx), int(cy)), int(r_outer + 16), int(r_outer + 16))

        # ── ring body ───────────────────────────────────────────────
        ring_grad = QRadialGradient(cx, cy, r_outer)
        ring_grad.setColorAt(0.0, QColor(
            min(255, bg.red() + 40), min(255, bg.green() + 40),
            min(255, bg.blue() + 40), 235))
        ring_grad.setColorAt(0.5, QColor(
            min(255, bg.red() + 20), min(255, bg.green() + 20),
            min(255, bg.blue() + 20), 230))
        ring_grad.setColorAt(1.0, QColor(
            bg.red(), bg.green(), bg.blue(), 220))
        painter.setBrush(QBrush(ring_grad))
        painter.setPen(QPen(QColor(255, 255, 255, 20), 1))
        painter.drawEllipse(QPoint(int(cx), int(cy)), int(r_outer), int(r_outer))

        # ── dividers (sample segments) ────────────────────────────
        n_sample = getattr(self, '_app_count', 6) or 6
        painter.setPen(QPen(QColor(255, 255, 255, 25), 1))
        for i in range(n_sample):
            a = 2.0 * math.pi * i / n_sample - math.pi / 2.0 - math.pi / n_sample
            ex = int(cx + r_outer * math.cos(a))
            ey = int(cy + r_outer * math.sin(a))
            ix = int(cx + r_inner * math.cos(a))
            iy = int(cy + r_inner * math.sin(a))
            painter.drawLine(ix, iy, ex, ey)

        # ── centre hub ──────────────────────────────────────────────
        hub_grad = QRadialGradient(cx, cy, r_inner)
        hub_grad.setColorAt(0.0, QColor(
            min(255, bg.red() + 50), min(255, bg.green() + 50),
            min(255, bg.blue() + 50), 248))
        hub_grad.setColorAt(1.0, QColor(
            min(255, bg.red() + 20), min(255, bg.green() + 20),
            min(255, bg.blue() + 20), 242))
        painter.setBrush(QBrush(hub_grad))
        painter.setPen(QPen(QColor(255, 255, 255, 18), 1))
        painter.drawEllipse(QPoint(int(cx), int(cy)), int(r_inner), int(r_inner))

        # Accent dot in centre
        painter.setBrush(QBrush(acc))
        painter.setPen(Qt.NoPen)
        dot_r = max(3, r_inner * 0.35)
        painter.drawEllipse(QPoint(int(cx), int(cy)), int(dot_r), int(dot_r))

        # ── sample app dots ─────────────────────────────────────────
        for i in range(n_sample):
            a = 2.0 * math.pi * i / n_sample - math.pi / 2.0
            ix = int(cx + r_icon * math.cos(a))
            iy = int(cy + r_icon * math.sin(a))

            # Tiny coloured dot representing an app icon
            hue = (i * 360 // n_sample) % 360
            dot_color = QColor()
            dot_color.setHsv(hue, 160, 210)
            painter.setBrush(QBrush(dot_color))
            painter.setPen(QPen(QColor(0, 0, 0, 60), 1))
            dot_sz = max(3, self.icon_sz * scale * 0.28)
            painter.drawRoundedRect(
                int(ix - dot_sz), int(iy - dot_sz),
                int(dot_sz * 2), int(dot_sz * 2),
                3, 3,
            )

        painter.end()

    def set_params(self, ring_r: int, center_r: int, icon_sz: int,
                   accent: str, bg: str = "#1e1e26") -> None:
        self.ring_r = ring_r
        self.center_r = center_r
        self.icon_sz = icon_sz
        self.accent = accent
        self.bg = bg
        self.update()

    def set_app_count(self, n: int) -> None:
        """Store app count for divider rendering (hack: store in instance)."""
        self._app_count = n
        self.update()


# =============================================================================
# SetupWizard  —  first-run onboarding
# =============================================================================

class SetupWizard(QDialog):
    """
    Multi-page setup wizard shown on first launch.
    Guides the user through: hotkey → apps → appearance → done.
    """

    ACCENT_COLORS = [
        ("#0078D4", "Windows 蓝"),
        ("#E74856", "珊瑚红"),
        ("#009B5A", "翠绿"),
        ("#F7630C", "活力橙"),
        ("#886CE4", "紫罗兰"),
        ("#00B7C3", "青碧"),
        ("#FFB900", "金黄"),
        ("#D448C3", "品红"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config_data = dict(DEFAULT_CONFIG)
        self._current_page = 0
        self._setup_ui()
        self.setWindowTitle(f"{APP_NAME} — 初始设置")
        self.setMinimumSize(620, 480)
        self.resize(660, 500)
        self.setModal(True)

    def _setup_ui(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background-color: #f5f5f8;
                color: #333;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }
            QLabel#stepLabel {
                color: #aaa;
                font-size: 12px;
            }
            QLabel#stepLabelActive {
                color: #0078D4;
                font-size: 12px;
                font-weight: bold;
            }
            QLabel#titleLabel {
                font-size: 20px;
                font-weight: bold;
                color: #1a1a1e;
            }
            QLabel#descLabel {
                font-size: 13px;
                color: #777;
                line-height: 1.5;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # ── Step indicator bar ──────────────────────────────────────────
        self._step_labels: List[QLabel] = []
        step_bar = QHBoxLayout()
        step_bar.setSpacing(0)
        step_bar.setContentsMargins(40, 18, 40, 10)

        step_names = ["欢迎", "快捷键", "应用", "外观", "完成"]
        for i, name in enumerate(step_names):
            if i > 0:
                sep = QLabel("  ▸  ")
                sep.setStyleSheet("color: #555; font-size: 12px;")
                step_bar.addWidget(sep)
            lbl = QLabel(name)
            lbl.setObjectName("stepLabel")
            step_bar.addWidget(lbl)
            self._step_labels.append(lbl)
        step_bar.addStretch()
        main_layout.addLayout(step_bar)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet("QFrame { color: #ddd; }")
        main_layout.addWidget(div)

        # ── Page stack ──────────────────────────────────────────────────
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("QStackedWidget { background: transparent; }")

        self._stack.addWidget(self._page_welcome())
        self._stack.addWidget(self._page_hotkey())
        self._stack.addWidget(self._page_apps())
        self._stack.addWidget(self._page_appearance())
        self._stack.addWidget(self._page_done())

        main_layout.addWidget(self._stack, stretch=1)

        # ── Bottom nav bar ──────────────────────────────────────────────
        nav = QHBoxLayout()
        nav.setContentsMargins(40, 12, 40, 20)
        nav.setSpacing(12)

        self._back_btn = QPushButton("← 上一步")
        self._back_btn.setMinimumWidth(90)
        self._back_btn.clicked.connect(self._go_back)
        self._back_btn.setVisible(False)
        nav.addWidget(self._back_btn)

        nav.addStretch()

        self._next_btn = QPushButton("下一步 →")
        self._next_btn.setMinimumWidth(110)
        self._next_btn.setDefault(True)
        self._next_btn.clicked.connect(self._go_next)
        nav.addWidget(self._next_btn)

        self._finish_btn = QPushButton("开始使用 SmartRing")
        self._finish_btn.setMinimumWidth(180)
        self._finish_btn.setVisible(False)
        self._finish_btn.clicked.connect(self._finish)
        nav.addWidget(self._finish_btn)

        main_layout.addLayout(nav)

        # Style navigation buttons (light theme)
        btn_style = """
            QPushButton {
                background-color: #0078D4; color: white;
                border-radius: 6px; padding: 8px 20px;
                font-weight: bold; font-size: 13px; border: none;
            }
            QPushButton:hover { background-color: #1084d8; }
            QPushButton:disabled { background-color: #ccc; color: #999; }
        """
        self._next_btn.setStyleSheet(btn_style)
        self._finish_btn.setStyleSheet(btn_style)
        self._back_btn.setStyleSheet(
            "QPushButton { background-color: #e0e0e4; color: #555; "
            "border-radius: 6px; padding: 8px 20px; font-size: 13px; border: 1px solid #ccc; }"
            "QPushButton:hover { background-color: #d0d0d5; }"
        )

        self._update_step()

    # ── Page builders ──────────────────────────────────────────────────

    def _page_welcome(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(60, 30, 60, 30)
        layout.setSpacing(14)

        layout.addStretch()

        # Logo area — big ring icon
        logo = QLabel()
        logo.setFixedSize(100, 100)
        logo.setAlignment(Qt.AlignCenter)
        logo.setPixmap(self._make_logo(100))
        layout.addWidget(logo, alignment=Qt.AlignCenter)

        title = QLabel("欢迎使用 SmartRing")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        desc = QLabel(
            "SmartRing 是受罗技 Action Ring 启发的环形应用启动器。<br><br>"
            "<b>按下快捷键</b> → 光标周围弹出环形菜单 → <b>移动鼠标选择应用</b> → 松开即启动<br><br>"
            "接下来几步将帮助您完成初始设置。"
        )
        desc.setObjectName("descLabel")
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc)

        layout.addStretch()
        return page

    def _page_hotkey(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(60, 20, 60, 20)
        layout.setSpacing(12)

        layout.addStretch()

        title = QLabel("设置快捷键")
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        desc = QLabel("点击下方输入框，然后按下你想要的快捷键组合（例如 F12 或 Ctrl+F12）")
        desc.setObjectName("descLabel")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        layout.addSpacing(10)

        self._hk_capture = KeyCaptureLineEdit()
        self._hk_capture.setFixedHeight(48)
        self._hk_capture.set_hotkey(self._config_data["hotkey"])
        self._hk_capture.key_captured.connect(self._on_hk_captured)
        layout.addWidget(self._hk_capture)

        layout.addSpacing(16)

        # Mode selection
        mode_label = QLabel("触发模式:")
        mode_label.setStyleSheet("font-weight: bold; color: #ccc;")
        layout.addWidget(mode_label)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(16)

        self._mode_hold = QPushButton("Hold 模式\n按住唤出，松开启动")
        self._mode_hold.setCheckable(True)
        self._mode_hold.setChecked(True)
        self._mode_hold.setMinimumHeight(56)
        self._mode_hold.clicked.connect(lambda: self._select_mode("hold"))
        mode_row.addWidget(self._mode_hold)

        self._mode_toggle = QPushButton("Toggle 模式\n按一下显示，再按隐藏")
        self._mode_toggle.setCheckable(True)
        self._mode_toggle.setMinimumHeight(56)
        self._mode_toggle.clicked.connect(lambda: self._select_mode("toggle"))
        mode_row.addWidget(self._mode_toggle)

        layout.addLayout(mode_row)
        self._update_mode_style()

        layout.addStretch()
        return page

    def _select_mode(self, mode: str) -> None:
        self._config_data["mode"] = mode
        self._mode_hold.setChecked(mode == "hold")
        self._mode_toggle.setChecked(mode == "toggle")
        self._update_mode_style()

    def _update_mode_style(self) -> None:
        mode = self._config_data["mode"]
        sel = (
            "QPushButton { background-color: #0078D4; border: 2px solid #005a9e; "
            "border-radius: 8px; color: white; font-size: 12px; padding: 8px; }"
        )
        unsel = (
            "QPushButton { background-color: #f0f0f3; border: 2px solid #ddd; "
            "border-radius: 8px; color: #777; font-size: 12px; padding: 8px; }"
            "QPushButton:hover { border-color: #0078D4; color: #333; }"
        )
        self._mode_hold.setStyleSheet(sel if mode == "hold" else unsel)
        self._mode_toggle.setStyleSheet(sel if mode == "toggle" else unsel)

    def _on_hk_captured(self, hotkey_str: str) -> None:
        self._config_data["hotkey"] = hotkey_str

    def _page_apps(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 16, 40, 16)
        layout.setSpacing(8)

        title = QLabel("配置应用列表")
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        desc = QLabel("添加你常用的应用程序，启动时可从环形菜单中选择。")
        desc.setObjectName("descLabel")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # App table header
        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("名称"))
        hdr.itemAt(0).widget().setMinimumWidth(100)
        hdr.addWidget(QLabel("路径"))
        hdr.addStretch()
        add_btn = QPushButton("＋ 添加应用")
        add_btn.setStyleSheet(
            "QPushButton { background-color: #1a6d34; color: white; "
            "border-radius: 4px; padding: 5px 12px; }"
            "QPushButton:hover { background-color: #228b41; }"
        )
        add_btn.clicked.connect(lambda: self._add_wiz_app())
        hdr.addWidget(add_btn)
        layout.addLayout(hdr)

        # Scrollable app rows
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background: #fafafa; border: 1px solid #ddd; border-radius: 6px; }"
            "QScrollBar:vertical { background: #f0f0f3; width: 8px; border-radius: 4px; }"
            "QScrollBar::handle:vertical { background: #ccc; border-radius: 4px; min-height: 24px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
        )
        scroll.setMaximumHeight(200)
        self._wiz_app_container = QWidget()
        self._wiz_app_container.setStyleSheet("background: transparent;")
        self._wiz_app_layout = QVBoxLayout(self._wiz_app_container)
        self._wiz_app_layout.setSpacing(3)
        self._wiz_app_layout.setContentsMargins(6, 6, 6, 6)
        self._wiz_app_layout.addStretch()
        scroll.setWidget(self._wiz_app_container)
        layout.addWidget(scroll)

        # Pre-fill with defaults
        self._wiz_app_rows: List[Tuple[QLineEdit, QLineEdit]] = []
        for app in self._config_data["apps"]:
            self._add_wiz_app(app["name"], app["path"])

        return page

    def _add_wiz_app(self, name: str = "", path: str = "") -> None:
        row_w = QWidget()
        row_w.setStyleSheet("background: transparent;")
        row = QHBoxLayout(row_w)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(6)

        input_style = (
            "QLineEdit {"
            "  background-color: white;"
            "  border: 1px solid #ccc;"
            "  border-radius: 4px;"
            "  padding: 5px 8px;"
            "  color: #333;"
            "  font-size: 12px;"
            "}"
            "QLineEdit:focus {"
            "  border-color: #0078D4;"
            "  background-color: #fafafe;"
            "}"
            "QLineEdit::placeholder {"
            "  color: #aaa;"
            "}"
        )

        name_e = QLineEdit(name)
        name_e.setPlaceholderText("应用名称")
        name_e.setMaximumWidth(110)
        name_e.setStyleSheet(input_style)
        row.addWidget(name_e)

        path_e = QLineEdit(path)
        path_e.setPlaceholderText("程序路径 (.exe / .lnk)")
        path_e.setStyleSheet(input_style)
        row.addWidget(path_e, stretch=1)

        browse = QPushButton("浏览…")
        browse.setMaximumWidth(55)
        browse.setStyleSheet(
            "QPushButton { background-color: #3a3a44; border: 1px solid #555; "
            "border-radius: 4px; padding: 4px 8px; color: #ccc; font-size: 12px; }"
            "QPushButton:hover { background-color: #4a4a54; }"
        )
        browse.clicked.connect(lambda checked, pe=path_e: self._browse_wiz_file(pe))
        row.addWidget(browse)

        delete = QPushButton("✕")
        delete.setFixedWidth(26)
        delete.setStyleSheet(
            "QPushButton { background-color: #5a1a1a; border: 1px solid #7a2a2a; "
            "border-radius: 3px; color: #ff8888; font-weight: bold; }"
            "QPushButton:hover { background-color: #7a2a2a; }"
        )
        delete.clicked.connect(lambda: self._del_wiz_app(row_w))
        row.addWidget(delete)

        self._wiz_app_layout.insertWidget(self._wiz_app_layout.count() - 1, row_w)
        self._wiz_app_rows.append((name_e, path_e))

    def _del_wiz_app(self, row_w: QWidget) -> None:
        layout = row_w.layout()
        if layout:
            name_e = layout.itemAt(0).widget()
            for i, (ne, pe) in enumerate(self._wiz_app_rows):
                if ne is name_e:
                    self._wiz_app_rows.pop(i)
                    break
        self._wiz_app_layout.removeWidget(row_w)
        row_w.deleteLater()

    def _browse_wiz_file(self, line_edit: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择应用程序", "C:\\",
            "可执行程序 (*.exe *.lnk);;EXE 程序 (*.exe);;快捷方式 (*.lnk);;所有文件 (*.*)",
        )
        if path:
            line_edit.setText(path)

    def _page_appearance(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 16, 40, 16)
        layout.setSpacing(10)

        title = QLabel("外观设置")
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        desc = QLabel("自定义环形菜单的外观，下方预览会<b>实时更新</b>。")
        desc.setObjectName("descLabel")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # ── Main content: left = preview, right = controls ────────────
        content = QHBoxLayout()
        content.setSpacing(20)

        # LEFT — live ring preview
        preview_container = QFrame()
        preview_container.setStyleSheet(
            "QFrame { background-color: #fff; border: 1px solid #ddd; border-radius: 10px; }"
        )
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(10, 10, 10, 10)

        preview_label = QLabel("实时预览")
        preview_label.setStyleSheet("color: #888; font-size: 11px; border: none; background: transparent;")
        preview_label.setAlignment(Qt.AlignCenter)
        preview_layout.addWidget(preview_label)

        r = self._config_data["ring_radius"]
        cr = self._config_data["center_radius"]
        sz = self._config_data["icon_size"]
        acc = self._config_data["accent_color"]
        bg = self._config_data.get("bg_color", "#1e1e26")
        self._ring_preview = RingPreview(r, cr, sz, acc, bg)
        preview_layout.addWidget(self._ring_preview, alignment=Qt.AlignCenter)

        preview_hint = QLabel("← 调整右侧参数实时查看效果")
        preview_hint.setStyleSheet("color: #666; font-size: 10px; border: none;")
        preview_hint.setAlignment(Qt.AlignCenter)
        preview_layout.addWidget(preview_hint)

        content.addWidget(preview_container)

        # RIGHT — controls
        controls = QVBoxLayout()
        controls.setSpacing(10)

        # Accent color grid
        color_label = QLabel("主题色:")
        color_label.setStyleSheet("font-weight: bold; color: #444;")
        controls.addWidget(color_label)

        color_grid = QGridLayout()
        color_grid.setSpacing(6)
        self._color_btns: List[QPushButton] = []
        for i, (hex_code, cname) in enumerate(self.ACCENT_COLORS):
            btn = QPushButton()
            btn.setFixedSize(36, 36)
            btn.setToolTip(cname)
            is_sel = hex_code == self._config_data["accent_color"]
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {hex_code}; border-radius: 18px; "
                f"border: 3px solid {'#222' if is_sel else '#ddd'}; }}"
                f"QPushButton:hover {{ border-color: #555; }}"
            )
            btn.clicked.connect(lambda checked, h=hex_code: self._select_color(h))
            color_grid.addWidget(btn, i // 4, i % 4)
            self._color_btns.append(btn)
        controls.addLayout(color_grid)

        # ── Theme toggle (light / dark) ──────────────────────────────
        theme_label = QLabel("界面主题:")
        theme_label.setStyleSheet("font-weight: bold; color: #444; margin-top: 4px;")
        controls.addWidget(theme_label)

        theme_row = QHBoxLayout()
        theme_row.setSpacing(10)
        self._theme_light = QPushButton("浅色")
        self._theme_light.setCheckable(True)
        self._theme_light.setMinimumHeight(34)
        self._theme_dark = QPushButton("深色")
        self._theme_dark.setCheckable(True)
        self._theme_dark.setMinimumHeight(34)

        cur_theme = self._config_data.get("theme", "dark")
        self._theme_light.setChecked(cur_theme == "light")
        self._theme_dark.setChecked(cur_theme == "dark")
        self._theme_light.clicked.connect(lambda: self._set_theme("light"))
        self._theme_dark.clicked.connect(lambda: self._set_theme("dark"))
        self._update_theme_toggle_style()

        theme_row.addWidget(self._theme_light)
        theme_row.addWidget(self._theme_dark)
        theme_row.addStretch()
        controls.addLayout(theme_row)

        controls.addSpacing(4)

        # ── Ring sizes with SpinBox +/- buttons ──────────────────────
        size_label = QLabel("圆环尺寸:")
        size_label.setStyleSheet("font-weight: bold; color: #444;")
        controls.addWidget(size_label)

        def _update_preview(*args):
            rr = self._ring_spin.value()
            cr2 = self._center_spin.value()
            sz2 = self._icon_spin.value()
            self._config_data["ring_radius"] = rr
            self._config_data["center_radius"] = cr2
            self._config_data["icon_size"] = sz2
            if hasattr(self, '_ring_preview'):
                self._ring_preview.set_params(rr, cr2, sz2,
                    self._config_data["accent_color"],
                    self._config_data.get("bg_color", "#1e1e26"))

        size_grid = QGridLayout()
        size_grid.setSpacing(6)

        size_grid.addWidget(QLabel("外环半径:"), 0, 0)
        self._ring_spin = SpinBox(
            value=self._config_data["ring_radius"], min_val=80, max_val=500, step=5
        )
        self._ring_spin.textChanged.connect(_update_preview)
        size_grid.addWidget(self._ring_spin, 0, 1)

        size_grid.addWidget(QLabel("中心半径:"), 1, 0)
        self._center_spin = SpinBox(
            value=self._config_data["center_radius"], min_val=20, max_val=250, step=2
        )
        self._center_spin.textChanged.connect(_update_preview)
        size_grid.addWidget(self._center_spin, 1, 1)

        size_grid.addWidget(QLabel("图标大小:"), 2, 0)
        self._icon_spin = SpinBox(
            value=self._config_data["icon_size"], min_val=16, max_val=96, step=2
        )
        self._icon_spin.textChanged.connect(_update_preview)
        size_grid.addWidget(self._icon_spin, 2, 1)

        # Show labels toggle
        self._wiz_show_labels = QCheckBox("在圆环中显示应用名称")
        self._wiz_show_labels.setChecked(self._config_data.get("show_labels", True))
        self._wiz_show_labels.setStyleSheet("color: #444; font-size: 12px;")
        self._wiz_show_labels.toggled.connect(
            lambda v: self._config_data.update({"show_labels": v})
        )
        controls.addWidget(self._wiz_show_labels)

        controls.addLayout(size_grid)
        controls.addStretch()

        content.addLayout(controls, stretch=1)
        layout.addLayout(content)

        # Store references for _select_color
        self._r_edit = self._ring_spin  # compatibility alias
        self._cr_edit = self._center_spin
        self._icon_edit = self._icon_spin

        return page

    def _set_theme(self, theme: str) -> None:
        self._config_data["theme"] = theme
        self._theme_light.setChecked(theme == "light")
        self._theme_dark.setChecked(theme == "dark")
        self._update_theme_toggle_style()

    def _update_theme_toggle_style(self) -> None:
        t = self._config_data.get("theme", "dark")
        sel = (
            "QPushButton { background-color: #0078D4; color: white; "
            "border-radius: 6px; padding: 6px 14px; font-weight: bold; border: none; }"
        )
        unsel = (
            "QPushButton { background-color: #e8e8ec; color: #666; "
            "border-radius: 6px; padding: 6px 14px; border: 1px solid #ddd; }"
            "QPushButton:hover { background-color: #ddd; }"
        )
        self._theme_light.setStyleSheet(sel if t == "light" else unsel)
        self._theme_dark.setStyleSheet(sel if t == "dark" else unsel)

    def _select_color(self, hex_code: str) -> None:
        self._config_data["accent_color"] = hex_code
        for btn, (hc, _) in zip(self._color_btns, self.ACCENT_COLORS):
            is_sel = hc == hex_code
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {hc}; border-radius: 18px; "
                f"border: 3px solid {'#222' if is_sel else '#ddd'}; }}"
                f"QPushButton:hover {{ border-color: #555; }}"
            )
        # Update live preview
        if hasattr(self, '_ring_preview'):
            rr = self._ring_spin.value()
            cr2 = self._center_spin.value()
            sz2 = self._icon_spin.value()
            self._ring_preview.set_params(rr, cr2, sz2, hex_code,
                self._config_data.get("bg_color", "#1e1e26"))

    def _page_done(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(60, 30, 60, 30)
        layout.setSpacing(12)

        layout.addStretch()

        check = QLabel("✓")
        check.setStyleSheet("font-size: 48px; color: #009B5A;")
        check.setAlignment(Qt.AlignCenter)
        layout.addWidget(check)

        title = QLabel("设置完成！")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Summary
        summary = (
            f"<p style='color:#ccc;'>"
            f"快捷键: <b style='color:#4af;'>{self._config_data['hotkey'].upper()}</b><br>"
            f"模式: <b>{'Hold (按住)' if self._config_data['mode'] == 'hold' else 'Toggle (切换)'}</b><br>"
            f"应用数量: <b>{len(self._wiz_app_rows)}</b> 个<br>"
            f"主题色: <span style='color:{self._config_data['accent_color']};'>●</span> {self._config_data['accent_color']}"
            f"</p>"
        )
        self._summary_label = QLabel(summary)
        self._summary_label.setWordWrap(True)
        self._summary_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._summary_label)

        tip = QLabel(
            "SmartRing 将在系统托盘中运行。<br>"
            "按下你设置的快捷键即可唤出环形菜单。<br>"
            "右键托盘图标可随时修改设置。"
        )
        tip.setObjectName("descLabel")
        tip.setWordWrap(True)
        tip.setAlignment(Qt.AlignCenter)
        layout.addWidget(tip)

        layout.addSpacing(12)

        # Auto-start checkbox
        self._wiz_auto_start = QCheckBox("开机自启 — 随 Windows 自动启动 SmartRing (推荐)")
        self._wiz_auto_start.setChecked(self._config_data.get("auto_start", False))
        self._wiz_auto_start.setStyleSheet(
            "QCheckBox { font-size: 14px; font-weight: bold; color: #333; }"
            "QCheckBox::indicator { width: 20px; height: 20px; }"
        )
        layout.addWidget(self._wiz_auto_start, alignment=Qt.AlignCenter)

        layout.addStretch()
        return page

    # ── Navigation ─────────────────────────────────────────────────────

    def _update_step(self) -> None:
        for i, lbl in enumerate(self._step_labels):
            if i == self._current_page:
                lbl.setObjectName("stepLabelActive")
            else:
                lbl.setObjectName("stepLabel")
            lbl.style().unpolish(lbl)
            lbl.style().polish(lbl)

        self._stack.setCurrentIndex(self._current_page)
        self._back_btn.setVisible(self._current_page > 0)
        self._next_btn.setVisible(self._current_page < 4)
        self._finish_btn.setVisible(self._current_page == 4)

        # Update next button text
        if self._current_page == 3:
            self._next_btn.setText("查看完成 →")
        else:
            self._next_btn.setText("下一步 →")

        # Update summary on done page
        if self._current_page == 4 and hasattr(self, '_summary_label'):
            summary = (
                f"<p style='color:#ccc;'>"
                f"快捷键: <b style='color:#4af;'>{self._config_data['hotkey'].upper()}</b><br>"
                f"模式: <b>{'Hold (按住唤出)' if self._config_data['mode'] == 'hold' else 'Toggle (切换)'}</b><br>"
                f"应用数量: <b>{len(self._wiz_app_rows)}</b> 个<br>"
                f"主题色: <span style='color:{self._config_data['accent_color']};'>●</span> {self._config_data['accent_color']}"
                f"</p>"
            )
            self._summary_label.setText(summary)

    def _go_back(self) -> None:
        if self._current_page > 0:
            self._current_page -= 1
            self._update_step()

    def _go_next(self) -> None:
        if self._current_page < 4:
            # Save current page data before moving
            if self._current_page == 2:  # apps page
                apps = []
                for name_e, path_e in self._wiz_app_rows:
                    n = name_e.text().strip()
                    p = path_e.text().strip()
                    if n and p:
                        apps.append({"name": n, "path": p, "args": "", "icon": ""})
                if apps:
                    self._config_data["apps"] = apps
            elif self._current_page == 3:  # appearance page
                if hasattr(self, '_ring_spin'):
                    self._config_data["ring_radius"] = self._ring_spin.value()
                    self._config_data["center_radius"] = self._center_spin.value()
                    self._config_data["icon_size"] = self._icon_spin.value()

            self._current_page += 1
            self._update_step()

    def _finish(self) -> None:
        # Save apps
        apps = []
        for name_e, path_e in self._wiz_app_rows:
            n = name_e.text().strip()
            p = path_e.text().strip()
            if n and p:
                apps.append({"name": n, "path": p, "args": "", "icon": ""})
        if apps:
            self._config_data["apps"] = apps

        # Save appearance
        if hasattr(self, '_ring_spin'):
            self._config_data["ring_radius"] = self._ring_spin.value()
            self._config_data["center_radius"] = self._center_spin.value()
            self._config_data["icon_size"] = self._icon_spin.value()
        # Theme is already stored in _config_data["theme"] by _set_theme

        # Save auto_start preference from wizard checkbox
        if hasattr(self, '_wiz_auto_start'):
            self._config_data["auto_start"] = self._wiz_auto_start.isChecked()

        # Write config.json
        cfg_path = config_path()
        try:
            with open(cfg_path, "w", encoding="utf-8") as fh:
                json.dump(self._config_data, fh, indent=2, ensure_ascii=False)
        except OSError:
            QMessageBox.warning(self, "错误", "无法保存配置文件，请检查磁盘权限。")
            return

        # Apply auto-start immediately
        set_auto_start(self._config_data.get("auto_start", False))

        self.accept()

    def _make_logo(self, size: int) -> QPixmap:
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        # Outer ring
        p.setBrush(QBrush(QColor(40, 40, 48)))
        p.setPen(QPen(QColor("#0078D4"), size * 0.06))
        r = size * 0.42
        cx, cy = size / 2, size / 2
        p.drawEllipse(QPoint(int(cx), int(cy)), int(r), int(r))
        # Inner dot
        p.setBrush(QBrush(QColor("#0078D4")))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPoint(int(cx), int(cy)), int(r * 0.38), int(r * 0.38))
        p.end()
        return pix


# =============================================================================
# SmartRingApp  —  main application controller
# =============================================================================

class SmartRingApp(QObject):
    """Top-level controller: tray icon, hotkey listener, ring overlay."""

    def __init__(self, config: ConfigManager) -> None:
        super().__init__()
        self._config = config
        self._ring: Optional[RingOverlay] = None
        self._listener: Optional[pynput_keyboard.Listener] = None
        self._listener_thread: Optional[threading.Thread] = None
        self._pressed = False
        self._was_pressed = False
        self._lock = threading.Lock()

        self._setup_tray()
        self._start_listener()

        # Poll timer bridges pynput (bg thread) → Qt (main thread)
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start(25)

        # Apply auto-start setting on every launch (highest priority)
        set_auto_start(self._config.auto_start)

        # Startup notification
        mode_desc = "按住唤出，松开启动" if self._config.mode == "hold" else "按一下切换"
        self._tray.showMessage(
            APP_NAME,
            f"已就绪！\n快捷键: {self._config.hotkey.upper()}\n模式: {mode_desc}",
            QSystemTrayIcon.Information, 3000,
        )

    # ── tray ─────────────────────────────────────────────────────────────

    def _setup_tray(self) -> None:
        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(self._tray_icon())
        self._tray.setToolTip(f"{APP_NAME}\n快捷键: {self._config.hotkey}")

        menu = QMenu()
        menu.setStyleSheet("""
            QMenu { background-color: #2b2b30; color: #d0d0d5; border: 1px solid #444; }
            QMenu::item:selected { background-color: #0078D4; }
        """)

        settings_action = QAction("设置 (&S)", menu)
        settings_action.triggered.connect(self._open_settings)
        menu.addAction(settings_action)

        menu.addSeparator()

        reload_action = QAction("重新加载配置 (&R)", menu)
        reload_action.triggered.connect(self._reload_config)
        menu.addAction(reload_action)

        menu.addSeparator()

        reset_action = QAction("初始化 — 恢复默认设置", menu)
        reset_action.triggered.connect(self._reset_config)
        menu.addAction(reset_action)

        menu.addSeparator()

        quit_action = QAction("退出 (&Q)", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._tray.show()

        self._tray.activated.connect(self._on_tray_activate)

    def _tray_icon(self) -> QIcon:
        pix = QPixmap(32, 32)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        acc = hex_to_qcolor(self._config.accent_color)
        p.setBrush(QBrush(QColor(50, 50, 55)))
        p.setPen(QPen(acc, 2.5))
        p.drawEllipse(4, 4, 24, 24)
        p.setBrush(QBrush(acc))
        p.setPen(Qt.NoPen)
        p.drawEllipse(11, 11, 10, 10)
        p.end()
        return QIcon(pix)

    def _on_tray_activate(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self._open_settings()

    def _open_settings(self) -> None:
        # Prevent duplicate settings windows
        if hasattr(self, '_settings_dlg') and self._settings_dlg is not None:
            try:
                if self._settings_dlg.isVisible():
                    self._settings_dlg.raise_()
                    self._settings_dlg.activateWindow()
                    return
            except RuntimeError:
                pass  # underlying C++ object was deleted
        dlg = SettingsDialog(self._config)
        self._settings_dlg = dlg
        dlg.config_saved.connect(self._on_config_saved)
        dlg.show()

    def _on_config_saved(self) -> None:
        self._start_listener()
        self._tray.setIcon(self._tray_icon())
        self._tray.setToolTip(f"{APP_NAME}\n快捷键: {self._config.hotkey}")

    def _reload_config(self) -> None:
        self._config.load()
        self._start_listener()
        self._tray.setIcon(self._tray_icon())
        self._tray.setToolTip(f"{APP_NAME}\n快捷键: {self._config.hotkey}")
        self._tray.showMessage(APP_NAME, f"配置已重新加载\n快捷键: {self._config.hotkey}",
                               QSystemTrayIcon.Information, 2000)

    def _reset_config(self) -> None:
        """Reset config.json to factory defaults after confirmation."""
        reply = QMessageBox.question(
            None, "初始化 — 恢复默认设置",
            "确定要将所有设置恢复为默认值吗？\n\n"
            "这将：\n"
            "  - 重置快捷键为 F12\n"
            "  - 重置圆环尺寸和颜色\n"
            "  - 恢复默认应用列表\n"
            "  - 清除开机自启设置\n\n"
            "此操作不可撤销！",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # Second confirmation
        reply2 = QMessageBox.warning(
            None, "确认重置",
            "再次确认：是否确实要初始化所有设置？\n\n"
            "配置文件将被删除并重建为出厂默认值。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply2 != QMessageBox.Yes:
            return

        # Delete config file
        cfg_path = config_path()
        try:
            if os.path.isfile(cfg_path):
                os.remove(cfg_path)
        except OSError as exc:
            self._tray.showMessage(APP_NAME, f"重置失败: {exc}",
                                   QSystemTrayIcon.Warning, 3000)
            return

        # Remove startup shortcut
        set_auto_start(False)

        # Reload (will recreate config from defaults)
        self._config.load()
        self._start_listener()
        self._tray.setIcon(self._tray_icon())
        self._tray.setToolTip(f"{APP_NAME}\n快捷键: {self._config.hotkey}")

        self._tray.showMessage(
            APP_NAME,
            "设置已恢复为默认值。\n\n"
            "快捷键: F12\n"
            "模式: Hold (按住唤出)\n"
            "右键托盘图标可重新配置。",
            QSystemTrayIcon.Information, 5000,
        )

    def _quit(self) -> None:
        self._stop_listener()
        if self._ring and self._ring.isVisible():
            self._ring.hide_ring()
        self._tray.hide()
        QApplication.quit()

    # ── hotkey listener ──────────────────────────────────────────────────

    def _start_listener(self) -> None:
        self._stop_listener()

        try:
            self._modifiers, self._main_key = parse_hotkey(self._config.hotkey)
        except ValueError as e:
            self._tray.showMessage(APP_NAME, f"快捷键配置错误: {e}",
                                   QSystemTrayIcon.Warning, 3000)
            return

        self._current_modifiers: set = set()
        self._main_held = False
        self._pressed = False
        self._was_pressed = False

        def on_press(key):
            with self._lock:
                if key in (Key.ctrl_l, Key.ctrl_r):
                    self._current_modifiers.add(Key.ctrl)
                elif key in (Key.alt_l, Key.alt_r):
                    self._current_modifiers.add(Key.alt)
                elif key in (Key.shift_l, Key.shift_r):
                    self._current_modifiers.add(Key.shift)
                elif key in (Key.cmd_l, Key.cmd_r):
                    self._current_modifiers.add(Key.cmd)
                elif self._key_match(key, self._main_key):
                    self._main_held = True
                if self._check_combo() and not self._pressed:
                    self._pressed = True

        def on_release(key):
            with self._lock:
                if key in (Key.ctrl_l, Key.ctrl_r):
                    self._current_modifiers.discard(Key.ctrl)
                elif key in (Key.alt_l, Key.alt_r):
                    self._current_modifiers.discard(Key.alt)
                elif key in (Key.shift_l, Key.shift_r):
                    self._current_modifiers.discard(Key.shift)
                elif key in (Key.cmd_l, Key.cmd_r):
                    self._current_modifiers.discard(Key.cmd)
                elif self._key_match(key, self._main_key):
                    self._main_held = False
                if not self._check_combo() and self._pressed:
                    self._pressed = False

        self._listener = pynput_keyboard.Listener(
            on_press=on_press,
            on_release=on_release,
        )
        self._listener_thread = threading.Thread(
            target=self._listener.run, daemon=True
        )
        self._listener_thread.start()

    def _stop_listener(self) -> None:
        try:
            if self._listener:
                self._listener.stop()
                self._listener = None
        except Exception:
            pass

    @staticmethod
    def _key_match(key, target) -> bool:
        if key == target:
            return True
        if target == Key.ctrl and key in (Key.ctrl_l, Key.ctrl_r):
            return True
        if target == Key.alt and key in (Key.alt_l, Key.alt_r):
            return True
        if target == Key.shift and key in (Key.shift_l, Key.shift_r):
            return True
        if target == Key.cmd and key in (Key.cmd_l, Key.cmd_r):
            return True
        return False

    def _check_combo(self) -> bool:
        if not self._modifiers.issubset(self._current_modifiers):
            return False
        return self._main_held

    # ── poll ─────────────────────────────────────────────────────────────

    def _poll(self) -> None:
        with self._lock:
            pressed = self._pressed

        just_pressed = pressed and not self._was_pressed
        just_released = not pressed and self._was_pressed
        self._was_pressed = pressed

        ring_visible = self._ring is not None and self._ring.isVisible()

        if just_pressed:
            if not ring_visible:
                self._show_ring()
            elif self._config.mode == "toggle":
                self._ring.hide_ring()
        elif just_released and ring_visible:
            if self._config.mode == "hold":
                self._on_hotkey_release()

    def _show_ring(self) -> None:
        try:
            self._show_ring_impl()
        except Exception as exc:
            self._tray.showMessage(
                APP_NAME, f"显示圆环失败:\n{exc}",
                QSystemTrayIcon.Warning, 3000,
            )

    def _show_ring_impl(self) -> None:
        cursor = QCursor.pos()
        apps = self._config.apps
        if not apps:
            self._tray.showMessage(
                APP_NAME, "应用列表为空！请右键托盘 → 设置，添加至少一个应用。",
                QSystemTrayIcon.Warning, 5000,
            )
            return

        need_recreate = (
            self._ring is None
            or len(getattr(self._ring, '_apps', [])) != len(apps)
        )

        if need_recreate:
            if self._ring:
                try:
                    self._ring._mouse_timer.stop()
                    self._ring.hide()
                except Exception:
                    pass
                self._ring.deleteLater()
                self._ring = None

            self._ring = RingOverlay(
                apps=apps,
                ring_radius=self._config.ring_radius,
                center_radius=self._config.center_radius,
                icon_size=self._config.icon_size,
                accent_color=self._config.accent_color,
                bg_color=self._config.bg_color,
                animation_duration=self._config.animation_duration,
                show_labels=self._config.show_labels,
            )
            self._ring.app_launched.connect(self._on_app_launched)
            self._ring.dismissed.connect(self._on_ring_dismissed)
        else:
            self._ring._ring_r = self._config.ring_radius
            self._ring._center_r = self._config.center_radius
            self._ring._icon_sz = self._config.icon_size
            self._ring._accent = hex_to_qcolor(self._config.accent_color)
            self._ring._bg = hex_to_qcolor(self._config.bg_color)
            self._ring._anim_ms = self._config.animation_duration
            self._ring._show_labels = self._config.show_labels
            self._ring._apps = apps
            self._ring._widget_size = 2 * (self._ring._ring_r + self._ring._label_padding)
            self._ring.resize(self._ring._widget_size, self._ring._widget_size)
            self._ring._preload_icons()

        self._ring.show_at(cursor)

    def _on_hotkey_release(self) -> None:
        if self._ring is None:
            return
        if self._ring._highlighted >= 0 and not self._ring._launched:
            self._ring._launched = True
            self._ring.app_launched.emit(self._ring._highlighted)
        else:
            self._ring.hide_ring()

    def _on_app_launched(self, index: int) -> None:
        app = self._config.apps[index]
        path = app.get("path", "")
        args = app.get("args", "")

        # Hide the ring immediately so it doesn't appear frozen
        if self._ring:
            self._ring.hide_ring()

        if not path:
            self._tray.showMessage(APP_NAME, f"应用 '{app['name']}' 路径为空!",
                                   QSystemTrayIcon.Warning, 2000)
            return

        # Resolve short names (e.g. 'notepad.exe') to full paths
        full_path = resolve_app_path(path)

        # Launch in a deferred manner so the ring hides first
        def _launch():
            try:
                if args:
                    subprocess.Popen(f'"{full_path}" {args}', shell=True)
                else:
                    if sys.platform == "win32":
                        os.startfile(full_path)
                    else:
                        subprocess.Popen([full_path])
            except FileNotFoundError:
                self._tray.showMessage(APP_NAME, f"找不到应用:\n{path}",
                                       QSystemTrayIcon.Warning, 3000)
            except Exception as exc:
                self._tray.showMessage(APP_NAME, f"启动失败: {exc}",
                                       QSystemTrayIcon.Warning, 3000)

        QTimer.singleShot(100, _launch)

    def _on_ring_dismissed(self) -> None:
        pass


# =============================================================================
# Entry point
# =============================================================================

def _check_single_instance() -> bool:
    """Return True if this is the only instance; False if already running."""
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        from ctypes import wintypes

        mutex_name = f"Global\\{APP_NAME}_SingleInstance"
        handle = ctypes.windll.kernel32.CreateMutexW(None, True, mutex_name)
        if handle == 0:
            return True  # can't check, assume ok
        last_error = ctypes.windll.kernel32.GetLastError()
        if last_error == 183:  # ERROR_ALREADY_EXISTS
            ctypes.windll.kernel32.CloseHandle(handle)
            return False
        # Keep the mutex alive by not closing it; it's released on process exit
        return True
    except Exception:
        return True  # if mutex check fails, allow launching


def main() -> int:
    # High-DPI
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_NAME)

    # ── Single-instance check ──────────────────────────────────────────
    if not _check_single_instance():
        QMessageBox.information(
            None, APP_NAME,
            "SmartRing 已在运行中。\n\n请查看系统托盘中的 SmartRing 图标。",
        )
        return 0

    # ── First-run wizard ───────────────────────────────────────────────
    cfg_path = config_path()
    if not os.path.exists(cfg_path):
        wizard = SetupWizard()
        if wizard.exec_() != QDialog.Accepted:
            return 0  # user cancelled setup

    # ── Normal launch ──────────────────────────────────────────────────
    cfg = ConfigManager(cfg_path)
    smartring = SmartRingApp(cfg)

    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
