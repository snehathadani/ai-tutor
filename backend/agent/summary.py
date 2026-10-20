from __future__ import annotations

import json
from typing import Any

from livekit.agents.llm import ChatContext
from livekit.plugins.openai import LLM as OpenAILLM

from lib.config import Settings


async def generate_session_summary(
    settings: Settings,
    transcript: list[dict[str, Any]],
    mastery: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if not transcript:
        return None

    llm = OpenAILLM(
        model=settings.deepseek_model,
        base_url=settings.deepseek_base_url,
        api_key=settings.deepseek_api_key,
        temperature=0.4,
        max_completion_tokens=256,
    )

    transcript_text = "\n".join(
        f"{turn['role']}: {turn['text']}" for turn in transcript[-50:]
    )
    mastery_text = json.dumps(mastery, indent=2)

    chat_ctx = ChatContext()
    chat_ctx.add_message(
        role="system",
        content=(
            "You are a tutor summary assistant. Produce a short JSON object with keys: "
            "summary (one paragraph), strengths (list), next_steps (list). "
            "Be encouraging and specific. No raw scores, just concepts."
        ),
    )
    chat_ctx.add_message(
        role="user",
        content=(
            f"Recent transcript:\n{transcript_text}\n\n"
            f"Mastery snapshot:\n{mastery_text}\n\n"
            "Write the summary JSON."
        ),
    )

    try:
        chunks: list[str] = []
        async with llm.chat(chat_ctx=chat_ctx) as stream:
            async for chunk in stream:
                if chunk.delta and chunk.delta.content:
                    chunks.append(chunk.delta.content)
        raw = "".join(chunks).strip()
        # Strip markdown fences if the model returns them.
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()
        parsed = json.loads(raw)
        return {
            "summary": parsed.get("summary", ""),
            "strengths": parsed.get("strengths", []),
            "next_steps": parsed.get("next_steps", []),
            "generated_ts": __import__("time").time(),
        }
    except Exception:
        return {
            "summary": "We had a great probability practice session! Keep exploring chance, fractions, and sample spaces.",
            "strengths": ["Participated actively"],
            "next_steps": ["Try another probability problem next time."],
            "generated_ts": __import__("time").time(),
        }
