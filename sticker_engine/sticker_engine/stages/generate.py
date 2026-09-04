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
from ..config.prompts import apply_set as _apply_prompt_set


# ---- IP 身份门禁（2026-08-27 事故复盘）----
# 当日一单排列组合模式：codex 会话 input_image=0（-i 参考图被静默丢弃），
# 模型凭空造出非 IP 角色且全程无报错，差点流到发布环节。对策：
# 每次生成后立刻识图对比「成图 vs base」，不同角色 → 强化提示重试 1 次 → 仍不同则明确失败。
# 判定分三档：YES 同一角色 / MINOR 同一角色但缺小细节（字母标志·小配饰，放行）/ NO 换了角色（拦截）。
# 第一性原理：门禁只防「整单偷换角色」（2026-08-27 自创角色事故），不管「格子级表情夸张」
# ——表情包的本质就是同一角色做夸张变形：石化变灰、融化成液态、害羞脸红都是正确画法
# （2026-08-29 星星布丁"石化格被当成换角色"误杀事故）。故 YES 按整张多数格子判定，
# NO 收紧为"多数格子呈现另一个角色设计"。
IDENTITY_CHECK_PROMPT = (
    "Image 1 is a generated sticker sheet; image 2 is the official base reference "
    "of the character that MUST appear in every panel.\n"
    "This is an EMOTION sticker sheet: the SAME character performs exaggerated "
    "emotions. Panel-level exaggeration is expected and CORRECT — a 'petrified' "
    "panel may turn the character gray/stone-like, a 'melting' panel may liquefy "
    "it, 'blushing' may redden it, 'burnt' may char it. These are EXPRESSION "
    "changes, NOT identity changes. Judge identity by the sheet as a whole: "
    "species/body shape, hairstyle and hair color, main outfit, resting palette.\n"
    "Answer with exactly YES, MINOR or NO as the first line:\n"
    "- YES: the character is clearly the one from image 2 (a few panels "
    "exaggerating colors/forms for emotion is fine, that is the point).\n"
    "- MINOR: same character, but small signature details are missing in most "
    "panels (a printed letter or logo, glasses, ribbons, tiny accessories) — "
    "identity itself still clearly matches.\n"
    "- NO: MOST panels show a genuinely different character design (wrong "
    "species, wrong hairstyle or hair color, wrong outfit type) that cannot be "
    "explained as emotion exaggeration.\n"
    "Then one short sentence naming what differs (if anything)."
)

_IDENTITY_RETRY_PREFIX = (
    "URGENT IDENTITY CORRECTION: a previous attempt drew a WRONG invented character. "
    "Copy the character design EXACTLY from the attached reference image(s): same species, "
    "same hairstyle and hair color, same outfit, same color palette. "
    "Include every signature detail — any letter or logo printed on the clothing or "
    "headwear, glasses, ribbons, badges — these are part of the identity. "
    "Inventing a different character means total failure.\n"
)

# NO 的定义是「多数格子换了角色」；codex 偶尔回 NO 但理由自己写着"一个格子如何"
# ——按定义不成立，按单格问题降级放行（2026-08-29 石化格误杀：15/16 正确仍被杀）
_SINGLE_PANEL_HINTS = (
    "one panel", "a single panel", "single panel", "one sticker",
    "a few panels", "one cell", "a cell", "one frame", "个别", "其中一格",
)


class GenerationMode(enum.Enum):
    REF_LIBRARY = "ref_library"
    STORY = "story"
    KEYWORD_COMBO = "keyword_combo"


