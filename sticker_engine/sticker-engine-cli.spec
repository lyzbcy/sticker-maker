# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: 打包 A 为单可执行 sticker-engine-cli（含 resources）
# 重新打包（macOS）: cd sticker_engine && source .venv/bin/activate && pyinstaller sticker-engine-cli.spec
# 重新打包（Windows）: cd sticker_engine && .venv\Scripts\activate && pyinstaller sticker-engine-cli.spec
# 产物均为 onedir：dist/sticker-engine-cli/sticker-engine-cli(.exe)
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

hiddenimports = (
    ['sticker_engine', 'sticker_engine.cli']
    + collect_submodules('sticker_engine.agent')
    + collect_submodules('sticker_engine.publish')
    + collect_submodules('flask')
    + collect_submodules('apscheduler')
    + collect_submodules('playwright')
)

datas = [
    ('sticker_engine/resources', 'resources'),
    ('sticker_engine/agent/AGENT_PROMPT.md', 'sticker_engine/agent'),
] + collect_data_files('playwright')

a = Analysis(
    ['cli_entry.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='sticker-engine-cli',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,   # CLI 需要 stdout/stderr（JSON-lines 协议依赖 stdout）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='sticker-engine-cli',
)
