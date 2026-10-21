import json
from fractions import Fraction
from pathlib import Path

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from livekit.agents.voice.events import RunContext

from agent.context import SessionContext
from agent.tools import _is_correct, _normalize, get_problem, grade_answer, record_observation
from lib.state import StateService
from lib.tutors import Tutor, TutorRegistry


@pytest_asyncio.fixture
async def state():
    svc = StateService(redis_client=FakeRedis(decode_responses=True))
    await svc.connect()
    yield svc
    await svc.close()


@pytest.fixture
def probability_tutor():
    registry = TutorRegistry(Path(__file__).resolve().parents[2] / "tutors")
    return registry.get("probability")


@pytest.fixture
def amc8_tutor():
    registry = TutorRegistry(Path(__file__).resolve().parents[2] / "tutors")
    return registry.get("amc8")


class _FakeRunContext(RunContext):
    def __init__(self, session_ctx):
        self._session_ctx = session_ctx

    @property
    def userdata(self):
        return self._session_ctx


@pytest.mark.asyncio
async def test_get_problem_carries_concept_slug(state, probability_tutor):
    session_ctx = SessionContext(session_id="s1", state=state, tutor=probability_tutor, student="parth")
    ctx = _FakeRunContext(session_ctx)
    raw = await get_problem(ctx, "probability-fraction")
    result = json.loads(raw)
    assert result["concept_slug"] == "probability-fraction"
    assert session_ctx.current_problem is not None
    assert session_ctx.current_problem["concept_slug"] == "probability-fraction"


@pytest.mark.asyncio
async def test_grade_answer_updates_mastery(state, probability_tutor):
    session_ctx = SessionContext(session_id="s1", state=state, tutor=probability_tutor, student="parth")
    ctx = _FakeRunContext(session_ctx)

    # Serve a problem with a known concept.
    await get_problem(ctx, "probability-fraction")
    problem_id = session_ctx.current_problem["id"]
    assert problem_id.startswith("pf-")

    # Wrong answer should drop mastery to level 0.
    raw = await grade_answer(ctx, problem_id, "99/100")
    result = json.loads(raw)
    assert result["correct"] is False
    mastery = await state.get_mastery("probability", "parth")
    assert mastery["probability-fraction"]["level"] == 0
    assert mastery["probability-fraction"]["total"] == 1
    assert mastery["probability-fraction"]["correct"] == 0

    # Serve the same or next problem in the concept and answer correctly.
    await get_problem(ctx, "probability-fraction")
    problem_id = session_ctx.current_problem["id"]
    raw = await grade_answer(ctx, problem_id, "3/8")
    result = json.loads(raw)
    assert result["correct"] is True
    mastery = await state.get_mastery("probability", "parth")
    assert mastery["probability-fraction"]["correct"] == 1


@pytest.mark.asyncio
async def test_grade_answer_does_not_leak_answer(state, probability_tutor):
    session_ctx = SessionContext(session_id="s1", state=state, tutor=probability_tutor, student="parth")
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
async def test_grade_answer_fails_loudly_without_concept_slug(state, probability_tutor):
    session_ctx = SessionContext(session_id="s1", state=state, tutor=probability_tutor, student="parth")
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
async def test_record_observation_rejects_neutral(state, probability_tutor):
    session_ctx = SessionContext(session_id="s1", state=state, tutor=probability_tutor, student="parth")
    ctx = _FakeRunContext(session_ctx)

    raw = await record_observation(ctx, "chance-words", "neutral")
    result = json.loads(raw)
    assert "error" in result
    assert result.get("recorded") is None
    mastery = await state.get_mastery("probability", "parth")
    assert mastery.get("chance-words", {}).get("total", 0) == 0


