# Caring Secretary TTS

这个 skill 只保留两项核心能力：

- 文本转语音播报
- 每日固定时间提醒

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

如果机器上没有 `skill-atlas`，程序会自动切换到 Mock 模式；如果没有 `pyaudio`，程序仍会输出播报文本，只是不播放音频。

## 使用

立即播报：

```bash
python secretary.py --say "您好"
python secretary.py --mock --say "测试播报"
```

注册每日提醒：

```bash
python secretary.py --daily 08:00 --message "喝水"
python secretary.py --mock --daily 08:00 --message "喝水" --name "Hydration"
```

直接测试 TTS 引擎：

```bash
python tts_engine.py --text "测试消息"
python tts_engine.py --mock --text "测试消息"
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
- 当前播放链路只支持 WAV 音频；如果服务返回其他格式，会输出清晰提示。
