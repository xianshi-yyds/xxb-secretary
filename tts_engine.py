"""Minimal TTS engine for the Caring Secretary skill."""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import urllib.request
import wave
from io import BytesIO
from typing import Any, Optional

import config

try:
    import pyaudio
except ImportError:
    pyaudio = None

SERVICE_CODE = "qwen_tts"


class TTSEngine:
    def __init__(self, mock_mode: bool = False):
        self.mock_mode = mock_mode
        self.model = config.TTS_MODEL
        self.voice = config.TTS_VOICE
        self.language = config.TTS_LANGUAGE
        self.speech_rate = config.TTS_SPEECH_RATE
        self.instructions = config.TTS_INSTRUCTIONS
        self.audio = None

        if not self.mock_mode and not self._skill_atlas_available():
            self.mock_mode = True
            print("[Info] 已自动切换到 Mock 模式。")

        if pyaudio is None:
            print("[Info] 未安装 pyaudio，将只输出文本，不播放音频。")
        else:
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

    def speak(self, text: str) -> Optional[str]:
        print(f"[Speak] {text}")

        if self.mock_mode:
            print(f"[Mock] {text}")
            return "MOCK"

        payload = {
            "text": text,
            "model": self.model,
            "voice": self.voice,
            "language": self.language,
            "speechRate": self.speech_rate,
            "instructions": self.instructions,
        }

        try:
            response = self._invoke_service_gateway(payload)
        except Exception as exc:
            print(f"[Error] TTS 调用失败: {exc}")
            return None

        if isinstance(response, str):
            return self._play_audio_url(response)

        audio_data = self._pick_value(response, "audioData", "audio_data")
        audio_url = self._pick_value(response, "audioUrl", "audio_url", "url")

        if audio_data:
            return self._play_audio_bytes(self._decode_audio_data(audio_data))
        if audio_url:
            return self._play_audio_url(audio_url)

        print("[Error] 服务响应中未找到可播放的音频字段。")
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

    def _play_audio_url(self, url: str) -> Optional[str]:
        try:
            request = urllib.request.Request(url, headers=self._asset_headers())
            with urllib.request.urlopen(request, timeout=60) as response:
                audio_bytes = response.read()
        except Exception as exc:
            print(f"[Error] 音频下载失败: {exc}")
            return None

        return self._play_audio_bytes(audio_bytes, source=url)

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

    def _play_audio_bytes(self, audio_bytes: bytes, source: str = "inline-audio") -> Optional[str]:
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

    def close(self) -> None:
        if self.audio is not None:
            self.audio.terminate()


def main() -> int:
    parser = argparse.ArgumentParser(description="贴心小秘书 TTS 测试")
    parser.add_argument("--mock", action="store_true", help="使用 Mock 模式")
    parser.add_argument(
        "--text",
        required=True,
        help="要播报的文本",
    )
    args = parser.parse_args()

    engine = TTSEngine(mock_mode=args.mock)
    try:
        engine.speak(args.text)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    sys.exit(main())
