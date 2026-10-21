from __future__ import annotations

from typing import Any

import livekit.agents as lka
from livekit.agents.llm import ChatContext

from agent.context import SessionContext
from agent.llm import build_voice_stack
from agent.prompts import build_system_prompt
from agent.tools import get_mastery, get_problem, grade_answer, record_observation
from lib.config import Settings
from lib.tutors import Tutor


def build_agent(
    settings: Settings,
    tutor: Tutor,
    session_ctx: SessionContext,
    chat_ctx: ChatContext,
    mastery: dict[str, dict[str, Any]] | None = None,
) -> lka.Agent:
    llm, stt, tts, vad = build_voice_stack(settings)
    tools = [get_problem, grade_answer, record_observation, get_mastery]

    instructions = build_system_prompt(tutor, mastery or {})

    return lka.Agent(
        instructions=instructions,
        chat_ctx=chat_ctx,
        llm=llm,
        stt=stt,
        tts=tts,
        vad=vad,
        tools=tools,
        turn_detection="vad",
        min_endpointing_delay=0.8,
        max_endpointing_delay=2.5,
        allow_interruptions=True,
    )
