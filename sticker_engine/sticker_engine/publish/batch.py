"""Batch: 批量发布（迁移自现有 batch_all.py）。

把多个 episode 分批发布，支持断点续传 + 失败重试。
- 每批 ≤5 弹（避免单批超时）
- _batch_total.json 记录跨批结果，--resume 续传
- 失败弹次自动重试 --retry 次
"""
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from .config import PublishConfig
from .publisher import Publisher
from .browser import BrowserSession

BATCH_SIZE = 5   # 每批最多 5 弹（单弹约 90-115 秒，5 弹 ≈ 10 分钟）


@dataclass
class BatchState:
    """批量发布状态（持久化到 _batch_total.json）。"""
    results: dict = field(default_factory=dict)   # {episode_name: "ok"/"fail"}

    @classmethod
    def load(cls, path: Path) -> "BatchState":
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(results=data.get("results", {}))
        return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"results": self.results}, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    def is_done(self, name: str) -> bool:
        return self.results.get(name) == "ok"


class BatchPublisher:
    """批量发布多个 episode。"""

    def __init__(self, config: PublishConfig, output_root: Path,
                 state_file: Optional[Path] = None):
        self.config = config
        self.output_root = Path(output_root)
        self.state_file = state_file or (self.output_root / "_batch_total.json")

    def list_episodes(self, start: int, end: int) -> list:
        """列出 episode_start 到 episode_end（按编号）。也兼容其他命名。"""
        episodes = []
        for n in range(start, end + 1):
            # 常见命名：episode_N 或 episode_YYYYMMDD_HHMMSS_N
            candidates = list(self.output_root.glob(f"episode_*_{n:02d}"))
            candidates += list(self.output_root.glob(f"episode_*_{n}"))
            candidates += list(self.output_root.glob(f"episode_{n:02d}*"))
            candidates += list(self.output_root.glob(f"episode_{n}*"))
            if candidates:
                episodes.append((n, candidates[0]))
        return episodes

    def run(self, start: Optional[int] = None, end: Optional[int] = None,
            only: Optional[list] = None, resume: bool = False,
            batch_size: int = BATCH_SIZE, retry: int = 2,
            gap_seconds: int = 8, headless: bool = False) -> dict:
        """批量发布。返回 {summary, results}。"""
        # 确定要发布的弹次
        if only:
            targets = [(n, self._find_episode(n)) for n in only]
            targets = [(n, p) for n, p in targets if p]
        else:
            start = start or 1
            end = end or 999
            targets = self.list_episodes(start, end)

        state = BatchState.load(self.state_file) if resume else BatchState()
        all_results = {}

        # 分批
        for i in range(0, len(targets), batch_size):
            batch = targets[i:i + batch_size]
            for num, ep_dir in batch:
                name = ep_dir.name
                if state.is_done(name):
                    all_results[name] = "ok (skipped)"
                    continue
                result = self._publish_one_with_retry(ep_dir, retry, headless)
                all_results[name] = result
                state.results[name] = "ok" if result == "ok" else "fail"
                state.save(self.state_file)
                time.sleep(gap_seconds)

        summary = {"ok": sum(1 for v in all_results.values() if "ok" in v),
                   "fail": sum(1 for v in all_results.values() if v == "fail")}
        return {"summary": summary, "results": all_results}

    def _find_episode(self, num: int) -> Optional[Path]:
        """按编号找一个 episode 目录。"""
        for pattern in [f"episode_*_{num:02d}", f"episode_*_{num}",
                        f"episode_{num:02d}*", f"episode_{num}*"]:
            matches = list(self.output_root.glob(pattern))
            if matches:
                return matches[0]
        return None

    def _publish_one_with_retry(self, ep_dir: Path, retry: int, headless: bool) -> str:
        """发布一弹，失败重试。返回 ok/fail。"""
        for attempt in range(retry + 1):
            session = BrowserSession(self.config)
            publisher = Publisher(self.config, session)
            try:
                result = publisher.publish(ep_dir, headless=headless)
                if result.get("success"):
                    return "ok"
            except Exception:
                pass
            finally:
                try:
                    session.close()
                except Exception:
                    pass
            time.sleep(5)   # 重试间隔
        return "fail"
