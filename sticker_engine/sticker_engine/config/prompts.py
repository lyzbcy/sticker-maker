"""Prompt 方案（多套可切换，2026-08-28）。

设计：
- 方案存 %APPDATA%/StickerEngine/prompts/*.json，一套 = {
      id, name, style_block,          # 覆盖内置 STYLE_BLOCK
      combo_extra, story_extra, ref_extra   # 各模式追加指令（可空）
  }
- 内置兜底方案 default 来自 templates.py 常量（萌系大头规格）——用户文件
  缺失/损坏时永远有可用方案。
- 生成时（GenerateStage）按 prefs.prompt_set_id 套用：style_block 替换 +
  extra 追加。prompt 因此完全数据化：用户可改，AI（拿到打分反馈后）也可改。
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ..resources.prompts.templates import (
    _STYLE_BLOCK, REF_LIBRARY_TEMPLATE, STORY_TEMPLATE, KEYWORD_COMBO_TEMPLATE)

BUILTIN_ID = "builtin-2026-08-28-moe"
BUILTIN_STANDARD_ID = "builtin-standard"

# 标准版风格块（2026-08-27 萌系升级之前的规格：1:1 头身、不带眼位/腮红/无关节细节）
_STANDARD_STYLE_BLOCK = (
    "STYLE (strictly identical across all panels):\n"
    "- Chibi aesthetic: exaggerated expressive big eyes, soft rounded facial "
    "lines, large head-to-body ratio (about 1:1)\n"
    "- 3D clay style, soft matte clay material, soft studio lighting\n"
    "- Each sticker gets a uniform thin white outline (die-cut sticker look) "
    "and a clean margin around it inside its cell\n"
    "- Every character fully visible inside its own cell: no cropped "
    "limbs/tails/hair, nothing floating or detached, no extra stray elements\n"
    "- Characters must never touch or cross the grid divider lines: keep "
    "completely empty background gutters between neighboring cells\n"
    "- Background: solid magenta (#ff00ff), completely flat — no shadows, "
    "no gradients, no scenery\n"
    "- Absolutely no text, letters, numbers or watermarks in any panel"
)


def is_builtin(set_id: str) -> bool:
    return set_id in (BUILTIN_ID, BUILTIN_STANDARD_ID)


def _prompts_dir(user_data: Path) -> Path:
    return user_data / "prompts"


@dataclass
class PromptSet:
    """一套生图方案。extra_* 会追加到对应模式模板末尾（STYLE 之前不保证，简单追加）。"""
    id: str
    name: str
    style_block: str = ""
    combo_extra: str = ""
    story_extra: str = ""
    ref_extra: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return dict(id=self.id, name=self.name, style_block=self.style_block,
                    combo_extra=self.combo_extra, story_extra=self.story_extra,
                    ref_extra=self.ref_extra, updated_at=self.updated_at)

    @classmethod
    def from_dict(cls, d: dict) -> "PromptSet":
        return cls(
            id=str(d.get("id") or ""),
            name=str(d.get("name") or "未命名方案"),
            style_block=str(d.get("style_block") or ""),
            combo_extra=str(d.get("combo_extra") or ""),
            story_extra=str(d.get("story_extra") or ""),
            ref_extra=str(d.get("ref_extra") or ""),
            updated_at=str(d.get("updated_at") or ""),
        )


def builtin_set() -> PromptSet:
    """内置默认：萌系大头规格（templates.py 的 STYLE_BLOCK）。"""
    return PromptSet(
        id=BUILTIN_ID, name="萌系大头（内置）",
        style_block=_STYLE_BLOCK, updated_at="builtin")


def builtin_standard_set() -> PromptSet:
    """内置第二套：标准版（萌系升级前的规格，供对比/偏好选择）。"""
    return PromptSet(
        id=BUILTIN_STANDARD_ID, name="标准版（内置）",
        style_block=_STANDARD_STYLE_BLOCK, updated_at="builtin")


def _safe_id(name: str) -> str:
    slug = re.sub(r"[\W_]+", "-", str(name)).strip("-").lower()
    return slug or f"set-{int(time.time())}"


def list_sets(user_data: Path) -> List[PromptSet]:
    """全部方案：用户文件 + 内置两套（萌系大头默认 / 标准版，均不可删）。"""
    sets: List[PromptSet] = []
    d = _prompts_dir(user_data)
    if d.exists():
        for f in sorted(d.glob("*.json")):
            try:
                sets.append(PromptSet.from_dict(json.loads(f.read_text(encoding="utf-8"))))
            except (json.JSONDecodeError, OSError):
                continue   # 坏文件跳过，不让一个坏方案拖垮列表
    sets.append(builtin_set())
    sets.append(builtin_standard_set())
    return sets


def save_set(user_data: Path, data: dict) -> PromptSet:
    """新建/更新一套（按 id 匹配；无 id/内置 id 时按名字生成）。"""
    d = _prompts_dir(user_data)
    d.mkdir(parents=True, exist_ok=True)
    ps = PromptSet.from_dict(data)
    if not ps.id or is_builtin(ps.id):
        ps.id = _safe_id(ps.name)
    # 同 id 覆盖；名字撞车加后缀
    existing = {s.id: s.name for s in list_sets(user_data)}
    if ps.id in existing and data.get("id") != ps.id:
        ps.id = f"{ps.id}-{int(time.time()) % 10000}"
    ps.updated_at = time.strftime("%Y-%m-%d %H:%M:%S")
    (d / f"{ps.id}.json").write_text(
        json.dumps(ps.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return ps


def delete_set(user_data: Path, set_id: str) -> bool:
    if is_builtin(set_id):
        return False   # 内置不可删
    f = _prompts_dir(user_data) / f"{set_id}.json"
    if f.exists():
        f.unlink()
        return True
    return False


def find_set(user_data: Path, set_id: Optional[str]) -> PromptSet:
    """按 id 找方案；找不到/未指定 → 内置。"""
    if set_id:
        for s in list_sets(user_data):
            if s.id == set_id:
                return s
    return builtin_set()


def apply_set(template_kind: str, ps: PromptSet) -> str:
    """把方案套到某模式模板上：替换 STYLE_BLOCK + 追加 extra。

    template_kind: "ref_library" | "story" | "keyword_combo"
    """
    base = {"ref_library": REF_LIBRARY_TEMPLATE,
            "story": STORY_TEMPLATE,
            "keyword_combo": KEYWORD_COMBO_TEMPLATE}[template_kind]
    # 替换 STYLE 块（模板以 _STYLE_BLOCK 结尾）
    if ps.style_block and base.endswith(_STYLE_BLOCK):
        base = base[: -len(_STYLE_BLOCK)] + ps.style_block
    extra = {"ref_library": ps.ref_extra, "story": ps.story_extra,
             "keyword_combo": ps.combo_extra}[template_kind]
    if extra:
        base = base + "\n" + extra
    return base
