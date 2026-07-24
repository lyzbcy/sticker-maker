import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union


@dataclass
class Panel:
    cn: str
    en: str
    emotion: str
    action: str


@dataclass
class Script:
    id: str
    name: str
    type: str
    characters: list   # list[str]
    panels: list       # list[Panel]
    link_note: str = ""


@dataclass
class LinkageLibrary:
    scripts: list   # list[Script]

    @classmethod
    def load(cls, path: Optional[Union[str, Path]] = None) -> "LinkageLibrary":
        """加载联动剧本库 JSON。

        - 文件缺失或 path 为 None 时返回空库（调用方据此降级，不抛异常）。
        - 容错读取：每条 script 的 panels 元素必须包含 cn/en/emotion/action 四字段，
          缺字段时跳过该 panel（不阻断整库加载）。
        """
        if path is None or not Path(path).exists():
            return cls(scripts=[])
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        scripts = []
        for s in data.get("scripts", []):
            panels = []
            for p in s.get("panels", []):
                try:
                    panels.append(Panel(
                        cn=p.get("cn", ""),
                        en=p.get("en", ""),
                        emotion=p.get("emotion", ""),
                        action=p.get("action", ""),
                    ))
                except (AttributeError, TypeError):
                    continue
            scripts.append(Script(
                id=s.get("id", s.get("name", "")),
                name=s.get("name", ""),
                type=s.get("type", ""),
                characters=list(s.get("characters", [])),
                panels=panels,
                link_note=s.get("link_note", ""),
            ))
        return cls(scripts=scripts)
