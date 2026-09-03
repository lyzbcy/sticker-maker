import os
from pathlib import Path
from typing import Optional
from .schema import Config, Prefs, ModeProbsConfig
from .paths import resolve_paths, current_platform

try:
    import yaml
except ImportError:
    yaml = None


def load_prefs_from_file(prefs_path: Path) -> Optional[Prefs]:
    """从 prefs.yaml 读用户偏好（前情提要）。文件不存在返回 None（首次启动）。"""
    if prefs_path is None or not Path(prefs_path).exists() or yaml is None:
        return None
    with open(prefs_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    mp = data.get("mode_probs", {})
    return Prefs(
        mode_probs=ModeProbsConfig(
            single=mp.get("single", 0.5), duo=mp.get("duo", 0.3),
            trio=mp.get("trio", 0.0), quad=mp.get("quad", 0.2)),
        single_char_probs=data.get("single_char_probs", {}),
        base_probs=data.get("base_probs", {}),
        grid_size=data.get("grid_size", 4),
        transparent_default=data.get("transparent_default", True),
        ref_lib_priority=data.get("ref_lib_priority", True),
        ref_consume=data.get("ref_consume", True),
        story_mode=data.get("story_mode", True),
        reference_lib_path=data.get("reference_lib_path"),
        default_series_id=data.get("default_series_id"),
        prompt_set_id=data.get("prompt_set_id"),
        vision_calls=data.get("vision_calls", False),
        browser_headless=data.get("browser_headless", False),
        sticker_price=int(data.get("sticker_price", 0) or 0),
    )


def save_prefs(prefs: Prefs, prefs_path: Path) -> None:
    prefs_path.parent.mkdir(parents=True, exist_ok=True)
    mp = prefs.mode_probs
    data = {
        "mode_probs": {"single": mp.single, "duo": mp.duo, "trio": mp.trio, "quad": mp.quad},
        "single_char_probs": prefs.single_char_probs,
        "base_probs": prefs.base_probs,
        "grid_size": prefs.grid_size,
        "transparent_default": prefs.transparent_default,
        "ref_lib_priority": prefs.ref_lib_priority,
        "ref_consume": prefs.ref_consume,
        "story_mode": prefs.story_mode,
        "reference_lib_path": prefs.reference_lib_path,
        "default_series_id": prefs.default_series_id,
        "prompt_set_id": prefs.prompt_set_id,
        "vision_calls": prefs.vision_calls,
        "browser_headless": prefs.browser_headless,
        "sticker_price": prefs.sticker_price,
    }
    if yaml is None:
        raise RuntimeError("PyYAML 未安装")
    with open(prefs_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
