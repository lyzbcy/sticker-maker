import enum
import random
import shutil
import time
from pathlib import Path
from typing import Optional
from ..pipeline.context import PipelineContext, LogEntry
from ..providers.codex import CodexProvider
from ..resources.prompts.templates import (
    REF_LIBRARY_TEMPLATE, STORY_TEMPLATE, KEYWORD_COMBO_TEMPLATE)


# ---- IP 身份门禁（2026-08-27 事故复盘）----
# 当日一单排列组合模式：codex 会话 input_image=0（-i 参考图被静默丢弃），
# 模型凭空造出非 IP 角色且全程无报错，差点流到发布环节。对策：
# 每次生成后立刻识图对比「成图 vs base」，不同角色 → 强化提示重试 1 次 → 仍不同则明确失败。
IDENTITY_CHECK_PROMPT = (
    "Image 1 is a generated sticker sheet; image 2 is the official base reference of the "
    "character that MUST appear in every panel.\n"
    "Question: do all panels of image 1 depict the SAME character design as image 2 "
    "(same species, same hairstyle and hair color, same outfit, same color palette)?\n"
    "Answer with exactly YES or NO as the first line, then one short sentence of reason."
)

_IDENTITY_RETRY_PREFIX = (
    "URGENT IDENTITY CORRECTION: a previous attempt drew a WRONG invented character. "
    "Copy the character design EXACTLY from the attached reference image(s): same species, "
    "same hairstyle and hair color, same outfit, same color palette. "
    "Inventing a different character means total failure.\n"
)


class GenerationMode(enum.Enum):
    REF_LIBRARY = "ref_library"
    STORY = "story"
    KEYWORD_COMBO = "keyword_combo"


