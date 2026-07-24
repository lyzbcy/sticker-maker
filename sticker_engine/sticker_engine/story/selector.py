import random
from typing import List, Optional

from .library import Script


class StoryPoolDepleted(Exception):
    """剧本池耗尽（可选抛出，调用方也可直接判断空列表降级）。"""


class StorySelector:
    """
    移植自 generate_from_prep_state.pick_linkage_scripts：
    - 角色严格匹配（剧本 characters 必须等于本弹角色集合）
    - 已用剧本永久淘汰
    - 不足时返回少于 n 个（调用方据此降级）

    设计意图：避免单人弹（characters=["星星布丁"]）误选双人剧本
    （characters=["星星布丁","捞鱼"]）。旧逻辑用 any() 会把含该角色的双人剧
    也匹配上，此处改为严格相等。
    """

    def __init__(self, scripts: list, used: Optional[set] = None):
        self.scripts = list(scripts)
        self.used = set(used) if used else set()

    def pick(
        self,
        n: int,
        characters: Optional[list] = None,
        seed: Optional[int] = None,
    ) -> list:
        """选 n 组剧本。

        - 严格匹配角色：set(s.characters) == set(characters)；空 characters 的
          通配剧本在严格模式下被排除。
        - 无严格匹配时回退到全部剧本（调用方应据此 WARN/降级）。
        - 已用剧本永久排除；不足 n 个时返回全部可用（可为空列表）。
        - seed 使随机洗牌可测。
        """
        target = set(characters) if characters else None

        # 角色严格匹配
        if target is not None:
            candidate = []
            for s in self.scripts:
                sc = set(s.characters)
                if sc and sc == target:   # 通配（characters 空）在严格模式下排除
                    candidate.append(s)
            if not candidate:
                # 没有严格匹配的，放宽到全部（WARN 由调用方处理）
                candidate = list(self.scripts)
        else:
            candidate = list(self.scripts)

        available = [s for s in candidate if s.id not in self.used]
        rng = random.Random(seed)
        rng.shuffle(available)
        picked = available[:n]
        for s in picked:
            self.used.add(s.id)
        return picked
