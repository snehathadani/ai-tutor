from __future__ import annotations

import livekit.agents as lka
from livekit.agents import inference
from livekit.plugins.openai import LLM as OpenAILLM

from lib.config import Settings


def build_voice_stack(settings: Settings) -> tuple[OpenAILLM, inference.STT, inference.TTS, inference.VAD]:
    llm = OpenAILLM(
        model=settings.deepseek_model,
        base_url=settings.deepseek_base_url,
        api_key=settings.deepseek_api_key,
        temperature=0.6,
        max_completion_tokens=256,
    )
    stt = inference.STT(
        model=settings.stt_model,
        api_key=settings.livekit_api_key,
    )
    tts = inference.TTS(
        model=settings.tts_model,
        api_key=settings.livekit_api_key,
        voice=settings.tts_voice,
    )
    vad = inference.VAD()
    return llm, stt, tts, vad
