from __future__ import annotations

import asyncio
import logging
from typing import Any

import livekit.agents as lka
from livekit.agents.llm import ChatContext, ChatMessage

from agent.context import SessionContext
from agent.conversation import build_agent
from agent.summary import generate_session_summary
from lib.config import Settings
from lib.state import StateError, StateService
from lib.tutors import Tutor

logger = logging.getLogger(__name__)


def _filter_prior_messages(chat_ctx: ChatContext) -> list[Any]:
    """Keep non-system history so the new system instructions are not duplicated."""
    kept: list[Any] = []
    for item in chat_ctx.items:
        if isinstance(item, ChatMessage) and item.role in ("system", "developer"):
            continue
        kept.append(item)
    return kept


def register_turn_persistence(
    session: lka.AgentSession,
    *,
    state: StateService,
    tutor: Tutor,
    session_ctx: SessionContext,
    session_id: str,
    connected: bool,
) -> set[asyncio.Task[None]]:
    """Register the conversation_item_added handler that persists turns.

    livekit-agents' EventEmitter raises ValueError when a coroutine function is
    passed to ``.on()``, so the registered handler is synchronous and schedules
    the async persistence body with ``asyncio.create_task``. The returned set
    holds strong references to in-flight tasks so they are not garbage
    collected mid-flight; each task discards itself via a done callback. The
    caller must keep the returned set alive while the session runs (run_session
    holds it in a local).
    """
    pending: set[asyncio.Task[None]] = set()

    async def _persist(event: lka.ConversationItemAddedEvent) -> None:
        item = event.item
        if isinstance(item, ChatMessage) and item.role in ("user", "assistant"):
            text = ""
            for part in item.content:
                if isinstance(part, str):
                    text += part
            if connected:
                try:
                    await state.add_transcript_turn(
                        tutor.id,
                        session_id,
                        role=item.role,
                        text=text,
                        concept=session_ctx.current_concept,
                    )
                    await state.save_chat_context(tutor.id, session_id, session.history)
                except Exception as exc:
                    logger.error("Failed to persist turn: %s", exc)

    def _on_item(event: lka.ConversationItemAddedEvent) -> None:
        task = asyncio.create_task(_persist(event))
        pending.add(task)
        task.add_done_callback(pending.discard)

    session.on("conversation_item_added", _on_item)
    return pending


async def run_session(ctx: lka.JobContext, settings: Settings, tutor: Tutor) -> None:
    session_id = ctx.room.name
    state = StateService(settings.redis_url)
    connected = False
    try:
        try:
            await state.connect(retries=10, delay=1.0)
            connected = True
        except StateError as exc:
            logger.error("Redis unavailable for session %s: %s", session_id, exc)
            logger.warning("Continuing without persistence for this session.")

        prior = ChatContext.empty()
        mastery: dict[str, dict[str, Any]] = {}
        if connected:
            try:
                prior = await state.load_chat_context(tutor.id, session_id)
            except Exception as exc:
                logger.error("Failed to load chat context: %s", exc)
            try:
                mastery = await state.get_mastery(tutor.id)
            except Exception as exc:
                logger.error("Failed to load mastery: %s", exc)

        history = _filter_prior_messages(prior)
        chat_ctx = ChatContext(items=history)

        session_ctx = SessionContext(
            session_id=session_id, state=state, tutor=tutor, room=ctx.room
        )
        agent = build_agent(settings, tutor, session_ctx, chat_ctx, mastery=mastery)
        session = lka.AgentSession(userdata=session_ctx)

        persist_tasks = register_turn_persistence(
            session,
            state=state,
            tutor=tutor,
            session_ctx=session_ctx,
            session_id=session_id,
            connected=connected,
        )

        await ctx.connect(auto_subscribe=lka.AutoSubscribe.AUDIO_ONLY)

        if connected:
            try:
                await state.start_session(tutor.id, session_id)
            except Exception as exc:
                logger.error("Failed to record session start: %s", exc)

        logger.info("Starting voice session %s for tutor %s", session_id, tutor.id)
        await session.start(agent=agent, room=ctx.room)
    finally:
        try:
            await state.close()
        except Exception as exc:
            logger.warning("Error closing Redis in run_session: %s", exc)


async def finalize_session(ctx: lka.JobContext, settings: Settings, tutor: Tutor | None) -> None:
    session_id = ctx.room.name
    state = StateService(settings.redis_url)
    try:
        try:
            await state.connect(retries=3, delay=0.5)
        except StateError as exc:
            logger.error("Cannot finalize session %s: Redis unavailable (%s)", session_id, exc)
            return

        try:
            tutor_id = tutor.id if tutor else session_id.split("-")[0]
            transcript = await state.get_transcript(tutor_id, session_id)
            mastery = await state.get_mastery(tutor_id)
            summary = await generate_session_summary(settings, transcript, mastery, tutor)
            await state.end_session(tutor_id, session_id, summary=summary)
            if summary is not None:
                logger.info("Session %s finalized with summary", session_id)
            else:
                logger.info("Session %s finalized with no summary (empty transcript)", session_id)
        except Exception as exc:
            logger.error("Failed to finalize session %s: %s", session_id, exc)
    finally:
        try:
            await state.close()
        except Exception as exc:
            logger.warning("Error closing Redis in finalize_session: %s", exc)
