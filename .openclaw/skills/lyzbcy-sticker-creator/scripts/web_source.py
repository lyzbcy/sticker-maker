"""Resolve the current Sticker Maker source; do not vendor engine algorithms."""
import os,sys
from pathlib import Path

def source_root():
    candidates = ([Path(os.environ['STICKER_MAKER_ROOT'])] if os.environ.get('STICKER_MAKER_ROOT') else []) + list(Path(__file__).resolve().parents)
    for root in candidates:
        if (root/'sticker_engine/sticker_engine/stages/assets.py').is_file():
            sys.path.insert(0,str(root/'sticker_engine'))
            return root
    raise RuntimeError('Use this skill inside the current sticker-maker checkout, or set STICKER_MAKER_ROOT to it. No copied-engine fallback.')

PROJECT_ROOT=source_root()