@pytest.mark.asyncio
async def test_grade_answer_returns_hint_from_tutor_problem_bank(tmp_path, state):
    tutors_dir = tmp_path / "tutors"
    tutor_dir = tutors_dir / "fixture"
    tutor_dir.mkdir(parents=True)
    (tutor_dir / "tutor.yaml").write_text(
        "id: fixture\n"
        "title: Fixture Tutor\n"
        "subject: Math\n"
        "description: test\n"
        "persona: You are a tutor.\n"
        "concepts:\n"
        "  - slug: add\n"
        "    label: Addition\n"
    )
    (tutor_dir / "problems.yaml").write_text(
        "problems:\n"
        "  - id: add-1\n"
        "    concept_slug: add\n"
        "    question: What is 1 + 1?\n"
        "    answer:\n"
        "      acceptable:\n"
        "        - '2'\n"
        "      reason: One plus one is two.\n"
        "      hint: Count on your fingers.\n"
    )
    registry = TutorRegistry(tutors_dir)
    tutor = registry.get("fixture")
    session_ctx = SessionContext(session_id="s1", state=state, tutor=tutor, student="parth")
    ctx = _FakeRunContext(session_ctx)

    await get_problem(ctx, "add")
    raw = await grade_answer(ctx, "add-1", "99")
    result = json.loads(raw)
    assert result["correct"] is False
    assert "hint" in result
    assert "2" not in result["hint"]
    assert "Count on your fingers" in result["hint"]


_NUMERIC_CLASS_CHARS = set("0123456789./ -")


def _is_numeric_class(text: str) -> bool:
    return bool(text) and set(text) <= _NUMERIC_CLASS_CHARS and any(c.isdigit() for c in text)


def _parse_numeric(text: str, problem_id: str) -> Fraction | float:
    try:
        return Fraction(text)
    except (ValueError, ZeroDivisionError):
        pass
    try:
        return float(text)
    except ValueError:
        raise AssertionError(f"{problem_id}: cannot parse numeric value {text!r}")


def test_acceptable_variants_are_consistent(probability_tutor, amc8_tutor):
    # The naive "every variant grades true" check is vacuous: _is_correct's
    # first check is exact normalized-string equality, so feeding each variant
    # back in as the student answer always self-matches, even when the variant
    # is wrong. Instead, check each variant for consistency against the
    # canonical answer (acceptable[0]): numeric-class variants must be
    # numerically equal to it, non-numeric variants must be a genuinely
    # different rendering, and the list must contain no duplicates.
    for tutor in (probability_tutor, amc8_tutor):
        for problem in tutor.problems:
            acceptable = problem.answer.acceptable
            canonical = acceptable[0]
            normalized = [_normalize(v) for v in acceptable]
            assert len(set(normalized)) == len(normalized), (
                f"{problem.id}: duplicate acceptable entries after normalization: {acceptable}"
            )
            for variant in acceptable[1:]:
                if _is_numeric_class(variant):
                    assert _parse_numeric(variant, problem.id) == _parse_numeric(canonical, problem.id), (
                        f"{problem.id}: variant {variant!r} is not numerically equal to canonical {canonical!r}"
                    )
                else:
                    assert _normalize(variant) != _normalize(canonical), (
                        f"{problem.id}: variant {variant!r} is not a distinct rendering of canonical {canonical!r}"
                    )


def test_bare_numerator_does_not_match_fraction():
    assert _is_correct("1", {"acceptable": ["1/2", "1 / 2", "one half", "0.5"]}) is False
    assert _is_correct("5", {"acceptable": ["5/36", "5 / 36", "five thirty sixths"]}) is False
    assert _is_correct("15", {"acceptable": ["15/2", "15 / 2", "fifteen halves", "7.5"]}) is False
    assert _is_correct("3", {"acceptable": ["3/8", "3 / 8", "three eighths", "0.375"]}) is False
    assert _is_correct("4", {"acceptable": ["4/5", "4 / 5", "four fifths", "0.8"]}) is False


def test_trailing_words_after_number_still_grade_true():
    assert _is_correct("10 miles", {"acceptable": ["10"]}) is True
    assert _is_correct("24 books", {"acceptable": ["24"]}) is True
