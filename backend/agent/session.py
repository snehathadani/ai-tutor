from __future__ import annotations

import logging
from typing import Any

import livekit.agents as lka
from livekit.agents.llm import ChatContext, ChatMessage

from agent.context import SessionContext
from agent.conversation import build_agent
from agent.summary import generate_session_summary
from lib.config import Settings
from lib.state import StateError, StateService

logger = logging.getLogger(__name__)


def _filter_prior_messages(chat_ctx: ChatContext) -> list[Any]:
    """Keep non-system history so the new system instructions are not duplicated."""
    kept: list[Any] = []
    for item in chat_ctx.items:
        if isinstance(item, ChatMessage) and item.role in ("system", "developer"):
            continue
        kept.append(item)
    return kept


async def run_session(ctx: lka.JobContext, settings: Settings) -> None:
    session_id = ctx.room.name
    state = StateService(settings.redis_url)
    connected = False
    try:
        await state.connect(retries=10, delay=1.0)
        connected = True
    except StateError as exc:
        logger.error("Redis unavailable for session %s: %s", session_id, exc)
        logger.warning("Continuing without persistence for this session.")

    prior = ChatContext.empty()
    if connected:
        try:
            prior = await state.load_chat_context(session_id)
        except Exception as exc:
            logger.error("Failed to load chat context: %s", exc)

    history = _filter_prior_messages(prior)
    chat_ctx = ChatContext(items=history)

    session_ctx = SessionContext(session_id=session_id, state=state)
    agent = build_agent(settings, session_ctx, chat_ctx)
    session = lka.AgentSession(userdata=session_ctx)

    async def _on_item(event: lka.ConversationItemAddedEvent) -> None:
        item = event.item
        if isinstance(item, ChatMessage) and item.role in ("user", "assistant"):
            text = ""
            for part in item.content:
                if isinstance(part, str):
                    text += part
            if connected:
                try:
                    await state.add_transcript_turn(
                        session_id,
                        role=item.role,
                        text=text,
                        concept=session_ctx.current_concept,
                    )
                    await state.save_chat_context(session_id, session.history)
                except Exception as exc:
                    logger.error("Failed to persist turn: %s", exc)

    session.on("conversation_item_added", _on_item)

    await ctx.connect(auto_subscribe=lka.AutoSubscribe.AUDIO_ONLY)

    if connected:
        try:
            await state.start_session(session_id)
        except Exception as exc:
            logger.error("Failed to record session start: %s", exc)

    logger.info("Starting voice session %s", session_id)
    await session.start(agent=agent, room=ctx.room)


async def finalize_session(ctx: lka.JobContext, settings: Settings) -> None:
    session_id = ctx.room.name
    state = StateService(settings.redis_url)
    try:
        await state.connect(retries=3, delay=0.5)
    except StateError as exc:
        logger.error("Cannot finalize session %s: Redis unavailable (%s)", session_id, exc)
        return

    try:
        transcript = await state.get_transcript(session_id)
        mastery = await state.get_mastery()
        summary = await generate_session_summary(settings, transcript, mastery)
        await state.end_session(session_id, summary=summary)
        logger.info("Session %s finalized with summary", session_id)
    except Exception as exc:
        logger.error("Failed to finalize session %s: %s", session_id, exc)
