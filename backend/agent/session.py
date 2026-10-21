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

# Upper bound for waiting on the greeting's playout so a wedged TTS pipeline
# cannot stall run_session indefinitely.
GREETING_PLAYOUT_TIMEOUT_S = 15.0
# How long to wait for fire-and-forget turn persistence before closing Redis.
PERSIST_DRAIN_TIMEOUT_S = 5.0
# user_input_transcribed fires for every partial STT result; only keep this
# many characters of the transcript per log line.
_TRANSCRIPT_LOG_MAX_CHARS = 120


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
    skip_texts: set[str] | None = None,
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
            # The greeting is spoken on every join; persisting it would stack
            # one "Welcome back" per rejoin and replay them all to the user.
            if (
                item.role == "assistant"
                and skip_texts
                and text.strip() in skip_texts
            ):
                return
            if connected:
                try:
                    await state.add_transcript_turn(
                        tutor.id,
                        session_id,
                        role=item.role,
                        text=text,
                        concept=session_ctx.current_concept,
                    )
                except Exception as exc:
                    logger.error("Failed to persist transcript turn: %s", exc)
                try:
                    await state.save_chat_context(tutor.id, session_id, session.history)
                except Exception as exc:
                    # The transcript above is the resume source of truth; a
                    # failed chat_ctx write only costs us the fast path.
                    logger.error(
                        "Failed to save chat context (transcript fallback in use): %s", exc
                    )

    def _on_item(event: lka.ConversationItemAddedEvent) -> None:
        task = asyncio.create_task(_persist(event))
        pending.add(task)
        task.add_done_callback(pending.discard)

    session.on("conversation_item_added", _on_item)
    return pending


def register_pipeline_logging(session: lka.AgentSession) -> None:
    """Register synchronous handlers that log the voice pipeline's lifecycle.

    livekit-agents' EventEmitter rejects coroutine callbacks with ValueError,
    so every handler is a plain function (see register_turn_persistence for
    the asyncio.create_task pattern when async work is needed). These logs
    make STT/LLM/TTS failures visible in the agent job log instead of silent.
    """

    def _on_user_input_transcribed(event: lka.UserInputTranscribedEvent) -> None:
        text = event.transcript.strip()
        if not text:
            return
        logger.info(
            "User said%s: %s",
            " (final)" if event.is_final else " (partial)",
            text[:_TRANSCRIPT_LOG_MAX_CHARS],
        )

    def _on_error(event: lka.ErrorEvent) -> None:
        logger.error(
            "Pipeline error from %s: %r",
            type(event.source).__name__ if event.source is not None else "unknown",
            event.error,
        )

    def _on_speech_created(event: lka.SpeechCreatedEvent) -> None:
        logger.info(
            "TTS speaking (source=%s, user_initiated=%s)",
            event.source,
            event.user_initiated,
        )

    def _on_agent_state_changed(event: lka.AgentStateChangedEvent) -> None:
        logger.info("Agent state: %s -> %s", event.old_state, event.new_state)

    session.on("user_input_transcribed", _on_user_input_transcribed)
    session.on("error", _on_error)
    session.on("speech_created", _on_speech_created)
    session.on("agent_state_changed", _on_agent_state_changed)


async def speak_greeting(session: lka.AgentSession, line: str) -> None:
    """Speak the opening line via TTS only, with no LLM round-trip.

    The greeting must be heard even when the LLM provider is unreachable, so
    it goes straight to session.say. It is deliberately kept out of the chat
    context: a resumed call already carries the conversation, and repeated
    greetings in the model's history add nothing.

    Playout is awaited under a timeout and every failure is logged at ERROR;
    the session itself keeps running.
    """
    try:
        handle = session.say(line, add_to_chat_ctx=False)
    except Exception as exc:
        logger.error("Failed to start greeting speech: %s", exc)
        return

    try:
        await asyncio.wait_for(handle.wait_for_playout(), timeout=GREETING_PLAYOUT_TIMEOUT_S)
    except Exception as exc:
        logger.error("Greeting did not finish playing out: %s", exc)
        return

    if (exc := handle.exception()) is not None:
        logger.error("Greeting failed: %s", exc)


def greeting_line(tutor: Tutor, resumed: bool, concept_label: str | None) -> str:
    """The one line spoken on join, also used to keep it out of the transcript."""
    if not resumed:
        return tutor.greeting
    if concept_label:
        return f"Welcome back! Let's keep going with {concept_label}."
    return "Welcome back! Let's pick up where we left off."


