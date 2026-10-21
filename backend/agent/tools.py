from __future__ import annotations

import json
import logging
import re
from fractions import Fraction
from typing import Any

import livekit.agents as lka
from livekit.agents.voice.events import RunContext

from agent.context import SessionContext

logger = logging.getLogger(__name__)

# Student answers are logged, not stored, so keep the log line short.
_ARG_LOG_MAX_CHARS = 60


def _normalize(text: str) -> str:
    return re.sub(r"[^\w\s/\.\-]", "", text.lower().strip())


def _is_correct(given: str, answer_spec: dict[str, Any]) -> bool:
    given_clean = _normalize(given)
    acceptable = answer_spec.get("acceptable", [])
    for ans in acceptable:
        if given_clean == _normalize(ans):
            return True
    # Try fraction/numeric equivalence for answers containing a slash.
    if "/" in given_clean:
        try:
            given_frac = Fraction(given_clean.split()[0])
            for ans in acceptable:
                if "/" in ans:
                    try:
                        ans_frac = Fraction(_normalize(ans).split()[0])
                        if given_frac == ans_frac:
                            return True
                    except Exception:
                        continue
        except Exception:
            pass
    # Try float equivalence.
    try:
        given_float = float(given_clean.split()[0])
        for ans in acceptable:
            try:
                if abs(given_float - float(_normalize(ans).split()[0])) < 1e-6:
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def _ctx(ctx: RunContext) -> SessionContext:
    userdata = ctx.userdata
    if not isinstance(userdata, SessionContext):
        raise RuntimeError("SessionContext not attached to AgentSession userdata")
    return userdata


@lka.function_tool
async def get_problem(ctx: RunContext, concept_slug: str, difficulty: int = 1) -> str:
    """Get a practice problem for a concept."""
    logger.info(
        "tool get_problem(concept_slug=%s, difficulty=%s)", concept_slug, difficulty
    )
    session_ctx = _ctx(ctx)
    tutor = session_ctx.tutor
    problems = tutor.problems_by_concept.get(concept_slug, [])
    if not problems:
        return json.dumps({"error": f"Unknown concept or no problems: {concept_slug}"})
    problem = problems[(difficulty - 1) % len(problems)]
    session_ctx.set_problem(problem.model_dump())
    # Publishing the new concept and marking the one we left are the two
    # side effects of a concept switch.
    await session_ctx.publish_concept()
    await session_ctx.flush_covered()
    return json.dumps(
        {
            "problem_id": problem.id,
            "question": problem.question,
            "concept_slug": problem.concept_slug,
            "difficulty": difficulty,
        }
    )


@lka.function_tool
async def grade_answer(ctx: RunContext, problem_id: str, student_answer: str) -> str:
    """Check a student's answer against the hidden answer key. Never reveals the answer."""
    logger.info(
        "tool grade_answer(problem_id=%s, student_answer=%s)",
        problem_id,
        str(student_answer)[:_ARG_LOG_MAX_CHARS],
    )
    session_ctx = _ctx(ctx)
    problem = session_ctx.current_problem
    if problem is None or problem.get("id") != problem_id:
        return json.dumps(
            {
                "correct": False,
                "hint": "I don't have an active problem for that ID. Let's pick one first.",
            }
        )
    concept = problem.get("concept_slug")
    if not concept:
        logger.error(
            "Problem %s is missing concept_slug; mastery cannot be updated.",
            problem.get("id"),
        )
        return json.dumps(
            {
                "correct": False,
                "error": "Internal problem configuration error: concept missing.",
            }
        )
    correct = _is_correct(student_answer, problem["answer"])
    await session_ctx.state.update_mastery(session_ctx.tutor.id, concept, correct=correct, weight=1.0)
    if correct:
        session_ctx.clear_problem()
        await session_ctx.publish_concept()
        return json.dumps(
            {
                "correct": True,
                "hint": "Nice work! What strategy did you use?",
            }
        )
    return json.dumps(
        {
            "correct": False,
            "hint": problem["answer"].get("hint", "Try re-reading the question and look for clues."),
        }
    )


@lka.function_tool
async def record_observation(ctx: RunContext, concept_slug: str, signal: str) -> str:
    """Record soft evidence that the student got it or is struggling.

    signal must be "got_it" or "struggling".
    """
    logger.info(
        "tool record_observation(concept_slug=%s, signal=%s)", concept_slug, signal
    )
    if signal not in ("got_it", "struggling"):
        return json.dumps(
            {
                "error": f"Invalid signal '{signal}'. Use 'got_it' or 'struggling'."
            }
        )
    session_ctx = _ctx(ctx)
    if concept_slug not in session_ctx.tutor.concept_by_slug:
        return json.dumps({"error": f"Unknown concept: {concept_slug}"})
    await session_ctx.state.record_observation(session_ctx.tutor.id, concept_slug, signal)
    return json.dumps({"recorded": True, "concept_slug": concept_slug, "signal": signal})


@lka.function_tool
async def get_mastery(ctx: RunContext) -> str:
    """Read the student's current mastery snapshot."""
    logger.info("tool get_mastery()")
    session_ctx = _ctx(ctx)
    mastery = await session_ctx.state.get_mastery(session_ctx.tutor.id)
    return json.dumps(mastery)
