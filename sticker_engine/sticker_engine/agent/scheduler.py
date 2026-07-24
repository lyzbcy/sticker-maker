"""定时任务调度（apscheduler）。

注册 cron 风格的定时任务，触发 run/publish/batch/shelf。
持久化到 schedules.json，服务重启后恢复。
"""
import json
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Callable


@dataclass
class ScheduledJob:
    job_id: str
    cron: str            # "分 时 日 月 周"，如 "0 9 * * *"
    action: str          # run / publish / batch / shelf
    args: dict = field(default_factory=dict)
    next_run: Optional[str] = None


class Scheduler:
    """定时任务管理（apscheduler 包装）。"""

    def __init__(self, state_file: Path, trigger_fn: Optional[Callable] = None):
        self.state_file = Path(state_file)
        self.trigger_fn = trigger_fn or (lambda action, args: None)
        self._jobs: dict = {}   # {job_id: ScheduledJob}
        self._scheduler = None
        self._load()

    def _load(self):
        if self.state_file.exists():
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            for j in data.get("jobs", []):
                job = ScheduledJob(**j)
                self._jobs[job.job_id] = job

    def _persist(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        data = {"jobs": [asdict(j) for j in self._jobs.values()]}
        self.state_file.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                   encoding="utf-8")

    def start(self):
        """启动 apscheduler 并恢复所有任务。"""
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        self._scheduler = BackgroundScheduler()
        for job in self._jobs.values():
            self._add_aps_job(job)
        self._scheduler.start()

    def _add_aps_job(self, job: ScheduledJob):
        """把 ScheduledJob 加到 apscheduler。"""
        if not self._scheduler:
            return
        # cron "分 时 日 月 周" → CronTrigger 参数
        parts = job.cron.split()
        trigger = CronTrigger(
            minute=parts[0] if len(parts) > 0 else None,
            hour=parts[1] if len(parts) > 1 else None,
            day=parts[2] if len(parts) > 2 else None,
            month=parts[3] if len(parts) > 3 else None,
            day_of_week=parts[4] if len(parts) > 4 else None,
        )
        self._scheduler.add_job(
            self._on_trigger, trigger,
            args=[job.action, job.args, job.job_id], id=job.job_id)

    def _on_trigger(self, action: str, args: dict, job_id: str):
        """定时触发：调用 trigger_fn 执行 action。"""
        try:
            self.trigger_fn(action, args)
        except Exception as e:
            print(f"[scheduler] 任务 {job_id} 执行失败: {e}")

    def add(self, cron: str, action: str, args: dict = None) -> ScheduledJob:
        """注册定时任务。返回 job。"""
        job = ScheduledJob(job_id=str(uuid.uuid4())[:8], cron=cron,
                           action=action, args=args or {})
        self._jobs[job.job_id] = job
        if self._scheduler:
            self._add_aps_job(job)
        self._persist()
        return job

    def list(self) -> list:
        jobs = list(self._jobs.values())
        # 填 next_run（从 apscheduler 取）
        if self._scheduler:
            for job in jobs:
                ap_job = self._scheduler.get_job(job.job_id)
                if ap_job and ap_job.next_run_time:
                    job.next_run = ap_job.next_run_time.isoformat()
        return jobs

    def remove(self, job_id: str) -> bool:
        if job_id not in self._jobs:
            return False
        del self._jobs[job_id]
        if self._scheduler:
            try:
                self._scheduler.remove_job(job_id)
            except Exception:
                pass
        self._persist()
        return True

    def shutdown(self):
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
