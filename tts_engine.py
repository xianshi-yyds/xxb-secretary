"""Minimal TTS engine for the Caring Secretary skill."""

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import wave
from io import BytesIO
from typing import Any, Optional
from urllib.parse import urlparse

import config

try:
    import pyaudio
except ImportError:
    pyaudio = None

SERVICE_CODE = "qwen_tts"
SUPPORTED_FORMATS = {"wav", "mp3", "ogg"}
SUPPORTED_OUTPUT_MODES = {"json", "path", "media-tag", "hermes"}
MOCK_WAV_BYTES = (
    b"RIFF$\x00\x00\x00WAVEfmt "
    b"\x10\x00\x00\x00\x01\x00\x01\x00"
    b"\xc0]\x00\x00\x80\xbb\x00\x00"
    b"\x02\x00\x10\x00data\x00\x00\x00\x00"
)


def ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def build_output_path(text: str, audio_format: str) -> str:
    safe_name = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text.strip())[:24].strip("-") or "secretary-audio"
    return os.path.join(os.path.expanduser("~"), ".hermes", "audio_cache", f"{safe_name}.{audio_format}")


def normalize_output_path(output_path: str, audio_format: str) -> str:
    root, ext = os.path.splitext(output_path)
    expected_ext = f".{audio_format.lower()}"
    if ext.lower() == expected_ext:
        return output_path
    return root + expected_ext


def build_hermes_media_output(file_path: str, audio_as_voice: bool = False) -> str:
    media = f"MEDIA:{file_path}"
    if audio_as_voice:
        return f"[[audio_as_voice]]\n{media}"
    return media


def build_output_payload(file_path: str, audio_format: str, voice_candidate: bool = False) -> dict[str, Any]:
    return {
        "success": True,
        "file_path": file_path,
        "format": audio_format,
        "media_type": "audio",
        "voice_candidate": voice_candidate,
    }


def format_output(
    file_path: str,
    audio_format: str,
    output_mode: str = "json",
    voice_message: bool = False,
) -> str:
    if output_mode == "json":
        return json.dumps(
            build_output_payload(file_path, audio_format, voice_candidate=voice_message),
            ensure_ascii=False,
        )
    if output_mode == "path":
        return file_path
    if output_mode == "media-tag":
        return f"MEDIA:{file_path}"
    if output_mode == "hermes":
        return build_hermes_media_output(file_path, audio_as_voice=voice_message)
    raise ValueError(f"不支持的输出模式: {output_mode}")


def convert_audio_file(source_path: str, target_path: str, audio_format: str) -> str:
    audio_format = audio_format.lower()
    if audio_format not in SUPPORTED_FORMATS:
        raise ValueError(f"不支持的音频格式: {audio_format}")

    if source_path == target_path:
        return target_path

    ensure_parent_dir(target_path)

    if audio_format == "wav":
        shutil.copyfile(source_path, target_path)
        return target_path

    if shutil.which("ffmpeg") is None:
        raise RuntimeError("未找到 ffmpeg，无法进行音频格式转换。")

    command = ["ffmpeg", "-y", "-i", source_path]
    if audio_format == "mp3":
        command += [target_path]
    elif audio_format == "ogg":
        command += ["-acodec", "libopus", "-ac", "1", "-b:a", "64k", "-vbr", "off", target_path]

    result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    if result.returncode != 0 or not os.path.exists(target_path) or os.path.getsize(target_path) == 0:
        error_msg = (result.stderr or result.stdout or "未知错误").strip()
        raise RuntimeError(f"音频转换失败: {error_msg}")
    return target_path


