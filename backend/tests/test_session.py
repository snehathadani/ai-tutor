"""Regression tests for the conversation_item_added registration path.

livekit-agents 1.8.8's EventEmitter raises ValueError when a coroutine function
is passed to ``.on()``; the handler registered by agent.session must therefore
be synchronous and schedule its async body with ``asyncio.create_task``. These
tests use a stub session whose ``.on`` mirrors the SDK's rejection; no live
room or worker process is required.
"""

import asyncio
import inspect
from types import SimpleNamespace

import livekit.agents as lka
import pytest
from livekit.agents.llm import ChatMessage

from agent.context import SessionContext
from agent.session import register_turn_persistence


class _StrictEmitterSession:
    """Stub whose ``.on`` rejects coroutine callbacks exactly like the SDK."""

    def __init__(self) -> None:
        self.history: list[str] = []
        self.handlers: dict[str, list] = {}

    def on(self, event: str, callback=None):
        if callback is not None and inspect.iscoroutinefunction(callback):
            raise ValueError(
                "Cannot register an async callback with `.on()`. "
                "Use `asyncio.create_task` within your synchronous callback instead."
            )
        self.handlers.setdefault(event, []).append(callback)
        return callback


class _StubState:
    def __init__(self) -> None:
        self.turns: list[dict] = []
        self.saved_contexts: list = []

    async def add_transcript_turn(self, tutor_id, sid, role, text, concept=None):
        self.turns.append({"role": role, "text": text, "concept": concept})

    async def save_chat_context(self, tutor_id, sid, history):
        self.saved_contexts.append(history)


def _make_event(text: str) -> lka.ConversationItemAddedEvent:
    return lka.ConversationItemAddedEvent(item=ChatMessage(role="user", content=[text]))


def test_stub_on_rejects_async_callback_like_sdk():
    session = _StrictEmitterSession()

    async def _bad(event):  # pragma: no cover - must never be registered
        return event

    with pytest.raises(ValueError, match="Cannot register an async callback"):
        session.on("conversation_item_added", _bad)


def test_register_turn_persistence_uses_sync_callback():
    session = _StrictEmitterSession()
    state = _StubState()
    tutor = SimpleNamespace(id="probability")
    session_ctx = SessionContext(session_id="probability-abc", state=state, tutor=tutor)
    pending = register_turn_persistence(
        session,
        state=state,
        tutor=tutor,
        session_ctx=session_ctx,
        session_id="probability-abc",
        connected=True,
    )
    (handler,) = session.handlers["conversation_item_added"]
    assert not inspect.iscoroutinefunction(handler)
    assert isinstance(pending, set)


@pytest.mark.asyncio
async def test_registered_handler_schedules_persist_task_and_discards_it():
    session = _StrictEmitterSession()
    state = _StubState()
    tutor = SimpleNamespace(id="probability")
    session_ctx = SessionContext(session_id="probability-abc", state=state, tutor=tutor)
    pending = register_turn_persistence(
        session,
        state=state,
        tutor=tutor,
        session_ctx=session_ctx,
        session_id="probability-abc",
        connected=True,
    )
    (handler,) = session.handlers["conversation_item_added"]

    handler(_make_event("hello"))
    assert pending, "handler must schedule the persistence task immediately"
    (task,) = list(pending)
    await task
    await asyncio.sleep(0)  # let done callbacks run
    assert pending == set(), "completed tasks must be discarded from the pending set"
    assert state.turns == [{"role": "user", "text": "hello", "concept": None}]
    assert state.saved_contexts == [session.history]
