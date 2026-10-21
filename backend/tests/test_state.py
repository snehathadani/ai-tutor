import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis

from lib.state import StateService


@pytest_asyncio.fixture
async def state():
    svc = StateService(redis_client=FakeRedis(decode_responses=True))
    await svc.connect()
    yield svc
    await svc.close()


@pytest.mark.asyncio
async def test_mastery_updates(state):
    await state.update_mastery(
        "probability", "parth", "probability-fraction", correct=True, weight=1.0
    )
    mastery = await state.get_mastery("probability", "parth")
    assert mastery["probability-fraction"]["level"] == 1
    assert mastery["probability-fraction"]["correct"] == 1

    await state.update_mastery(
        "probability", "parth", "probability-fraction", correct=True, weight=1.0
    )
    await state.update_mastery(
        "probability", "parth", "probability-fraction", correct=True, weight=1.0
    )
    mastery = await state.get_mastery("probability", "parth")
    assert mastery["probability-fraction"]["level"] == 2


@pytest.mark.asyncio
async def test_transcript_and_summary(state):
    sid = "session-abc"
    await state.start_session("probability", sid)
    await state.add_transcript_turn("probability", sid, "user", "What is 3/8?")
    await state.add_transcript_turn("probability", sid, "assistant", "How many parts are there in total?")
    transcript = await state.get_transcript("probability", sid)
    assert len(transcript) == 2
    assert transcript[0]["role"] == "user"

    summary = {"summary": "Good session", "strengths": ["fractions"], "next_steps": ["more"]}
    await state.end_session("probability", sid, summary=summary)
    sessions = await state.list_sessions("probability")
    assert len(sessions) == 1
    assert sessions[0]["summary"]["summary"] == "Good session"


@pytest.mark.asyncio
async def test_chat_context_roundtrip(state):
    from livekit.agents.llm import ChatContext

    sid = "session-ctx"
    ctx = ChatContext()
    ctx.add_message(role="user", content="hello")
    await state.save_chat_context("probability", sid, ctx)
    loaded = await state.load_chat_context("probability", sid)
    assert len(loaded.items) == 1
    assert loaded.items[0].role == "user"


@pytest.mark.asyncio
async def test_mastery_isolation_across_tutors(state):
    slug = "probability-fraction"
    await state.update_mastery("tutor-a", "parth", slug, correct=True, weight=1.0)
    await state.update_mastery("tutor-b", "parth", slug, correct=False, weight=1.0)

    mastery_a = await state.get_mastery("tutor-a", "parth")
    mastery_b = await state.get_mastery("tutor-b", "parth")

    assert mastery_a[slug]["level"] == 1
    assert mastery_a[slug]["correct"] == 1
    assert mastery_b[slug]["level"] == 0


@pytest.mark.asyncio
async def test_mastery_isolation_across_students(state):
    slug = "probability-fraction"
    await state.update_mastery("probability", "parth", slug, correct=True, weight=1.0)
    await state.update_mastery("probability", "asha", slug, correct=False, weight=1.0)

    parth = await state.get_mastery("probability", "parth")
    asha = await state.get_mastery("probability", "asha")

    assert parth[slug]["level"] == 1
    assert asha[slug]["level"] == 0
    # Display-name variations resolve to the same learner.
    same = await state.get_mastery("probability", "  PARTH ")
    assert same[slug]["correct"] == 1
    assert asha[slug]["correct"] == 0
    assert asha[slug]["total"] == 1


@pytest.mark.asyncio
async def test_sessions_isolation_across_tutors(state):
    await state.start_session("tutor-a", "session-a")
    await state.start_session("tutor-b", "session-b")

    a_sessions = await state.list_sessions("tutor-a")
    b_sessions = await state.list_sessions("tutor-b")

    assert [s["sid"] for s in a_sessions] == ["session-a"]
    assert [s["sid"] for s in b_sessions] == ["session-b"]
