import argparse
import re
import sys
import time

from tts_engine import TTSEngine

try:
    from scheduler import SchedulerUnavailableError, SecretaryScheduler
except ImportError:
    SchedulerUnavailableError = RuntimeError
    SecretaryScheduler = None

TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def validate_time(time_str: str) -> str:
    if not TIME_PATTERN.fullmatch(time_str):
        raise ValueError("时间格式必须是 HH:MM，且小时为 00-23、分钟为 00-59。")
    return time_str


class CaringSecretary:
    def __init__(self, mock_mode: bool = False):
        self.engine = TTSEngine(mock_mode=mock_mode)
        self.scheduler = None

        if SecretaryScheduler is None:
            print("[Info] 未安装 apscheduler，提醒功能不可用。")
            return

        try:
            self.scheduler = SecretaryScheduler(self.engine)
        except SchedulerUnavailableError as exc:
            print(f"[Info] {exc}")
            self.scheduler = None

    def say(self, text: str) -> None:
        self.engine.speak(text)

    def add_daily_reminder(self, time_str: str, message: str, name: str = "DailyReminder") -> None:
        validate_time(time_str)
        if self.scheduler is None:
            raise RuntimeError("当前环境未安装 apscheduler，无法注册每日提醒。")
        self.scheduler.add_daily_reminder(time_str, message, name)

    def run_forever(self) -> None:
        print("[Info] 小秘书已进入常驻状态，按 Ctrl+C 退出。")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[Info] 正在停止小秘书。")
        finally:
            if self.scheduler is not None:
                self.scheduler.stop()
            self.engine.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="贴心小秘书")
    parser.add_argument("--mock", action="store_true", help="使用 Mock 模式")
    parser.add_argument("--say", help="立即播报一段文本")
    parser.add_argument("--daily", help="注册每日提醒，格式必须为 HH:MM")
    parser.add_argument("--message", help="提醒内容")
    parser.add_argument("--name", default="DailyReminder", help="提醒名称")
    args = parser.parse_args()

    if not args.say and not args.daily:
        parser.error("至少提供 --say 或 --daily 其中之一。")

    if args.daily and not args.message:
        parser.error("使用 --daily 时必须同时提供 --message。")

    secretary = None
    should_close_engine = True

    try:
        secretary = CaringSecretary(mock_mode=args.mock)
        if args.say:
            secretary.say(args.say)

        if args.daily:
            should_close_engine = False
            secretary.add_daily_reminder(args.daily, args.message, args.name)
            secretary.run_forever()
        return 0
    except ValueError as exc:
        print(f"[Error] {exc}")
        return 2
    except RuntimeError as exc:
        print(f"[Error] {exc}")
        return 2
    finally:
        if secretary is not None and should_close_engine:
            secretary.engine.close()


if __name__ == "__main__":
    sys.exit(main())
