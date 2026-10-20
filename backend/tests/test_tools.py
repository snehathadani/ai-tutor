import json

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from livekit.agents.voice.events import RunContext

from agent.context import SessionContext
from agent.tools import get_problem, grade_answer, record_observation
from lib.state import StateService


@pytest_asyncio.fixture
async def state():
    svc = StateService(redis_client=FakeRedis(decode_responses=True))
    await svc.connect()
    yield svc
    await svc.close()


class _FakeUserdata:
    def __init__(self, ctx):
        self._ctx = ctx

    def __getattribute__(self, name):
        if name == "_ctx":
            return object.__getattribute__(self, name)
        return getattr(self._ctx, name)


class _FakeRunContext(RunContext):
    def __init__(self, session_ctx):
        self._session_ctx = session_ctx

    @property
    def userdata(self):
        return self._session_ctx


@pytest.mark.asyncio
async def test_get_problem_carries_concept_slug(state):
    session_ctx = SessionContext(session_id="s1", state=state)
    ctx = _FakeRunContext(session_ctx)
    raw = await get_problem(ctx, "probability-fraction")
    result = json.loads(raw)
    assert result["concept_slug"] == "probability-fraction"
    assert session_ctx.current_problem is not None
    assert session_ctx.current_problem["concept_slug"] == "probability-fraction"


@pytest.mark.asyncio
async def test_grade_answer_updates_mastery(state):
    session_ctx = SessionContext(session_id="s1", state=state)
    ctx = _FakeRunContext(session_ctx)

    # Serve a problem with a known concept.
    await get_problem(ctx, "probability-fraction")
    problem_id = session_ctx.current_problem["id"]
    assert problem_id.startswith("pf-")

    # Wrong answer should drop mastery to level 0.
    raw = await grade_answer(ctx, problem_id, "99/100")
    result = json.loads(raw)
    assert result["correct"] is False
    mastery = await state.get_mastery()
    assert mastery["probability-fraction"]["level"] == 0
    assert mastery["probability-fraction"]["total"] == 1
    assert mastery["probability-fraction"]["correct"] == 0

    # Serve the same or next problem in the concept and answer correctly.
    await get_problem(ctx, "probability-fraction")
    problem_id = session_ctx.current_problem["id"]
    raw = await grade_answer(ctx, problem_id, "3/8")
    result = json.loads(raw)
    assert result["correct"] is True
    mastery = await state.get_mastery()
    assert mastery["probability-fraction"]["correct"] == 1


@pytest.mark.asyncio
async def test_grade_answer_does_not_leak_answer(state):
    session_ctx = SessionContext(session_id="s1", state=state)
    ctx = _FakeRunContext(session_ctx)

    await get_problem(ctx, "sample-space")
    problem = session_ctx.current_problem
    raw = await grade_answer(ctx, problem["id"], "wrong answer")
    result = json.loads(raw)
    assert result["correct"] is False

    answer_spec = problem["answer"]
    leaked_text = json.dumps(result)
    for acceptable in answer_spec["acceptable"]:
        assert acceptable.lower() not in leaked_text.lower()
    assert answer_spec["reason"].lower() not in leaked_text.lower()
    assert "hint" in result


@pytest.mark.asyncio
async def test_grade_answer_fails_loudly_without_concept_slug(state):
    session_ctx = SessionContext(session_id="s1", state=state)
    ctx = _FakeRunContext(session_ctx)

    # Manually inject a problem missing concept_slug.
    session_ctx.set_problem(
        {
            "id": "bad-problem",
            "question": "What is 1+1?",
            "answer": {"acceptable": ["2"], "reason": "One plus one is two."},
        }
    )
    raw = await grade_answer(ctx, "bad-problem", "2")
    result = json.loads(raw)
    assert result["correct"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_record_observation_rejects_neutral(state):
    session_ctx = SessionContext(session_id="s1", state=state)
    ctx = _FakeRunContext(session_ctx)

    raw = await record_observation(ctx, "chance-words", "neutral")
    result = json.loads(raw)
    assert "error" in result
    assert result.get("recorded") is None
    mastery = await state.get_mastery()
    assert mastery.get("chance-words", {}).get("total", 0) == 0
