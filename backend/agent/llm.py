from __future__ import annotations

import livekit.agents as lka
from livekit.agents import inference
from livekit.plugins.openai import LLM as OpenAILLM

from lib.config import VALID_LLM_PROVIDERS, Settings


def build_llm(settings: Settings, temperature: float = 0.6) -> lka.llm.LLM:
    provider = settings.llm_provider.lower()
    if provider == "openai":
        return OpenAILLM(
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            temperature=temperature,
            max_completion_tokens=256,
        )
    if provider == "anthropic":
        from livekit.plugins.anthropic import LLM as AnthropicLLM

        return AnthropicLLM(
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            temperature=temperature,
            max_tokens=256,
        )
    raise ValueError(
        f"Unsupported LLM_PROVIDER '{settings.llm_provider}'. "
        f"Valid values are: {', '.join(VALID_LLM_PROVIDERS)}."
    )


def build_voice_stack(settings: Settings) -> tuple[lka.llm.LLM, inference.STT, inference.TTS, inference.VAD]:
    llm = build_llm(settings)
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
