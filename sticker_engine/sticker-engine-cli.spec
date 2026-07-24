# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: 打包 A 为单可执行 sticker-engine-cli（含 resources）
# 重新打包：cd sticker_engine && source .venv/bin/activate && pyinstaller sticker-engine-cli.spec

block_cipher = None

a = Analysis(
    ['sticker_engine/cli.py'],
    pathex=[],
    binaries=[],
    datas=[('sticker_engine/resources', 'resources')],   # 含 base 图/剧本库/关键词库（修 A 评审 C3）
    hiddenimports=['sticker_engine'],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='sticker-engine-cli',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
