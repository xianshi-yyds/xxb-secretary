import argparse
import json
import re
import sys
import time

from tts_engine import TTSEngine, SUPPORTED_FORMATS, build_hermes_media_output, build_output_path

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

    def say(
        self,
        text: str,
        output_path: str | None = None,
        audio_format: str = "wav",
        play_audio: bool = True,
    ) -> str | None:
        if output_path or not play_audio:
            print(f"[Speak] {text}")
            target_path = output_path or build_output_path(text, audio_format)
            return self.engine.export(text, output_path=target_path, audio_format=audio_format, play_audio=play_audio)

        self.engine.speak(text)
        return None

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
    parser.add_argument("--export", help="将播报音频导出到指定路径")
    parser.add_argument("--format", choices=sorted(SUPPORTED_FORMATS), default="wav", help="导出音频格式")
    parser.add_argument("--no-play", action="store_true", help="导出时不进行本地播放")
    parser.add_argument("--hermes-media", action="store_true", help="按 Hermes MEDIA 格式输出导出结果")
    parser.add_argument("--audio-as-voice", action="store_true", help="配合 --hermes-media 输出语音消息指令")
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
            exported = secretary.say(
                args.say,
                output_path=args.export,
                audio_format=args.format,
                play_audio=not args.no_play,
            )
            if exported:
                if args.hermes_media:
                    print(build_hermes_media_output(exported, audio_as_voice=args.audio_as_voice))
                else:
                    print(json.dumps({"success": True, "file_path": exported, "format": args.format}, ensure_ascii=False))

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
