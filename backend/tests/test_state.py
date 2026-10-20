import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis

from lib.state import StateService


@pytest_asyncio.fixture
async def state():
    svc = StateService(redis_client=FakeRedis(decode_responses=True))
    await svc.connect()
    yield svc


@pytest.mark.asyncio
async def test_mastery_updates(state):
    await state.update_mastery("probability-fraction", correct=True, weight=1.0)
    mastery = await state.get_mastery()
    assert mastery["probability-fraction"]["level"] == 1
    assert mastery["probability-fraction"]["correct"] == 1

    await state.update_mastery("probability-fraction", correct=True, weight=1.0)
    await state.update_mastery("probability-fraction", correct=True, weight=1.0)
    mastery = await state.get_mastery()
    assert mastery["probability-fraction"]["level"] == 2


@pytest.mark.asyncio
async def test_transcript_and_summary(state):
    sid = "session-abc"
    await state.start_session(sid)
    await state.add_transcript_turn(sid, "user", "What is 3/8?")
    await state.add_transcript_turn(sid, "assistant", "How many parts are there in total?")
    transcript = await state.get_transcript(sid)
    assert len(transcript) == 2
    assert transcript[0]["role"] == "user"

    summary = {"summary": "Good session", "strengths": ["fractions"], "next_steps": ["more"]}
    await state.end_session(sid, summary=summary)
    sessions = await state.list_sessions()
    assert len(sessions) == 1
    assert sessions[0]["summary"]["summary"] == "Good session"


@pytest.mark.asyncio
async def test_chat_context_roundtrip(state):
    from livekit.agents.llm import ChatContext

    sid = "session-ctx"
    ctx = ChatContext()
    ctx.add_message(role="user", content="hello")
    await state.save_chat_context(sid, ctx)
    loaded = await state.load_chat_context(sid)
    assert len(loaded.items) == 1
    assert loaded.items[0].role == "user"
