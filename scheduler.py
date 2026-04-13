from datetime import datetime

try:
    from apscheduler.schedulers.background import BackgroundScheduler
except ImportError:
    BackgroundScheduler = None


class SchedulerUnavailableError(RuntimeError):
    pass


class SecretaryScheduler:
    def __init__(self, tts_engine):
        if BackgroundScheduler is None:
            raise SchedulerUnavailableError("未安装 apscheduler，提醒功能不可用。")
        self.scheduler = BackgroundScheduler()
        self.tts_engine = tts_engine
        self.scheduler.start()

    def add_daily_reminder(self, time_str: str, message: str, task_name: str = "Reminder") -> None:
        hour, minute = map(int, time_str.split(":"))

        def reminder_task() -> None:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{now}] 执行提醒: {task_name}")
            self.tts_engine.speak(f"现在是 {time_str}，提醒您{message}。")

        self.scheduler.add_job(
            reminder_task,
            "cron",
            hour=hour,
            minute=minute,
            id=task_name,
            replace_existing=True,
        )
        print(f"[Info] 已注册每日提醒: {task_name} @ {time_str}")

    def stop(self) -> None:
        self.scheduler.shutdown(wait=False)