# 主题抽取的跨单记忆：连续两单不选同一主题（400 单量产时的主题去重意识）。
# stage 每单都会新建实例（api.run 每次 _build），实例字段不跨单存活，
# 故挂在类属性上——同进程内批量连跑时生效；单测里用 seed 前先重置。
_LAST_THEME_KEY = None


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
        # 落盘当次 prompt：打分 JSON 会嵌入它，发给 AI 即可反哺优化方案
        ps = self._active_prompt_set(ctx)
        nl = chr(10)
        prompt_header = (
            "# mode: " + mode.value + nl +
            "# prompt_set: " + ps.id + " (" + ps.name + ")" + nl)
        (ctx.episode_dir / "原图" / "prompt.txt").write_text(
            prompt_header + prompt, encoding="utf-8")
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
                self._emit(ctx, f"第 1 次未通过（{why[:80]}），带强化身份提示开始第 2 次尝试（共 2 次）…")
            # 生图（长等待：每 5 秒心跳报告"在等什么"）
            tag = "第 1 次" if attempt == 0 else "第 2 次(强化身份)"
            self._emit(ctx, f"正在调用 codex 生图（{tag}尝试，单次约 2~7 分钟，请稍候）…")
            def _beat(elapsed, tail):
                msg = f"等待 codex 响应（{tag}尝试）… 已等 {elapsed}s"
                if tail:
                    msg += f"｜codex 输出：{tail[-120:]}"
                self._emit(ctx, msg)
            grid = self.codex.generate(prompt=cur_prompt, refs=refs, on_wait=_beat)
            if grid is None:
                detail = getattr(self.codex, "last_error", "") or "未知原因"
                self._emit(ctx, f"codex 生图失败：{detail}")
                ctx.log(LogEntry(stage="S1", status="FAIL",
                                 message=f"codex 生图失败（mode={mode.value}）：{detail}"))
                ctx.abort("S1", f"codex 生图失败：{detail}", "检查 codex 登录状态后重跑一单")
                return None
            # 废图质检：参考图被 codex 丢弃时，偶发产出全黑/纯色图（2026-08-27 实测）
            if not self._grid_sanity_ok(grid):
                why = "生成的网格图异常（全黑/纯色废图），疑似 codex 生成失败"
                self._emit(ctx, f"{why}，尝试重试…")
                continue
            # 0 token 模式（2026-09-03）：门禁识图每单喂 2 张大图给最强
            # 模型，token 巨大；前置三重防线（prompt 拍平/ASCII 暂存/
            # CRITICAL 前缀）已根治丢图事故，门禁默认跳过（prefs 可开）
            if not bool(getattr(ctx.config.prefs, "vision_calls", False)):
                self._emit(ctx, "IP 校验：0 token 模式已跳过（省额度；前置"
                                "防线仍在，可在设置中开启）")
                return grid
            ok, note = self._check_identity(ctx, grid, bases)
            if ok:
                self._emit(ctx, f"IP 校验：{note}")
                return grid
            why = note
        ctx.log(LogEntry(stage="S1", status="FAIL",
                         message=f"生成质量/IP 校验连续未通过（已重试）：{why}"))
        self._emit(ctx, f"IP 校验连续 2 次未通过，本单已主动中止（不是超时/卡死，"
                        f"参考图也未消耗，可直接再跑一单）：{why}")
        ctx.abort("S1", f"IP 校验连续 2 次未通过：{why}",
                  "参考图未消耗，可直接再跑一单；若总在同一点失败可换 base 图")
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
        reason = " ".join(ans.strip().split())[len(head.split()[0]):][:100].strip() if ans.strip() else ""
        if head.startswith("YES"):
            return True, "成图与 base 为同一角色 ✓"
        if head.startswith("MINOR"):
            # 同一角色、缺小细节（字母标志/小配饰）：放行——生图模型漏画服装上的
            # 字母是常见退化，不该整单作废（用户可在打分备注中指出，反哺 prompt）
            return True, ("同一角色，个别小细节缺失（" + (reason or "未说明") + "）——放行，"
                          "如在意可打分备注")
        if head.startswith("NO"):
            full = " ".join(ans.strip().split())
            # 兜底：理由自己暴露"只是个别格子"→ 不满足 NO 的"多数格子"定义，降级放行
            if any(h in full.lower() for h in _SINGLE_PANEL_HINTS):
                return True, ("多数格子角色正确，仅个别格子异常（"
                              + (reason or full[:80]) + "）——放行，异常格子可打分备注")
            return False, "成图角色与 base 不是同一角色（" + (reason or full[:100]) + "）"
        ctx.log(LogEntry(stage="S1", status="WARN",
                         message="IP 校验识图无明确回复，放行并留痕"))
        return True, "识图无明确回复，本次放行（留痕）"

    def _active_prompt_set(self, ctx):
        """当前生效的 Prompt 方案（prefs.prompt_set_id 指定，缺省=内置）。"""
        if getattr(self, "_prompt_set_cache", None) is None:
            from ..config.prompts import find_set
            user_data = ctx.config.paths.user_data
            self._prompt_set_cache = find_set(
                user_data, getattr(ctx.config.prefs, "prompt_set_id", None))
        return self._prompt_set_cache

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
            prompt = _apply_prompt_set(
                "ref_library", self._active_prompt_set(ctx)).format(
                grid=grid, n=n, n_img=n_img)
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
                prompt = _apply_prompt_set(
                    "story", self._active_prompt_set(ctx)).format(
                    grid=grid, n=n, stories_description=desc)
        if mode == GenerationMode.KEYWORD_COMBO:
            panels_desc = self._random_combo_panels(ctx, n)
            prompt = _apply_prompt_set(
                "keyword_combo", self._active_prompt_set(ctx)).format(
                grid=grid, n=n, panels_description=panels_desc)
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

        2026-09 升级（400 单量产多样性）：keywords.json 新增 themes 主题池
        （{"主题名": [词条…]}）。有 themes 时走主题抽取——每单锁定 1 个主题
        抽约 70%（16 格中 10-12 个）+ 其他主题随机补足（4-6 个），单内主题
        连贯 + 跨主题新鲜感；连续两单不选同一主题（类级记忆）。读不到
        themes 时退回 emotions 均匀抽（旧结构兼容）。
        """
        kws = self.keywords or {}
        actions = kws.get("actions") or ["smiling"]
        props = kws.get("props") or []

        themes = self._normalize_themes(kws.get("themes"))
        if themes:
            picked, main_key, main_n = self._pick_themed_entries(themes, n)
            self._emit(ctx, f"本单主题：「{main_key}」——主题内抽 {min(main_n, len(themes[main_key]))} 格"
                            f" + 跨主题点缀 {n - main_n} 格（词条库 {len(themes)} 个主题）")
        else:
            emotions = self._normalize_entries(kws.get("emotions") or ["happy"])
            picked = self._draw_without_repeat(emotions, n)

        # 0 token 模式（2026-09-03）：把选定词条的中文含义随 prompt 一起
        # 记到 ctx——S2 无需识图命名（切图格序 = prompt 格序，直传即可）
        # 2026-09-04 平台限制反哺：含义词字段只存 8 字节（4 个中文字），
        # 超长词在平台被硬截断（"回消息晚了对不起"→"回消息晚了"）；且
        # "呀/哦"后缀去重被审核点名（121 两次驳回警告限制投稿）。双兜底：
        # ①超 4 字或 zh 重复的词条从全库备池换掉 ②换无可换才退回后缀
        themes_all = self._normalize_themes(kws.get("themes"))
        used_en = {e.get("en") for e in picked}
        used_zh, spares = set(), []
        for es in themes_all.values():
            for e in es:
                zh = str(e.get("zh") or "").strip()
                if not zh or len(zh) > 4 or zh in used_zh or e.get("en") in used_en:
                    continue
                spares.append(e)
        replaced, new_picked = [], []
        for e in picked:
            zh = str(e.get("zh") or e.get("en") or "").strip() or "表情"
            if (len(zh) > 4 or zh in used_zh) and spares:
                replaced.append(f"{zh}->{spares[0].get('zh')}")
                e = spares.pop(0)
                zh = str(e.get("zh") or e.get("en") or "").strip() or "表情"
            used_zh.add(zh)
            new_picked.append(e)
        picked = new_picked
        if replaced:
            self._emit(ctx, f"含义词修正 {len(replaced)} 条（超长/重复换词条）："
                            + "、".join(replaced[:5]) + ("…" if len(replaced) > 5 else ""))
        zh_words = []
        for e in picked:
            w = str(e.get("zh") or e.get("en") or "").strip() or "表情"
            zh_words.append(w)
        seen = {}
        deduped = []
        suffixes = ["", "呀", "哦", "～"]
        for w in zh_words:
            cnt = seen.get(w, 0)
            suf = suffixes[min(cnt, len(suffixes) - 1)]
            deduped.append(w + (suf if cnt else ""))
            seen[w] = cnt + 1
        try:
            ctx.preset_meanings = deduped
        except AttributeError:
            pass
        lines = []
        big_head_used = 0   # 每单 BIG-HEAD 硬上限（打分反哺 2026-09-04）
        for i, e in enumerate(picked, 1):
            action = self.rng.choice(actions)
            parts = [f"{i}. {e['en'].capitalize()}: {e['desc']}"]
            if e["desc"] != e["en"]:
                parts.append(f"action: {action}")
            if props and self.rng.random() < 0.4:
                parts.append(f"with {self.rng.choice(props)}")
            # 大头变奏（2026-08-27 调研落地）：混排两档比例让一套里萌点
            # 密度更高。2026-09-04 打分反哺降配：用户 4 条"头太大了"备注
            # （156/148/129/125），概率 30%→20% 且每单硬上限 4 格（此前
            # 独立 30% 方差大，157 单曾抽到 8 格全是大头）
            if big_head_used < 4 and self.rng.random() < 0.2:
                big_head_used += 1
                parts.append("BIG-HEAD MODE: head fills two-thirds of the "
                             "sticker height, almost all head with tiny body")
            lines.append(" — ".join(parts))
        return "\n".join(lines)

    @staticmethod
    def _normalize_entries(raw) -> list:
        """词条归一化：str → {en, desc}（旧格式兼容，desc 用 en 兜底）。

        zh 字段透传（0 token 模式的预置含义词来源——丢了会退化成英文词）。
        """
        out = []
        for item in raw or []:
            if isinstance(item, dict):
                e = {"en": str(item.get("en", "")),
                     "desc": str(item.get("desc") or item.get("en", ""))}
                if item.get("zh"):
                    e["zh"] = str(item.get("zh"))
                out.append(e)
            else:
                out.append({"en": str(item), "desc": str(item)})
        return out

    @classmethod
    def _normalize_themes(cls, raw_themes) -> dict:
        """themes 归一化：{主题名: [词条…]}，跳过空主题（坏数据防御）。"""
        themes = {}
        for key, entries in (raw_themes or {}).items():
            norm = cls._normalize_entries(entries)
            if norm:
                themes[str(key)] = norm
        return themes

    def _draw_without_repeat(self, pool: list, n: int) -> list:
        """无重复抽取 n 个（按 en 去重；同词条多次出现=权重累加，
        2026-09-04 打分反哺的高频词加权靠这个生效）。池不足 n 时重新
        装填，允许跨装填重复。"""
        def _en(e):
            return e.get("en") if isinstance(e, dict) else str(e)
        uniq, wmap = [], {}
        for e in pool or []:
            en = _en(e)
            if en not in wmap:
                wmap[en] = 0.0
                uniq.append(e)
            wmap[en] += 1.0
        picked = []
        bag, ws = list(uniq), [wmap[_en(e)] for e in uniq]
        for _ in range(n):
            if not bag:
                bag, ws = list(uniq), [wmap[_en(e)] for e in uniq]
            i = self.rng.choices(range(len(bag)), weights=ws, k=1)[0]
            picked.append(bag.pop(i))
            ws.pop(i)
        return picked

    # 高频聊天主题（2026-09-04 打分反哺：57 单 28 条"使用场景太少"备注
    # 全部来自冷门叙事主题的词条——挂袜/烘焙/量尺寸/太空漫游/修网络这类
    # "看图讲故事"场景在聊天里几乎用不上。高频主题主抽+点缀权重加倍，
    # 冷门主题仍会出现（多样性保留）但占比下降）
    _CHAT_FIRST_THEMES = {
        "日常寒暄", "打工人", "干饭", "睡觉休息", "恋爱贴贴", "友谊互动",
    }

    def _pick_themed_entries(self, themes: dict, n: int):
        """主题抽取：主主题抽 ~70% + 其他主题补足，返回 (词条列表, 主题名, 主题内个数)。

        - 主主题加权随机（高频聊天主题 ×3 权重）；若与上一单相同且有得换则避开
        - 16 格 → 主题内 11 格（10-12 区间）+ 跨主题 5 格（4-6 区间）
        - 跨主题点缀池同样向高频主题倾斜（词条 ×2）
        - 其他主题为空（只有 1 个主题）时退回主主题装填，保证凑满 n 格
        """
        global _LAST_THEME_KEY
        keys = list(themes.keys())
        # 加权抽主主题（打分反哺 2026-09-04）
        weights = [3 if k in self._CHAT_FIRST_THEMES else 1 for k in keys]
        main_key = self.rng.choices(keys, weights=weights, k=1)[0]
        if len(keys) > 1 and main_key == _LAST_THEME_KEY:
            others = [k for k in keys if k != _LAST_THEME_KEY]
            w2 = [3 if k in self._CHAT_FIRST_THEMES else 1 for k in others]
            main_key = self.rng.choices(others, weights=w2, k=1)[0]
        _LAST_THEME_KEY = main_key

        main_n = max(1, min(int(round(n * 0.7)), n))
        picked = self._draw_without_repeat(themes[main_key], main_n)
        # 跨主题点缀：其余主题的词条合并抽（已按 en 全库去重，无重复风险）；
        # 高频主题词条出现两次（权重×2）
        rest_pool = []
        for k in keys:
            if k == main_key:
                continue
            for e in themes[k]:
                rest_pool.append(e)
                if k in self._CHAT_FIRST_THEMES:
                    rest_pool.append(e)
        if not rest_pool:
            rest_pool = themes[main_key]
        if n > len(picked):
            picked += self._draw_without_repeat(rest_pool, n - len(picked))
        self.rng.shuffle(picked)
        return picked, main_key, main_n
