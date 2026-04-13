import os

# TTS Configuration
TTS_MODEL = os.getenv("TTS_MODEL", "qwen3-tts-instruct-flash")
TTS_VOICE = os.getenv("TTS_VOICE", "Cherry")
TTS_LANGUAGE = os.getenv("TTS_LANGUAGE", "Chinese")
TTS_SPEECH_RATE = float(os.getenv("TTS_SPEECH_RATE", "1.0"))
TTS_INSTRUCTIONS = os.getenv("TTS_INSTRUCTIONS", "语速偏慢，音调温柔甜美，语气治愈温暖，像贴心朋友般关怀，充满耐心和爱心。")

# Note: API Key 不再需要配置，已通过 service-gateway-invoke 统一认证