async def run_session(ctx: lka.JobContext, settings: Settings, tutor: Tutor) -> None:
    session_id = ctx.room.name
    state = StateService(settings.redis_url)
    connected = False
    persist_tasks: set[asyncio.Task[None]] = set()
    try:
        try:
            await state.connect(retries=10, delay=1.0)
            connected = True
        except StateError as exc:
            logger.error("Redis unavailable for session %s: %s", session_id, exc)
            logger.warning("Continuing without persistence for this session.")

        prior = ChatContext.empty()
        mastery: dict[str, dict[str, Any]] = {}
        resumed_turns = 0
        restored_concept: str | None = None
        if connected:
            try:
                prior = await state.load_chat_context(tutor.id, session_id)
            except Exception as exc:
                logger.error("Failed to load chat context: %s", exc)
            resumed_turns = len(_filter_prior_messages(prior))
            if resumed_turns == 0:
                # chat_ctx is only a cache; the transcript is the durable
                # record, so a rejoin can still continue the conversation.
                try:
                    prior = await state.build_chat_context_from_transcript(
                        tutor.id, session_id
                    )
                    resumed_turns = len(_filter_prior_messages(prior))
                except Exception as exc:
                    logger.error("Failed to rebuild history from transcript: %s", exc)
            try:
                meta = await state.get_session_meta(tutor.id, session_id)
                restored_concept = (meta.get("current_concept") or "").strip() or None
            except Exception as exc:
                logger.error("Failed to load session position: %s", exc)
            try:
                mastery = await state.get_mastery(tutor.id)
            except Exception as exc:
                logger.error("Failed to load mastery: %s", exc)

        if resumed_turns:
            logger.info(
                "Resuming %s with %d prior turns%s",
                session_id,
                resumed_turns,
                f", concept={restored_concept}" if restored_concept else "",
            )
        else:
            logger.info("No prior turns for %s; starting fresh", session_id)

        history = _filter_prior_messages(prior)
        chat_ctx = ChatContext(items=history)

        session_ctx = SessionContext(
            session_id=session_id, state=state, tutor=tutor, room=ctx.room
        )
        if restored_concept and restored_concept in tutor.concept_by_slug:
            session_ctx.current_concept = restored_concept
            session_ctx._active_concept = restored_concept
        agent = build_agent(settings, tutor, session_ctx, chat_ctx, mastery=mastery)
        session = lka.AgentSession(userdata=session_ctx)

        concept_label = (
            tutor.concept_by_slug[restored_concept].label
            if restored_concept and restored_concept in tutor.concept_by_slug
            else None
        )
        opening_line = greeting_line(tutor, resumed_turns > 0, concept_label)

        persist_tasks = register_turn_persistence(
            session,
            state=state,
            tutor=tutor,
            session_ctx=session_ctx,
            session_id=session_id,
            connected=connected,
            skip_texts={opening_line},
        )
        register_pipeline_logging(session)

        # `session.start()` returns as soon as the session is live; the job
        # keeps running until the room closes. Without waiting here the
        # entrypoint returns immediately, the finally block closes Redis, and
        # every later turn fails with "Redis client is not connected".
        close_event = asyncio.Event()

        def _on_close(_event: object) -> None:
            close_event.set()

        session.on("close", _on_close)

        await ctx.connect(auto_subscribe=lka.AutoSubscribe.AUDIO_ONLY)

        if connected:
            try:
                await state.start_session(tutor.id, session_id)
            except Exception as exc:
                logger.error("Failed to record session start: %s", exc)

        logger.info("Starting voice session %s for tutor %s", session_id, tutor.id)
        await session.start(agent=agent, room=ctx.room)

        # Greet immediately after the session is live: one short line over TTS
        # only, so the tutor is never silent on join even when the LLM is down.
        await speak_greeting(session, opening_line)

        # Hold the entrypoint open for the whole call so persistence, mastery
        # and the concept position keep writing to Redis.
        await close_event.wait()
        logger.info("Voice session %s closed", session_id)
    finally:
        # Turn persistence is fire-and-forget so it never blocks the voice
        # loop, which means late tasks can still be writing when the job ends.
        # Drain them before closing Redis or the final turns are lost with
        # "Redis client is not connected".
        if persist_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*persist_tasks, return_exceptions=True),
                    timeout=PERSIST_DRAIN_TIMEOUT_S,
                )
            except Exception as exc:
                logger.warning("Persist tasks did not drain cleanly: %s", exc)
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
