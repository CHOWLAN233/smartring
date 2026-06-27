# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for SmartRing — single-file Windows executable.
"""

block_cipher = None

a = Analysis(
    ['smartring.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        # pynput internals
        'pynput.keyboard._win32',
        'pynput.mouse._win32',
        # PyQt5 platform & plugins
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        'PyQt5.sip',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SmartRing',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='smartring.ico',   # our ring icon
)