class TTSEngine:
    def __init__(self, mock_mode: bool = False):
        self.mock_mode = mock_mode
        self.model = config.TTS_MODEL
        self.voice = config.TTS_VOICE
        self.language = config.TTS_LANGUAGE
        self.speech_rate = config.TTS_SPEECH_RATE
        self.instructions = config.TTS_INSTRUCTIONS
        self.audio = None
        self._audio_init_attempted = False

        if not self.mock_mode and not self._skill_atlas_available():
            self.mock_mode = True
            print("[Info] 已自动切换到 Mock 模式。")

    def _ensure_audio(self) -> None:
        if self._audio_init_attempted:
            return

        self._audio_init_attempted = True
        if pyaudio is None:
            print("[Info] 未安装 pyaudio，将只输出文本，不播放音频。")
            return

        try:
            self.audio = pyaudio.PyAudio()
        except Exception as exc:
            print(f"[Warning] 初始化音频设备失败，将只输出文本: {exc}")
            self.audio = None

    def _skill_atlas_available(self) -> bool:
        try:
            result = subprocess.run(
                ["skill-atlas", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            result = None

        if result and result.returncode == 0:
            return True

        print(
            "[Warning] 未找到可用的 skill-atlas CLI。\n"
            "请先执行: npm install -g skill-atlas-cli\n"
            "然后执行: skill-atlas agent-register"
        )
        return False

    def _invoke_service_gateway(self, payload: dict[str, Any]) -> Any:
        result = subprocess.run(
            [
                "skill-atlas",
                "service-gateway-invoke",
                "--service-code",
                SERVICE_CODE,
                "--payload",
                json.dumps(payload, ensure_ascii=False),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

        if result.returncode != 0:
            error_msg = (result.stderr or result.stdout or "未知错误").strip()
            raise RuntimeError(f"服务调用失败: {error_msg}")

        response = self._extract_json_from_output(result.stdout)
        if response is None:
            raise RuntimeError("服务返回无法解析的结果。")
        return response

    def _extract_json_from_output(self, output: str) -> Optional[Any]:
        clean_output = re.sub(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", "", output)

        if "返回数据:" in clean_output:
            clean_output = clean_output.split("返回数据:", 1)[1]

        clean_output = clean_output.strip()
        for line in clean_output.splitlines():
            candidate = line.strip()
            if not candidate:
                continue
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        matches = re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", clean_output)
        for match in reversed(matches):
            try:
                value = json.loads(match)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
        return None

    def _pick_value(self, response: dict[str, Any], *keys: str) -> Optional[str]:
        for key in keys:
            value = response.get(key)
            if value:
                return value

        data = response.get("data")
        if isinstance(data, dict):
            for key in keys:
                value = data.get(key)
                if value:
                    return value
        return None

    def _decode_audio_data(self, audio_base64: str) -> bytes:
        try:
            return base64.b64decode(audio_base64)
        except Exception as exc:
            raise RuntimeError(f"音频解码失败: {exc}") from exc

    def _asset_headers_for_url(self, url: str) -> dict[str, str]:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if host != "skillatlas.cn" and not host.endswith(".skillatlas.cn"):
            return {}

        token = self._load_skillatlas_token()
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}

    def _asset_headers(self) -> dict[str, str]:
        token = self._load_skillatlas_token()
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}

    def _load_skillatlas_token(self) -> Optional[str]:
        config_dir = os.getenv("SKILLATLAS_CONFIG_DIR") or os.path.join(
            os.path.expanduser("~"),
            ".skillatlas",
        )
        meta_path = os.path.join(config_dir, "skillatlas-meta.json")

        try:
            with open(meta_path, "r", encoding="utf-8") as file:
                meta = json.load(file)
        except Exception:
            return None

        token = meta.get("token")
        if isinstance(token, str) and token:
            return token
        return None

    def _download_audio_url(self, url: str) -> bytes:
        try:
            request = urllib.request.Request(url, headers=self._asset_headers_for_url(url))
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except Exception as exc:
            raise RuntimeError(f"音频下载失败: {exc}") from exc

    def synthesize(self, text: str) -> bytes:
        if self.mock_mode:
            return MOCK_WAV_BYTES

        payload = {
            "text": text,
            "model": self.model,
            "voice": self.voice,
            "language": self.language,
            "speechRate": self.speech_rate,
            "instructions": self.instructions,
        }
        response = self._invoke_service_gateway(payload)

        if isinstance(response, str):
            return self._download_audio_url(response)

        audio_data = self._pick_value(response, "audioData", "audio_data")
        audio_url = self._pick_value(response, "audioUrl", "audio_url", "url")

        if audio_data:
            return self._decode_audio_data(audio_data)
        if audio_url:
            return self._download_audio_url(audio_url)

        raise RuntimeError("服务响应中未找到可播放的音频字段。")

    def save_audio(self, audio_bytes: bytes, output_path: str) -> str:
        ensure_parent_dir(output_path)
        with open(output_path, "wb") as file:
            file.write(audio_bytes)
        return output_path

    def play_audio(self, audio_bytes: bytes, source: str = "inline-audio") -> Optional[str]:
        self._ensure_audio()
        try:
            with wave.open(BytesIO(audio_bytes), "rb") as wav_file:
                params = wav_file.getparams()
                frames = wav_file.readframes(wav_file.getnframes())
        except wave.Error:
            print(f"[Error] 仅支持 WAV 音频播放，当前返回格式无法播放: {source}")
            return None

        if self.audio is None:
            print("[Info] 音频已获取，但当前环境无法播放。")
            return source

        try:
            stream = self.audio.open(
                format=self.audio.get_format_from_width(params.sampwidth),
                channels=params.nchannels,
                rate=params.framerate,
                output=True,
            )
            try:
                stream.write(frames)
            finally:
                stream.stop_stream()
                stream.close()
        except Exception as exc:
            print(f"[Warning] 音频播放失败: {exc}")
            return source

        print("[Info] 音频播放完成。")
        return source

    def export(self, text: str, output_path: Optional[str] = None, audio_format: str = "wav", play_audio: bool = True) -> Optional[str]:
        audio_format = audio_format.lower()
        if audio_format not in SUPPORTED_FORMATS:
            raise ValueError(f"不支持的音频格式: {audio_format}")

        requested_path = output_path or build_output_path(text, audio_format)
        final_output_path = normalize_output_path(requested_path, audio_format)
        base_wav_path = final_output_path if audio_format == "wav" else os.path.splitext(final_output_path)[0] + ".wav"

        audio_bytes = self.synthesize(text)
        self.save_audio(audio_bytes, base_wav_path)

        final_path = base_wav_path
        if audio_format != "wav":
            final_path = convert_audio_file(base_wav_path, final_output_path, audio_format)
            if base_wav_path != final_path and os.path.exists(base_wav_path):
                os.remove(base_wav_path)

        if play_audio:
            self.play_audio(audio_bytes, source=final_path)

        return final_path

    def speak(self, text: str) -> Optional[str]:
        print(f"[Speak] {text}")

        if self.mock_mode:
            print(f"[Mock] {text}")
            return "MOCK"

        try:
            audio_bytes = self.synthesize(text)
        except Exception as exc:
            print(f"[Error] TTS 调用失败: {exc}")
            return None

        return self.play_audio(audio_bytes)

    def close(self) -> None:
        if self.audio is not None:
            self.audio.terminate()


def main() -> int:
    parser = argparse.ArgumentParser(description="贴心小秘书 TTS 测试")
    parser.add_argument("--mock", action="store_true", help="使用 Mock 模式")
    parser.add_argument("--text", required=True, help="要播报的文本")
    parser.add_argument("--output", help="导出音频到指定路径")
    parser.add_argument("--format", choices=sorted(SUPPORTED_FORMATS), default="wav", help="导出音频格式")
    parser.add_argument("--no-play", action="store_true", help="只导出，不进行本地播放")
    parser.add_argument(
        "--output-mode",
        choices=sorted(SUPPORTED_OUTPUT_MODES),
        default="json",
        help="导出结果输出模式，默认 json；hermes 仅为兼容选项",
    )
    parser.add_argument("--voice-message", action="store_true", help="将结果标记为语音消息候选")
    args = parser.parse_args()

    engine = TTSEngine(mock_mode=args.mock)
    try:
        if args.output or args.output_mode != "json" or args.no_play:
            output_path = args.output or build_output_path(args.text, args.format)
            exported = engine.export(args.text, output_path=output_path, audio_format=args.format, play_audio=not args.no_play)
            if exported:
                print(format_output(exported, args.format, output_mode=args.output_mode, voice_message=args.voice_message))
            return 0 if exported else 1

        engine.speak(args.text)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    sys.exit(main())
