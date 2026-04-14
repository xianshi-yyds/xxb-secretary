# Caring Secretary TTS

这个 skill 现在支持三种使用模式：

- 本地文本转语音播报
- 每日固定时间提醒
- 导出音频文件 / 按不同输出模式返回结果

## 安装

先安装并注册 `skill-atlas`：

```bash
npm install -g skill-atlas-cli
skill-atlas agent-register
```

首次使用真实 TTS 前，必须先完成这一步 `agent-register`；否则真实调用会失败，但 `--mock` 仍可正常验证流程。

macOS 如需本地播放音频，还需要安装 `portaudio`：

```bash
brew install portaudio
python -m pip install -r requirements.txt
```

如需导出 `mp3/ogg`，本机还需要安装 `ffmpeg`。

如果机器上没有 `skill-atlas`，程序会自动切换到 Mock 模式；如果没有 `pyaudio`，程序仍会输出播报文本，只是不播放音频。

## 使用

### 1) 本地立即播报

```bash
python secretary.py --say "您好"
python secretary.py --mock --say "测试播报"
python tts_engine.py --text "测试消息"
```

### 2) 导出音频文件

```bash
python tts_engine.py --text "老板你好" --output /tmp/boss.wav --format wav --no-play
python tts_engine.py --text "老板你好" --output /tmp/boss.mp3 --format mp3 --no-play
python secretary.py --say "老板你好" --export /tmp/boss.ogg --format ogg --no-play
```

默认会输出一段通用 JSON，便于脚本或不同平台消费：

```json
{"success": true, "file_path": "/tmp/boss.ogg", "format": "ogg", "media_type": "audio", "voice_candidate": false}
```

如果你只想拿到文件路径：

```bash
python tts_engine.py --text "老板你好" --output /tmp/boss.mp3 --format mp3 --no-play --output-mode path
```

输出：

```text
/tmp/boss.mp3
```

### 3) 媒体标签输出

平台无关的媒体标签模式：

```bash
python tts_engine.py --text "老板你好" --output /tmp/boss.mp3 --format mp3 --no-play --output-mode media-tag
```

输出：

```text
MEDIA:/tmp/boss.mp3
```

Hermes 兼容模式只是其中一种可选输出模式：

普通媒体：

```bash
python tts_engine.py --text "老板你好" --output /tmp/boss.mp3 --format mp3 --no-play --output-mode hermes
```

输出：

```text
MEDIA:/tmp/boss.mp3
```

语音消息候选模式：

```bash
python tts_engine.py --text "老板你好" --output /tmp/boss.ogg --format ogg --no-play --output-mode json --voice-message
python tts_engine.py --text "老板你好" --output /tmp/boss.ogg --format ogg --no-play --output-mode hermes --voice-message
python secretary.py --say "老板你好" --export /tmp/boss.ogg --format ogg --no-play --output-mode hermes --voice-message
```

JSON 输出示例：

```json
{"success": true, "file_path": "/tmp/boss.ogg", "format": "ogg", "media_type": "audio", "voice_candidate": true}
```

Hermes 兼容输出示例：

```text
[[audio_as_voice]]
MEDIA:/tmp/boss.ogg
```

### 4) 注册每日提醒

```bash
python secretary.py --daily 08:00 --message "喝水"
python secretary.py --mock --daily 08:00 --message "喝水" --name "Hydration"
```

## 配置项

通过环境变量调整 TTS 参数：

- `TTS_MODEL`
- `TTS_VOICE`
- `TTS_LANGUAGE`
- `TTS_SPEECH_RATE`
- `TTS_INSTRUCTIONS`

## 说明

- 每日提醒只接受严格的 `HH:MM` 格式。
- 缺少 `apscheduler` 时，`--say` 仍可使用，但 `--daily` 会给出明确错误。
- 当前播放链路只支持 WAV 音频直接本地播放。
- `mp3/ogg` 导出依赖 `ffmpeg` 转码。
- 默认推荐使用 `--output-mode json`，适用范围更广。
- `--output-mode hermes` 只是兼容选项，不再是唯一协议入口。
- `--voice-message` 表达的是“语音消息候选”语义，最终是否被渲染成语音消息取决于消费端适配能力。
