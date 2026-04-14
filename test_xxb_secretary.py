import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import secretary
import tts_engine
from tts_engine import TTSEngine


class TTSEngineFeatureTests(unittest.TestCase):
    def test_save_audio_bytes_to_output_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "voice.wav")
            engine = TTSEngine(mock_mode=True)
            payload = b"RIFFdemo-audio"

            saved_path = engine.save_audio(payload, output_path)

            self.assertEqual(saved_path, output_path)
            self.assertTrue(os.path.exists(output_path))
            with open(output_path, "rb") as fh:
                self.assertEqual(fh.read(), payload)

    def test_build_hermes_media_output_for_voice(self):
        media = tts_engine.build_hermes_media_output(
            "/tmp/boss.ogg",
            audio_as_voice=True,
        )
        self.assertEqual(media, "[[audio_as_voice]]\nMEDIA:/tmp/boss.ogg")

    def test_build_hermes_media_output_plain_media(self):
        media = tts_engine.build_hermes_media_output("/tmp/boss.mp3")
        self.assertEqual(media, "MEDIA:/tmp/boss.mp3")

    def test_convert_audio_uses_ffmpeg_for_mp3(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = os.path.join(tmpdir, "voice.wav")
            target = os.path.join(tmpdir, "voice.mp3")
            with open(source, "wb") as fh:
                fh.write(b"RIFFfake")

            with patch("tts_engine.subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                with open(target, "wb") as fh:
                    fh.write(b"ID3")

                result = tts_engine.convert_audio_file(source, target, "mp3")

            self.assertEqual(result, target)
            self.assertTrue(mock_run.called)

    def test_export_normalizes_output_extension_to_selected_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "boss.wav")
            engine = TTSEngine(mock_mode=True)

            exported = engine.export("老板你好", output_path=output_path, audio_format="mp3", play_audio=False)

            self.assertTrue(exported.endswith(".mp3"))
            self.assertTrue(os.path.exists(exported))
            self.assertFalse(os.path.exists(output_path))

    def test_export_no_play_does_not_initialize_pyaudio(self):
        class FakePyAudioModule:
            calls = 0

            class PyAudio:
                def __init__(self):
                    FakePyAudioModule.calls += 1

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(tts_engine, "pyaudio", FakePyAudioModule):
                engine = TTSEngine(mock_mode=True)
                exported = engine.export("老板你好", output_path=os.path.join(tmpdir, "boss.wav"), audio_format="wav", play_audio=False)
                self.assertTrue(os.path.exists(exported))
                self.assertEqual(FakePyAudioModule.calls, 0)

    def test_asset_headers_not_sent_to_untrusted_host(self):
        engine = TTSEngine(mock_mode=True)
        with patch.object(TTSEngine, "_load_skillatlas_token", return_value="secret-token"):
            trusted = engine._asset_headers_for_url("https://assets.skillatlas.cn/audio.wav")
            root_domain = engine._asset_headers_for_url("https://skillatlas.cn/audio.wav")
            untrusted = engine._asset_headers_for_url("https://evil.example/audio.wav")
            lookalike = engine._asset_headers_for_url("https://evilskillatlas.cn/audio.wav")

        self.assertEqual(trusted, {"Authorization": "Bearer secret-token"})
        self.assertEqual(root_domain, {"Authorization": "Bearer secret-token"})
        self.assertEqual(untrusted, {})
        self.assertEqual(lookalike, {})

    def test_secretary_export_no_play(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "boss.wav")
            captured = {}

            def fake_synthesize(self, text):
                captured["text"] = text
                return b"RIFFdemo"

            with patch.object(TTSEngine, "synthesize", fake_synthesize):
                with patch.object(TTSEngine, "play_audio", side_effect=AssertionError("should not play")):
                    sec = secretary.CaringSecretary(mock_mode=True)
                    exported = sec.say("老板你好", output_path=output_path, audio_format="wav", play_audio=False)

            self.assertEqual(captured["text"], "老板你好")
            self.assertEqual(exported, output_path)
            self.assertTrue(os.path.exists(output_path))

    def test_secretary_cli_export_json_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "boss.mp3")

            def fake_export(self, text, output_path=None, audio_format="wav", play_audio=True):
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, "wb") as fh:
                    fh.write(b"ID3demo")
                return output_path

            with patch.object(TTSEngine, "export", fake_export):
                with patch("sys.argv", [
                    "secretary.py",
                    "--say", "老板你好",
                    "--export", output_path,
                    "--format", "mp3",
                    "--no-play",
                ]):
                    stdout = io.StringIO()
                    with redirect_stdout(stdout):
                        rc = secretary.main()

            self.assertEqual(rc, 0)
            self.assertIn('"success": true', stdout.getvalue())
            self.assertIn(output_path, stdout.getvalue())

    def test_tts_cli_hermes_media_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "boss.ogg")

            def fake_export(self, text, output_path=None, audio_format="wav", play_audio=True):
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, "wb") as fh:
                    fh.write(b"OggSdemo")
                return output_path

            with patch.object(TTSEngine, "export", fake_export):
                with patch("sys.argv", [
                    "tts_engine.py",
                    "--text", "老板你好",
                    "--output", output_path,
                    "--format", "ogg",
                    "--no-play",
                    "--hermes-media",
                    "--audio-as-voice",
                ]):
                    stdout = io.StringIO()
                    with redirect_stdout(stdout):
                        rc = tts_engine.main()

            self.assertEqual(rc, 0)
            self.assertIn("[[audio_as_voice]]", stdout.getvalue())
            self.assertIn(f"MEDIA:{output_path}", stdout.getvalue())

    def test_invalid_daily_time_returns_error_code_2(self):
        with patch("sys.argv", ["secretary.py", "--mock", "--daily", "25:61", "--message", "喝水"]):
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                rc = secretary.main()

        self.assertEqual(rc, 2)
        self.assertIn("时间格式必须是 HH:MM", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