class GenerateStage:
    """S1：三模式分派 → 拼 prompt → 调 codex → 捞图。"""

    MODE_LABELS = {
        GenerationMode.REF_LIBRARY: "参考图库",
        GenerationMode.STORY: "故事模式",
        GenerationMode.KEYWORD_COMBO: "排列组合",
    }

    def __init__(self, codex: CodexProvider, story_selector=None, keywords=None, seed=None):
        self.codex = codex
        self.story_selector = story_selector   # Task 5 的 StorySelector
        self.keywords = keywords               # dict: {emotions, actions, backgrounds}
        self.rng = random.Random(seed)

    def _emit(self, ctx, message: str) -> None:
        """发细粒度进度（做什么/输入/输出/在等什么）。runner 注入，可能为 None。"""
        cb = getattr(ctx, "stage_progress", None)
        if cb is not None:
            try:
                cb(message)
            except Exception:
                pass

    def decide_mode(self, ctx: PipelineContext) -> GenerationMode:
        prefs = ctx.config.prefs
        grid = ctx.episode.grid_size
        n = grid * grid
        # 参考图库优先（且够数）
        if prefs.ref_lib_priority and self._count_refs(ctx) >= n:
            return GenerationMode.REF_LIBRARY
        # 故事模式（按 episode 意图决定；selector 缺失/池耗尽在 _build 阶段降级，决策 L）
        if ctx.episode.story_mode:
            return GenerationMode.STORY
        # 降级/默认：排列组合
        return GenerationMode.KEYWORD_COMBO

    def _count_refs(self, ctx) -> int:
        ref_lib = ctx.config.paths.reference_lib
        if not ref_lib.exists():
            return 0
        return len([p for p in ref_lib.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg")])

    def run(self, ctx: PipelineContext) -> None:
        t0 = time.time()
        mode = self.decide_mode(ctx)
        ctx.gen_mode = mode.value   # C1 修复：把决出的 mode 写进 ctx，供 S2 决定抠图策略
        self._emit(ctx, f"生成模式已选定：{self.MODE_LABELS[mode]}")
        # 可观测性：开了参考图优先却没走成时，把原因说清楚
        # （2026-08-27 用户疑问"数量够为什么没走参考图模式"——当时是验证期
        # 临时关了开关；但此类情况不该让用户猜，直接报库存数）
        if ctx.config.prefs.ref_lib_priority and mode != GenerationMode.REF_LIBRARY:
            have = self._count_refs(ctx)
            need = ctx.episode.grid_size * ctx.episode.grid_size
            self._emit(ctx,
                       f"参考图库优先已开启，但库存 {have} 张 < 需要 {need} 张，"
                       f"自动改用{self.MODE_LABELS[mode]}（可往参考图库补图）")
        prompt, refs = self._build_prompt_and_refs(ctx, mode)
        bases = self._gather_bases(ctx)
        chars = "、".join(ctx.selected_characters) if ctx.selected_characters else "默认角色"
        self._emit(ctx, f"输入就绪：prompt {len(prompt)} 字 · 参考图 {len(refs)} 张 · 角色[{chars}]")
        grid_src = self._generate_with_identity_gate(ctx, mode, prompt, refs, bases)
        if grid_src is None:
            ctx.grid_image = None
            return
        # 复制到 episode 目录
        dst = ctx.episode_dir / "原图" / f"grid_{ctx.episode.grid_size}x{ctx.episode.grid_size}.png"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(grid_src, dst)
        ctx.grid_image = dst
        size_kb = dst.stat().st_size // 1024
        self._emit(ctx, f"输出就绪：{dst.name}（{size_kb} KB，耗时 {int(time.time() - t0)}s）")
        ctx.log(LogEntry(stage="S1", status="OK", message=f"生图完成 mode={mode.value} → {dst.name}"))
        # 参考图=弹药：成功后把用过的库图归档（复用会产出雷同贴纸，2026-08-27 产品定型）
        if mode == GenerationMode.REF_LIBRARY and getattr(ctx.config.prefs, "ref_consume", True):
            self._archive_used_refs(ctx, refs, bases)

    def _archive_used_refs(self, ctx, refs, bases) -> None:
        """把本次用过的参考图（库部分，不含 base）移入 参考图库/_used_日期/。"""
        base_set = {str(b) for b in (bases or [])}
        used = [Path(r) for r in refs if str(r) not in base_set]
        used = [u for u in used if u.exists()
                and ctx.config.paths.reference_lib in u.parents]
        if not used:
            return
        import datetime
        archive = (ctx.config.paths.reference_lib /
                   f"_used_{datetime.datetime.now():%Y%m%d}")
        archive.mkdir(parents=True, exist_ok=True)
        n = 0
        for u in used:
            dst = archive / u.name
            i = 2
            while dst.exists():
                dst = archive / f"{u.stem}-{i}{u.suffix}"
                i += 1
            try:
                u.rename(dst)
                n += 1
            except OSError:
                pass   # 移不动（占用等）就留着，不影响主流程
        left = self._count_refs(ctx)
        self._emit(ctx, f"参考图库：{n} 张已用完归档（_used_{datetime.datetime.now():%Y%m%d}/），"
                        f"剩余 {left} 张——复用同一批参考图会产出雷同贴纸，打完可在详情页「回流参考图库」补弹")

    def _generate_with_identity_gate(self, ctx, mode, prompt, refs, bases):
        """生图 + IP 身份门禁：最多 2 次尝试，生成后校验成图与 base 是否同一角色。

        - 第 1 次不过 → 带 _IDENTITY_RETRY_PREFIX 重试 1 次
        - 重试仍不过 → 记 FAIL、返回 None（本单作废，绝不带着错角色进 S2/发布）
        - 无 base 可比对 / 识图无回复 → WARN 性质放行（可用性优先，日志留痕）
        """
        why = ""
        for attempt in range(2):
            cur_prompt = prompt if attempt == 0 else _IDENTITY_RETRY_PREFIX + prompt
            if attempt > 0:
                self._emit(ctx, f"上次未通过（{why[:80]}），强化身份提示后重试…")
            # 生图（长等待：每 5 秒心跳报告"在等什么"）
            self._emit(ctx, "正在调用 codex 生图（首次调用可能需要 1~3 分钟，请稍候）…")
            def _beat(elapsed, tail):
                msg = f"等待 codex 响应… 已等 {elapsed}s"
                if tail:
                    msg += f"｜codex 输出：{tail[-120:]}"
                self._emit(ctx, msg)
            grid = self.codex.generate(prompt=cur_prompt, refs=refs, on_wait=_beat)
            if grid is None:
                detail = getattr(self.codex, "last_error", "") or "未知原因"
                self._emit(ctx, f"codex 生图失败：{detail}")
                ctx.log(LogEntry(stage="S1", status="FAIL",
                                 message=f"codex 生图失败（mode={mode.value}）：{detail}"))
                return None
            # 废图质检：参考图被 codex 丢弃时，偶发产出全黑/纯色图（2026-08-27 实测）
            if not self._grid_sanity_ok(grid):
                why = "生成的网格图异常（全黑/纯色废图），疑似 codex 生成失败"
                self._emit(ctx, f"{why}，尝试重试…")
                continue
            ok, note = self._check_identity(ctx, grid, bases)
            if ok:
                self._emit(ctx, f"IP 校验：{note}")
                return grid
            why = note
        ctx.log(LogEntry(stage="S1", status="FAIL",
                         message=f"生成质量/IP 校验连续未通过（已重试）：{why}"))
        self._emit(ctx, f"重试后仍未通过，本单已中止：{why}")
        return None

    def _grid_sanity_ok(self, grid_path) -> bool:
        """成图基础质检：>98% 像素同值视为纯色废图（全黑/全白）。读不出图不阻断。"""
        try:
            from PIL import Image
            im = Image.open(grid_path)
            im.load()
            hist = im.convert("L").histogram()
            total = im.size[0] * im.size[1]
            return max(hist) / max(total, 1) <= 0.98
        except Exception:
            return True

    def _check_identity(self, ctx, grid_path, bases):
        """识图对比成图与 base。返回 (ok, note)，note 人类可读进活动流。"""
        if not bases:
            return True, "无 base 参考图可比对，跳过校验（留痕）"
        ans = ""
        try:
            ans = self.codex.exec_text(IDENTITY_CHECK_PROMPT,
                                       refs=[grid_path] + list(bases), timeout=180)
        except Exception:
            ans = ""
        if not isinstance(ans, str):   # 测试桩/MagicMock 兜底
            ans = ""
        head = ans.strip().splitlines()[0].upper() if ans.strip() else ""
        if head.startswith("YES"):
            return True, "成图与 base 为同一角色 ✓"
        if head.startswith("NO"):
            return False, "成图角色与 base 不是同一角色（" + " ".join(ans.strip().split())[:100] + "）"
        ctx.log(LogEntry(stage="S1", status="WARN",
                         message="IP 校验识图无明确回复，放行并留痕"))
        return True, "识图无明确回复，本次放行（留痕）"

    def _gather_bases(self, ctx) -> list:
        """本次要保真的角色 base 图（单/多人）。"""
        selected_bases = list(getattr(ctx, "selected_bases", []) or [])
        if not selected_bases:
            base_path = self._pick_base(ctx)
            selected_bases = [base_path] if base_path else []
        return selected_bases

    def _build_prompt_and_refs(self, ctx: PipelineContext, mode: GenerationMode):
        grid = ctx.episode.grid_size
        n = grid * grid
        selected_bases = self._gather_bases(ctx)
        refs = selected_bases
        prompt = ""

        if mode == GenerationMode.REF_LIBRARY:
            n_img = n + len(selected_bases)
            prompt = REF_LIBRARY_TEMPLATE.format(grid=grid, n=n, n_img=n_img)
            refs += self._pick_refs(ctx, n)
        elif mode == GenerationMode.STORY:
            # selector 未注入或池耗尽 → 降级 combo（决策 L）
            if self.story_selector is None:
                ctx.log(LogEntry(stage="S1", status="WARN", message="未提供剧本选择器，降级到排列组合模式"))
                mode = GenerationMode.KEYWORD_COMBO
                stories = []
            else:
                stories = self.story_selector.pick(
                    n=grid, characters=ctx.selected_characters, seed=self.rng.random())
            if mode == GenerationMode.STORY and not stories:
                # 池耗尽 → 降级 combo（决策 L）
                ctx.log(LogEntry(stage="S1", status="WARN", message="剧本池耗尽，降级到排列组合模式"))
                mode = GenerationMode.KEYWORD_COMBO
            else:
                desc = " | ".join(
                    f"Row{i+1}: " + " → ".join(p.cn for p in s.panels[:grid])
                    for i, s in enumerate(stories))
                prompt = STORY_TEMPLATE.format(grid=grid, n=n, stories_description=desc)
        if mode == GenerationMode.KEYWORD_COMBO:
            panels_desc = self._random_combo_panels(ctx, n)
            prompt = KEYWORD_COMBO_TEMPLATE.format(grid=grid, n=n, panels_description=panels_desc)
        if ctx.selected_characters:
            identity = "、".join(
                f"image {i + 1}={name}"
                for i, name in enumerate(ctx.selected_characters)
            )
            # 2026-08-27 强化：参考图被 codex 偶发丢弃时，模型会自创角色；
            # 把身份要求提到最前并显式禁止"发明新角色"。
            prompt = (
                "CRITICAL: draw ONLY the exact character(s) shown in the reference image(s) "
                f"— character identity in order: {identity}. "
                "Match species, hairstyle, hair color, outfit and color palette precisely; "
                "never invent, merge or substitute a different character design. "
                + prompt
            )
        return prompt, refs

    def _pick_base(self, ctx) -> Optional[Path]:
        # I6 修复：用 PrepStage 按 base_probs 选好的 base（ctx.selected_base）
        # 兜底：若 Prep 没选（如旧测试路径），退化到第一个角色的第一个 base
        if ctx.selected_base is not None:
            return ctx.selected_base
        if not ctx.config.characters:
            return None
        char = next(iter(ctx.config.characters.values()))
        if not char.bases:
            return None
        base_rel = next(iter(char.bases.values()))
        import sticker_engine as _se
        res_root = _se.resources_path()
        return res_root / base_rel

    def _pick_refs(self, ctx, n) -> list:
        ref_lib = ctx.config.paths.reference_lib
        all_refs = [p for p in ref_lib.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg")]
        self.rng.shuffle(all_refs)
        return all_refs[:n]

    def _random_combo_panels(self, ctx, n) -> str:
        """拼排列组合模式的每格描述。

        2026-08 升级：keywords.json 的 emotions 支持 {en, desc} 画面级描述
        （如 "crying rivers" → "fountain tears squirting from big watery eyes..."），
        每格 = 情绪画面 + 动作 + 概率点缀道具，输出带编号的场景列表——
        比旧版 "happy + smiling" 抽象词拼接的良品率高得多。
        兼容旧格式（纯字符串数组）。
        """
        kws = self.keywords or {}
        raw_emotions = kws.get("emotions") or ["happy"]
        actions = kws.get("actions") or ["smiling"]
        props = kws.get("props") or []

        # 归一化：str → {en, desc}（旧格式兼容，desc 用 en 兜底）
        emotions = []
        for item in raw_emotions:
            if isinstance(item, dict):
                emotions.append({"en": str(item.get("en", "")),
                                 "desc": str(item.get("desc") or item.get("en", ""))})
            else:
                emotions.append({"en": str(item), "desc": str(item)})

        # 情绪去重抽取 n 个（池小于 n 时重新装填）
        picked = []
        pool = list(emotions)
        for _ in range(n):
            if not pool:
                pool = list(emotions)
            e = pool.pop(self.rng.randrange(len(pool)))
            picked.append(e)

        lines = []
        for i, e in enumerate(picked, 1):
            action = self.rng.choice(actions)
            parts = [f"{i}. {e['en'].capitalize()}: {e['desc']}"]
            if e["desc"] != e["en"]:
                parts.append(f"action: {action}")
            if props and self.rng.random() < 0.4:
                parts.append(f"with {self.rng.choice(props)}")
            # 大头变奏（2026-08-27 调研落地）：约 30% 的格子切"超大头"比例——
            # 头身比是萌感基础盘，混排两档比例让一套里萌点密度更高
            if self.rng.random() < 0.3:
                parts.append("BIG-HEAD MODE: head fills two-thirds of the "
                             "sticker height, almost all head with tiny body")
            lines.append(" — ".join(parts))
        return "\n".join(lines)
