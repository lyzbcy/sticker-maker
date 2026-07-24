import random
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
from ..pipeline.context import PipelineContext, LogEntry
from ..config.schema import normalize_probs


@dataclass
class PrepResult:
    episode_dir: Path
    characters: list
    mode: str   # single/duo/trio/quad


def _pick_by_probs(options: dict, rng: random.Random) -> str:
    """按概率字典抽一个 key。options={key: prob}。"""
    items = list(options.items())
    r = rng.random()
    acc = 0.0
    for k, p in items:
        acc += p
        if r <= acc:
            return k
    return items[-1][0]


class PrepStage:
    """S0：建目录、选模式/角色/base、写角色卡、产出 prep_state。"""

    def __init__(self, seed: int = None):
        self.rng = random.Random(seed)

    def run(self, ctx: PipelineContext) -> None:
        prefs = ctx.config.prefs
        # 1) 选模式
        mode = ctx.episode.forced_mode or _pick_by_probs({
            "single": prefs.mode_probs.single, "duo": prefs.mode_probs.duo,
            "trio": prefs.mode_probs.trio, "quad": prefs.mode_probs.quad,
        }, self.rng)
        # 2) 选角色（按模式取数量）
        mode_count = {"single": 1, "duo": 2, "trio": 3, "quad": 4}[mode]
        if ctx.episode.forced_characters:
            chars = ctx.episode.forced_characters[:mode_count]
        else:
            chars = self._pick_characters(ctx, mode, mode_count)
        # 3) 建 episode 目录
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        episode_dir = ctx.config.paths.output_root / f"episode_{ts}"
        episode_dir.mkdir(parents=True, exist_ok=True)
        for sub in ["原图", "最终版", "参考图"]:
            (episode_dir / sub).mkdir(exist_ok=True)
        ctx.episode_dir = episode_dir
        # 4) 写角色卡
        contains_laoyu = "捞鱼" in chars
        (episode_dir / "本次制作角色.md").write_text(
            f"# 本次制作角色\n\n角色：{'、'.join(chars)}\n含捞鱼：{'是' if contains_laoyu else '否'}\n",
            encoding="utf-8")
        # 5) 日志
        ctx.log(LogEntry(stage="S0", status="OK",
                         message=f"准备完成：模式={mode} 角色={chars} 目录={episode_dir.name}"))

    def _pick_characters(self, ctx, mode, count):
        all_chars = list(ctx.config.characters.keys())
        # 角色库为空（如 placeholder 配置）时直接返回空列表，保持管线可运行
        if not all_chars:
            return []
        if mode == "single":
            probs = ctx.config.prefs.single_char_probs or {c: 1.0/len(all_chars) for c in all_chars}
            probs = normalize_probs(probs)
            return [_pick_by_probs(probs, self.rng)]
        else:
            probs = ctx.config.prefs.single_char_probs or {c: 1.0 for c in all_chars}
            pool = list(all_chars)
            self.rng.shuffle(pool)
            pool.sort(key=lambda c: -probs.get(c, 0))
            return pool[:count]
