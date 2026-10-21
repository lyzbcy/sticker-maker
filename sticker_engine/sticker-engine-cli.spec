# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: 打包 A 为单可执行 sticker-engine-cli（含 resources）
# 重新打包（macOS）: cd sticker_engine && source .venv/bin/activate && pyinstaller sticker-engine-cli.spec
# 重新打包（Windows）: cd sticker_engine && .venv\Scripts\activate && pyinstaller sticker-engine-cli.spec
# 产物均为 onedir：dist/sticker-engine-cli/sticker-engine-cli(.exe)
from PyInstaller.utils.hooks import collect_data_files, collect_submodules
import sys
import os
import shutil
from pathlib import Path

block_cipher = None

hiddenimports = (
    ['sticker_engine', 'sticker_engine.cli']
    + collect_submodules('sticker_engine.agent')
    + collect_submodules('sticker_engine.publish')
    + collect_submodules('flask')
    + collect_submodules('apscheduler')
    + collect_submodules('playwright')
    + collect_submodules('keyring.backends')
)

datas = [
    ('sticker_engine/resources', 'resources'),
    ('sticker_engine/agent/AGENT_PROMPT.md', 'sticker_engine/agent'),
] + collect_data_files('playwright')
if sys.platform != 'darwin' and os.environ.get('STICKER_BUNDLE_BROWSERS') == '1':
    # Keep downloaded build runtimes outside a Syncthing source checkout when
    # requested; the packaged browser location remains unchanged.
    datas.append((os.environ.get('STICKER_BUILD_BROWSERS','build/browsers'),'browsers'))

a = Analysis(
    ['cli_entry.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
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
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='sticker-engine-cli',
)

# Preserve the already-signed Chromium .app/framework tree on macOS.
# Analysis reclassifies Mach-O resources and tries to sign an incomplete cache
# bundle, which corrupts framework structure. Copy the complete runtime only
# after COLLECT; symlinks and executable modes must survive.
if sys.platform == 'darwin' and os.environ.get('STICKER_BUNDLE_BROWSERS') == '1':
    shutil.copytree(Path(os.environ.get('STICKER_BUILD_BROWSERS', str(Path(SPECPATH)/'build/browsers'))),
                    Path(DISTPATH)/'sticker-engine-cli/_internal/browsers', symlinks=True)
