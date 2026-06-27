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
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── PyQt5 ────────────────────────────────────────────────────────────────────
from PyQt5.QtCore import (
    QEasingCurve,
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
    QColorDialog,
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


def extract_icon(exe_path: str, size: int = 48) -> QIcon:
    """Extract the system icon for a .exe file on Windows."""
    try:
        provider = QFileIconProvider()
        icon = provider.icon(QFileInfo(exe_path))
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
            "QLineEdit { background-color: #1a1a20; border: 2px dashed #555; "
            "border-radius: 6px; padding: 10px 14px; color: #aaa; font-size: 15px; }"
            "QLineEdit:focus { border-color: #0078D4; color: #e0e0e0; }"
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
            "QLineEdit { background-color: #0d1a2d; border: 2px solid #0078D4; "
            "border-radius: 6px; padding: 10px 14px; color: #4af; font-size: 15px; }"
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
            "QLineEdit { background-color: #1a1a20; border: 2px dashed #555; "
            "border-radius: 6px; padding: 10px 14px; color: #aaa; font-size: 15px; }"
            "QLineEdit:focus { border-color: #0078D4; color: #e0e0e0; }"
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
        animation_duration: int = 220,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._apps = apps
        self._ring_r = ring_radius
        self._center_r = center_radius
        self._icon_sz = icon_size
        self._accent = hex_to_qcolor(accent_color)
        self._anim_ms = animation_duration
        self._highlighted: int = -1
        self._anim_highlight: float = -1.0   # animated highlight index (for transitions)
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
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
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
            if icon_path and os.path.isfile(icon_path):
                icon = QIcon(icon_path)
            elif exe_path and os.path.isfile(exe_path):
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

        # Apply drop-shadow to the icon
        pix = self._shadow_icon(pix)

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
        a = angle % (2.0 * math.pi)
        a = (a + math.pi / 2.0) % (2.0 * math.pi)
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
            # Animate the highlight transition
            self._highlight_anim.stop()
            self._highlight_anim.setStartValue(float(old) if old >= 0 else -1.0)
            self._highlight_anim.setEndValue(float(self._highlighted) if self._highlighted >= 0 else -1.0)
            self._highlight_anim.setDuration(120)
            self._highlight_anim.start()
            self.update()

    def _on_highlight_anim(self, value) -> None:
        self._anim_highlight = value
        self.update()

    # ── painting ─────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        cx, cy = self._ring_center.x(), self._ring_center.y()
        n = len(self._apps)
        if n == 0:
            painter.end()
            return

        acc = self._accent
        acc_light = QColor(acc.red(), acc.green(), acc.blue(), 120)

        # ── 1. Outer soft halo ───────────────────────────────────────
        halo = QRadialGradient(cx, cy, self._ring_r + 80)
        halo.setColorAt(0.0, QColor(12, 12, 16, 40))
        halo.setColorAt(0.8, QColor(8, 8, 10, 15))
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

        # Ring gradient — dark with subtle radial lightening toward centre
        ring_grad = QRadialGradient(cx, cy, self._ring_r)
        ring_grad.setColorAt(0.0, QColor(40, 40, 46, 235))
        ring_grad.setColorAt(0.55, QColor(32, 32, 38, 230))
        ring_grad.setColorAt(0.85, QColor(24, 24, 28, 225))
        ring_grad.setColorAt(1.0, QColor(18, 18, 20, 215))
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

        if hi >= 0:
            seg_angle = 2.0 * math.pi / n
            angle_center = self._app_angle(hi)
            angle_start = angle_center - seg_angle / 2.0
            angle_span = seg_angle

            # Highlight glow (larger, softer)
            glow_wedge = QPainterPath()
            glow_wedge.moveTo(cx, cy)
            glow_wedge.arcTo(
                cx - self._ring_r, cy - self._ring_r,
                self._ring_r * 2, self._ring_r * 2,
                int(-math.degrees(angle_start) * 16),
                int(-math.degrees(angle_span) * 16),
            )
            glow_wedge.closeSubpath()
            highlight_area = glow_wedge.intersected(ring_body).subtracted(hub)

            # Gradient for the highlighted segment
            hi_grad = QConicalGradient(cx, cy, -math.degrees(angle_center))
            hi_grad.setColorAt(0.0, QColor(acc.red(), acc.green(), acc.blue(), 200))
            hi_grad.setColorAt(0.5, QColor(acc.red(), acc.green(), acc.blue(), 170))
            hi_grad.setColorAt(1.0, QColor(acc.red(), acc.green(), acc.blue(), 200))
            painter.fillPath(highlight_area, QBrush(hi_grad))

            # Highlight outer arc
            painter.setPen(QPen(acc_light, 2.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawArc(
                cx - self._ring_r, cy - self._ring_r,
                self._ring_r * 2, self._ring_r * 2,
                int(-math.degrees(angle_start) * 16),
                int(-math.degrees(angle_span) * 16),
            )

            # Highlight inner arc
            painter.setPen(QPen(acc_light, 1.5))
            painter.drawArc(
                cx - self._center_r, cy - self._center_r,
                self._center_r * 2, self._center_r * 2,
                int(-math.degrees(angle_start) * 16),
                int(-math.degrees(angle_span) * 16),
            )

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
        hub_grad.setColorAt(0.0, QColor(50, 50, 58, 248))
        hub_grad.setColorAt(1.0, QColor(32, 32, 38, 242))
        painter.setBrush(QBrush(hub_grad))
        painter.setPen(QPen(QColor(255, 255, 255, 15), 1))
        painter.drawEllipse(QPoint(cx, cy), self._center_r, self._center_r)

        # Inner accent ring inside hub
        painter.setPen(QPen(QColor(acc.red(), acc.green(), acc.blue(), 60), 2))
        painter.setBrush(Qt.NoBrush)
        inner_r = self._center_r - 12
        painter.drawEllipse(QPoint(cx, cy), inner_r, inner_r)

        # Centre text
        painter.setPen(QColor(220, 220, 225))
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

            # Icon
            ipos = self._app_position(i, icon_r)
            pix = self._app_icon_pixmap(i)
            if not pix.isNull():
                pw, ph = pix.width(), pix.height()
                offset_x, offset_y = pw // 2, ph // 2
                # Slightly scale up highlighted icon
                scale = 1.08 if is_hi else 1.0
                if scale != 1.0:
                    sw, sh = int(pw * scale), int(ph * scale)
                    scaled = pix.scaled(sw, sh, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    painter.drawPixmap(
                        ipos.x() - sw // 2, ipos.y() - sh // 2, sw, sh, scaled,
                    )
                else:
                    painter.drawPixmap(
                        ipos.x() - offset_x, ipos.y() - offset_y, pw, ph, pix,
                    )

            # Label
            lpos = self._app_position(i, label_r)
            name = self._apps[i]["name"]

            label_font = QFont("Microsoft YaHei", 9, QFont.Bold if is_hi else QFont.Normal)
            painter.setFont(label_font)
            fm = QFontMetrics(label_font)
            text_w = fm.horizontalAdvance(name)
            th = fm.height()

            if is_hi:
                # Label background pill
                pill_w, pill_h = text_w + 14, th + 5
                pill_rect = QRect(lpos.x() - pill_w // 2, lpos.y() - pill_h // 2, pill_w, pill_h)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(QColor(acc.red(), acc.green(), acc.blue(), 200)))
                painter.drawRoundedRect(pill_rect, 8, 8)
                painter.setPen(QColor(255, 255, 255))
            else:
                painter.setPen(QColor(210, 210, 215))

            painter.drawText(
                QRect(lpos.x() - text_w // 2, lpos.y() - th // 2, text_w, th),
                Qt.AlignCenter, name,
            )

        painter.end()

    # ── events ───────────────────────────────────────────────────────────

    def mouseMoveEvent(self, event) -> None:
        self._update_highlight(event.pos())
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._highlighted >= 0:
            self._launched = True
            self.app_launched.emit(self._highlighted)
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.hide_ring()
        super().keyPressEvent(event)


# =============================================================================
# Settings Dialog  —  modern design
# =============================================================================

class SettingsDialog(QWidget):
    """Modern settings window with card-based layout."""

    config_saved = pyqtSignal()

    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self._config = config
        self._app_rows: List[Tuple[QLineEdit, QLineEdit, QLineEdit]] = []
        self._accent_color = hex_to_qcolor(config.accent_color)
        self._setup_ui()
        self._load()

    # ── UI construction ────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setWindowTitle(f"{APP_NAME} — 设置")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumSize(700, 560)
        self.resize(720, 600)

        # Main layout
        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(24, 20, 24, 20)

        # Title
        title = QLabel(f"<h2 style='color:#e0e0e0;'>⚙ {APP_NAME} 设置</h2>")
        outer.addWidget(title)
        outer.addSpacing(16)

        # Scroll area for all content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        clayout = QVBoxLayout(content)
        clayout.setSpacing(14)
        clayout.setContentsMargins(0, 0, 0, 0)

        # ── Card: Hotkey & Mode ──────────────────────────────────────
        card1 = self._make_card("⌨ 快捷键设置")
        grid1 = QGridLayout()
        grid1.setSpacing(10)
        grid1.addWidget(QLabel("快捷键组合:"), 0, 0)
        self._hotkey_edit = QLineEdit()
        self._hotkey_edit.setPlaceholderText("例如: f12  /  ctrl+f12  /  alt+shift+a")
        self._hotkey_edit.setMinimumWidth(200)
        grid1.addWidget(self._hotkey_edit, 0, 1)

        grid1.addWidget(QLabel("触发模式:"), 0, 2)
        self._mode_combo = QLineEdit()
        self._mode_combo.setPlaceholderText("hold 或 toggle")
        self._mode_combo.setMaximumWidth(100)
        self._mode_combo.setToolTip("hold = 按住唤出, 松开启动\n"
                                    "toggle = 按一下切换显示/隐藏")
        grid1.addWidget(self._mode_combo, 0, 3)
        grid1.setColumnStretch(1, 2)
        card1.setLayout(grid1)
        clayout.addWidget(card1)

        # ── Card: Appearance ─────────────────────────────────────────
        card2 = self._make_card("🎨 外观设置")
        grid2 = QGridLayout()
        grid2.setSpacing(10)

        # Accent colour
        grid2.addWidget(QLabel("主题色:"), 0, 0)
        self._color_swatch = QLabel()
        self._color_swatch.setFixedSize(32, 32)
        self._color_swatch.setStyleSheet(
            f"background-color: {self._config.accent_color}; "
            "border-radius: 6px; border: 1px solid #555;"
        )
        grid2.addWidget(self._color_swatch, 0, 1)
        self._color_edit = QLineEdit(self._config.accent_color)
        self._color_edit.setMaximumWidth(80)
        self._color_edit.textChanged.connect(self._on_color_text_changed)
        grid2.addWidget(self._color_edit, 0, 2)
        pick_btn = QPushButton("选择颜色...")
        pick_btn.clicked.connect(self._pick_color)
        grid2.addWidget(pick_btn, 0, 3)

        # Ring sizes
        grid2.addWidget(QLabel("外环半径:"), 1, 0)
        self._ring_r_edit = QLineEdit(str(self._config.ring_radius))
        self._ring_r_edit.setMaximumWidth(70)
        grid2.addWidget(self._ring_r_edit, 1, 1)
        grid2.addWidget(QLabel("px"), 1, 2)

        grid2.addWidget(QLabel("中心半径:"), 1, 3)
        self._center_r_edit = QLineEdit(str(self._config.center_radius))
        self._center_r_edit.setMaximumWidth(70)
        grid2.addWidget(self._center_r_edit, 1, 4)
        grid2.addWidget(QLabel("px"), 1, 5)

        grid2.addWidget(QLabel("图标大小:"), 2, 0)
        self._icon_sz_edit = QLineEdit(str(self._config.icon_size))
        self._icon_sz_edit.setMaximumWidth(70)
        grid2.addWidget(self._icon_sz_edit, 2, 1)
        grid2.addWidget(QLabel("px"), 2, 2)

        grid2.addWidget(QLabel("动画时长:"), 2, 3)
        self._anim_edit = QLineEdit(str(self._config.animation_duration))
        self._anim_edit.setMaximumWidth(70)
        grid2.addWidget(self._anim_edit, 2, 4)
        grid2.addWidget(QLabel("ms"), 2, 5)

        card2.setLayout(grid2)
        clayout.addWidget(card2)

        # ── Card: App list ───────────────────────────────────────────
        card3 = self._make_card("📱 应用程序列表")
        app_outer = QVBoxLayout()
        app_outer.setSpacing(6)

        # Header
        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("<i>名称、路径 — 路径支持 .exe / .lnk 或任意文件</i>"))
        hdr.addStretch()
        add_btn = QPushButton("＋ 添加应用")
        add_btn.setStyleSheet(
            "QPushButton { background-color: #1a6d34; color: white; "
            "border-radius: 4px; padding: 5px 14px; }"
            "QPushButton:hover { background-color: #228b41; }"
        )
        add_btn.clicked.connect(lambda: self._add_app_row())
        hdr.addWidget(add_btn)
        app_outer.addLayout(hdr)

        # Scrollable app rows
        app_scroll = QScrollArea()
        app_scroll.setWidgetResizable(True)
        app_scroll.setFrameShape(QFrame.NoFrame)
        app_scroll.setMaximumHeight(280)
        app_scroll.setStyleSheet("QScrollArea { background: #1e1e22; border-radius: 6px; }")
        self._app_container = QWidget()
        self._app_container.setStyleSheet("background: transparent;")
        self._app_layout = QVBoxLayout(self._app_container)
        self._app_layout.setSpacing(4)
        self._app_layout.setContentsMargins(4, 4, 4, 4)
        self._app_layout.addStretch()
        app_scroll.setWidget(self._app_container)
        app_outer.addWidget(app_scroll)

        card3.setLayout(app_outer)
        clayout.addWidget(card3, stretch=1)

        scroll.setWidget(content)
        outer.addWidget(scroll, stretch=1)

        # ── Bottom buttons ───────────────────────────────────────────
        outer.addSpacing(12)
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        save_btn = QPushButton("💾 保存设置")
        save_btn.setDefault(True)
        save_btn.setMinimumWidth(120)
        save_btn.setStyleSheet(
            "QPushButton { background-color: #0078D4; color: white; "
            "border-radius: 6px; padding: 8px 22px; font-weight: bold; }"
            "QPushButton:hover { background-color: #1084d8; }"
        )
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.setMinimumWidth(80)
        cancel_btn.clicked.connect(self.close)
        btn_row.addWidget(cancel_btn)

        outer.addLayout(btn_row)

        # Apply dark theme to the dialog
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
        """)

    def _make_card(self, title: str) -> QFrame:
        """Create a styled card frame with a title."""
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background-color: #222228; border: 1px solid #3a3a42; "
            "border-radius: 10px; padding: 14px; }"
        )
        # We'll set the layout externally — just return the frame
        return card

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
            "可执行文件 (*.exe *.lnk *.bat *.cmd);;所有文件 (*.*)",
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

    def _load(self) -> None:
        self._hotkey_edit.setText(self._config.hotkey)
        self._mode_combo.setText(self._config.mode)
        self._ring_r_edit.setText(str(self._config.ring_radius))
        self._center_r_edit.setText(str(self._config.center_radius))
        self._icon_sz_edit.setText(str(self._config.icon_size))
        self._anim_edit.setText(str(self._config.animation_duration))
        self._color_edit.setText(self._config.accent_color)

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

        self._config.data["hotkey"] = hotkey
        self._config.data["mode"] = self._mode_combo.text().strip() or "hold"
        self._config.data["accent_color"] = self._color_edit.text().strip()

        try:
            self._config.data["ring_radius"] = int(self._ring_r_edit.text() or "190")
        except ValueError:
            self._config.data["ring_radius"] = 190
        try:
            self._config.data["center_radius"] = int(self._center_r_edit.text() or "58")
        except ValueError:
            self._config.data["center_radius"] = 58
        try:
            self._config.data["icon_size"] = int(self._icon_sz_edit.text() or "38")
        except ValueError:
            self._config.data["icon_size"] = 38
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
        self.config_saved.emit()
        QMessageBox.information(self, "已保存", "配置已保存，快捷键已重新加载。")
        self.close()


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
                background-color: #1e1e24;
                color: #d0d0d5;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }
            QLabel#stepLabel {
                color: #888;
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
                color: #e8e8ec;
            }
            QLabel#descLabel {
                font-size: 13px;
                color: #999;
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
        div.setStyleSheet("QFrame { color: #333; }")
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

        self._finish_btn = QPushButton("🎯 开始使用 SmartRing")
        self._finish_btn.setMinimumWidth(180)
        self._finish_btn.setVisible(False)
        self._finish_btn.clicked.connect(self._finish)
        nav.addWidget(self._finish_btn)

        main_layout.addLayout(nav)

        # Style navigation buttons
        btn_style = """
            QPushButton {
                background-color: #0078D4; color: white;
                border-radius: 6px; padding: 8px 20px;
                font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background-color: #1084d8; }
            QPushButton:disabled { background-color: #444; color: #888; }
        """
        self._next_btn.setStyleSheet(btn_style)
        self._finish_btn.setStyleSheet(btn_style)
        self._back_btn.setStyleSheet(
            "QPushButton { background-color: #3a3a42; color: #ccc; "
            "border-radius: 6px; padding: 8px 20px; font-size: 13px; }"
            "QPushButton:hover { background-color: #4a4a52; }"
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

        self._mode_hold = QPushButton("🖐 Hold 模式\n按住唤出，松开启动")
        self._mode_hold.setCheckable(True)
        self._mode_hold.setChecked(True)
        self._mode_hold.setMinimumHeight(56)
        self._mode_hold.clicked.connect(lambda: self._select_mode("hold"))
        mode_row.addWidget(self._mode_hold)

        self._mode_toggle = QPushButton("🔘 Toggle 模式\n按一下显示，再按隐藏")
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
            "QPushButton { background-color: #0d2a45; border: 2px solid #0078D4; "
            "border-radius: 8px; color: white; font-size: 12px; padding: 8px; }"
        )
        unsel = (
            "QPushButton { background-color: #2a2a32; border: 2px solid #444; "
            "border-radius: 8px; color: #999; font-size: 12px; padding: 8px; }"
            "QPushButton:hover { border-color: #666; color: #ccc; }"
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
        scroll.setStyleSheet("QScrollArea { background: #1a1a20; border-radius: 6px; }")
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
        row.setContentsMargins(0, 1, 0, 1)
        row.setSpacing(6)

        name_e = QLineEdit(name)
        name_e.setPlaceholderText("应用名称")
        name_e.setMaximumWidth(110)
        row.addWidget(name_e)

        path_e = QLineEdit(path)
        path_e.setPlaceholderText("程序路径")
        row.addWidget(path_e, stretch=1)

        browse = QPushButton("浏览…")
        browse.setMaximumWidth(55)
        browse.clicked.connect(lambda checked, pe=path_e: self._browse_wiz_file(pe))
        row.addWidget(browse)

        delete = QPushButton("✕")
        delete.setFixedWidth(26)
        delete.setStyleSheet(
            "QPushButton { background-color: #5a1a1a; border-radius: 3px; "
            "color: #f88; font-weight: bold; }"
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
            "可执行文件 (*.exe *.lnk *.bat *.cmd);;所有文件 (*.*)",
        )
        if path:
            line_edit.setText(path)

    def _page_appearance(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(60, 20, 60, 20)
        layout.setSpacing(12)

        layout.addStretch()

        title = QLabel("外观设置")
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        desc = QLabel("自定义环形菜单的外观，以后随时可以在设置中修改。")
        desc.setObjectName("descLabel")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        layout.addSpacing(10)

        # Accent color grid
        color_label = QLabel("主题色:")
        color_label.setStyleSheet("font-weight: bold; color: #ccc;")
        layout.addWidget(color_label)

        color_grid = QGridLayout()
        color_grid.setSpacing(8)
        self._color_btns: List[QPushButton] = []
        for i, (hex_code, cname) in enumerate(self.ACCENT_COLORS):
            btn = QPushButton()
            btn.setFixedSize(44, 44)
            btn.setToolTip(cname)
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {hex_code}; border-radius: 22px; "
                f"border: 3px solid {'#fff' if hex_code == self._config_data['accent_color'] else 'transparent'}; }}"
                f"QPushButton:hover {{ border-color: #fff; }}"
            )
            btn.clicked.connect(lambda checked, h=hex_code: self._select_color(h))
            color_grid.addWidget(btn, i // 4, i % 4)
            self._color_btns.append(btn)
        layout.addLayout(color_grid)

        layout.addSpacing(14)

        # Ring size
        size_row = QHBoxLayout()
        size_row.setSpacing(16)
        size_row.addWidget(QLabel("圆环半径:"))
        self._r_edit = QLineEdit(str(self._config_data["ring_radius"]))
        self._r_edit.setMaximumWidth(70)
        size_row.addWidget(self._r_edit)
        size_row.addWidget(QLabel("px"))

        size_row.addWidget(QLabel("图标大小:"))
        self._icon_edit = QLineEdit(str(self._config_data["icon_size"]))
        self._icon_edit.setMaximumWidth(70)
        size_row.addWidget(self._icon_edit)
        size_row.addWidget(QLabel("px"))
        size_row.addStretch()
        layout.addLayout(size_row)

        layout.addStretch()
        return page

    def _select_color(self, hex_code: str) -> None:
        self._config_data["accent_color"] = hex_code
        for btn, (hc, _) in zip(self._color_btns, self.ACCENT_COLORS):
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {hc}; border-radius: 22px; "
                f"border: 3px solid {'#fff' if hc == hex_code else 'transparent'}; }}"
                f"QPushButton:hover {{ border-color: #fff; }}"
            )

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
                try:
                    self._config_data["ring_radius"] = int(self._r_edit.text() or "190")
                except ValueError:
                    pass
                try:
                    self._config_data["icon_size"] = int(self._icon_edit.text() or "38")
                except ValueError:
                    pass

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
        try:
            self._config_data["ring_radius"] = int(self._r_edit.text() or "190")
        except ValueError:
            pass
        try:
            self._config_data["icon_size"] = int(self._icon_edit.text() or "38")
        except ValueError:
            pass

        # Write config.json
        cfg_path = config_path()
        try:
            with open(cfg_path, "w", encoding="utf-8") as fh:
                json.dump(self._config_data, fh, indent=2, ensure_ascii=False)
        except OSError:
            QMessageBox.warning(self, "错误", "无法保存配置文件，请检查磁盘权限。")
            return

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

        settings_action = QAction("⚙ 设置 (&S)", menu)
        settings_action.triggered.connect(self._open_settings)
        menu.addAction(settings_action)

        menu.addSeparator()

        reload_action = QAction("🔄 重新加载配置 (&R)", menu)
        reload_action.triggered.connect(self._reload_config)
        menu.addAction(reload_action)

        menu.addSeparator()

        quit_action = QAction("❌ 退出 (&Q)", menu)
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
        cursor = QCursor.pos()
        apps = self._config.apps
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
                animation_duration=self._config.animation_duration,
            )
            self._ring.app_launched.connect(self._on_app_launched)
            self._ring.dismissed.connect(self._on_ring_dismissed)
        else:
            self._ring._ring_r = self._config.ring_radius
            self._ring._center_r = self._config.center_radius
            self._ring._icon_sz = self._config.icon_size
            self._ring._accent = hex_to_qcolor(self._config.accent_color)
            self._ring._anim_ms = self._config.animation_duration
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

        if not path:
            self._tray.showMessage(APP_NAME, f"应用 '{app['name']}' 路径为空!",
                                   QSystemTrayIcon.Warning, 2000)
            if self._ring:
                self._ring.hide_ring()
            return

        try:
            if args:
                subprocess.Popen(f'"{path}" {args}', shell=True)
            else:
                if sys.platform == "win32":
                    os.startfile(path)
                else:
                    subprocess.Popen([path])
        except FileNotFoundError:
            self._tray.showMessage(APP_NAME, f"找不到应用:\n{path}",
                                   QSystemTrayIcon.Warning, 3000)
        except Exception as exc:
            self._tray.showMessage(APP_NAME, f"启动失败: {exc}",
                                   QSystemTrayIcon.Warning, 3000)

        if self._ring:
            self._ring.hide_ring()

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
