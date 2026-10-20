from __future__ import annotations

import json
import re
from fractions import Fraction
from typing import Any

import livekit.agents as lka
from livekit.agents.voice.events import RunContext

from agent.context import SessionContext
from agent.prompts import CONCEPT_BY_SLUG

_PROBLEM_BANK: dict[str, list[dict[str, Any]]] = {
    "chance-words": [
        {
            "id": "cw-1",
            "question": "If it is cloudy today, is it impossible, unlikely, likely, or certain to rain?",
            "answer": {"acceptable": ["unlikely", "likely"], "reason": "It depends on the clouds, but rain is usually not certain."},
        },
        {
            "id": "cw-2",
            "question": "Rolling a 7 on a normal 6-sided die is what?",
            "answer": {"acceptable": ["impossible"], "reason": "A standard die only has 1-6."},
        },
    ],
    "sample-space": [
        {
            "id": "ss-1",
            "question": "A spinner is split into red, blue, green, and yellow. How many possible outcomes are there?",
            "answer": {"acceptable": ["4", "four"], "reason": "There are 4 colors."},
        },
        {
            "id": "ss-2",
            "question": "You toss a coin and roll a 6-sided die. How many total outcomes are in the sample space?",
            "answer": {"acceptable": ["12", "twelve"], "reason": "2 times 6 equals 12."},
        },
    ],
    "probability-fraction": [
        {
            "id": "pf-1",
            "question": "A bag has 3 red marbles and 5 blue marbles. What fraction of the marbles are red?",
            "answer": {"acceptable": ["3/8", "3 / 8", "three eighths", "0.375"], "reason": "3 red out of 8 total."},
        },
        {
            "id": "pf-2",
            "question": "If P(win) equals 1 out of 4, how would you write that as a fraction?",
            "answer": {"acceptable": ["1/4", "1 / 4", "one quarter", "one fourth", "0.25"], "reason": "1 out of 4 is one quarter."},
        },
    ],
    "fairness-comparing": [
        {
            "id": "fc-1",
            "question": "Die A has sides 1-6. Die B has sides 1,1,2,2,3,3. Is Die A fair? Is Die B fair?",
            "answer": {"acceptable": ["a fair", "a yes", "b not fair", "b no"], "reason": "Die A has equal chances; Die B repeats numbers."},
        },
        {
            "id": "fc-2",
            "question": "Spinner X has equal red and blue. Spinner Y has 3 red sections and 1 blue. Which spinner gives a better chance of blue?",
            "answer": {"acceptable": ["x", "spinner x"], "reason": "Spinner X is half blue; Spinner Y is only a quarter blue."},
        },
    ],
    "experiment-vs-theory": [
        {
            "id": "et-1",
            "question": "If you flip a coin 10 times, theory says half should be heads. If you got 4 heads, is that a surprise?",
            "answer": {"acceptable": ["not really", "a little", "no", "normal"], "reason": "Experiments rarely match theory exactly; 4 out of 10 is close to 5."},
        },
        {
            "id": "et-2",
            "question": "Theoretical probability of rolling a 3 on a die is 1/6. You roll 60 times. About how many 3s do you expect?",
            "answer": {"acceptable": ["10", "ten", "about 10"], "reason": "1/6 of 60 is 10."},
        },
    ],
    "complementary-events": [
        {
            "id": "ce-1",
            "question": "The chance of rain is 1/5. What is the chance it does NOT rain?",
            "answer": {"acceptable": ["4/5", "4 / 5", "four fifths", "0.8"], "reason": "The complement subtracts from 1."},
        },
        {
            "id": "ce-2",
            "question": "A spinner lands on green with probability 2/7. What is the probability of NOT green?",
            "answer": {"acceptable": ["5/7", "5 / 7", "five sevenths"], "reason": "1 minus 2/7 is 5/7."},
        },
    ],
    "two-coin-events": [
        {
            "id": "tc-1",
            "question": "You flip two coins. List the sample space: what are all the possible outcomes?",
            "answer": {"acceptable": ["hh ht th tt", "hh, ht, th, tt", "heads heads, heads tails, tails heads, tails tails"], "reason": "There are four ordered outcomes."},
        },
        {
            "id": "tc-2",
            "question": "When flipping two fair coins, what is the probability of getting one head and one tail?",
            "answer": {"acceptable": ["2/4", "1/2", "2 / 4", "0.5", "one half"], "reason": "HT and TH are the two favorable outcomes out of 4."},
        },
    ],
    "expected-value": [
        {
            "id": "ev-1",
            "question": "A game gives 3 points half the time and 1 point half the time. What is the average score per play?",
            "answer": {"acceptable": ["2", "two", "2 points"], "reason": "Half of 3 plus half of 1 equals 2."},
        },
        {
            "id": "ev-2",
            "question": "A raffle ticket costs $2. You have a 1 in 100 chance to win $100. On average, do you gain or lose money?",
            "answer": {"acceptable": ["lose", "lose money"], "reason": "Expected win is $1, but the ticket costs $2."},
        },
    ],
}


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
    """Get a probability practice problem for a concept."""
    problems = _PROBLEM_BANK.get(concept_slug)
    if not problems:
        return json.dumps({"error": f"Unknown concept: {concept_slug}"})
    problem = problems[(difficulty - 1) % len(problems)]
    session_ctx = _ctx(ctx)
    session_ctx.set_problem(problem)
    return json.dumps(
        {
            "problem_id": problem["id"],
            "question": problem["question"],
            "concept_slug": concept_slug,
            "difficulty": difficulty,
        }
    )


@lka.function_tool
async def grade_answer(ctx: RunContext, problem_id: str, student_answer: str) -> str:
    """Check a student's answer against the hidden answer key. Never reveals the answer."""
    session_ctx = _ctx(ctx)
    problem = session_ctx.current_problem
    if problem is None or problem.get("id") != problem_id:
        return json.dumps(
            {
                "correct": False,
                "hint": "I don't have an active problem for that ID. Let's pick one first.",
            }
        )
    correct = _is_correct(student_answer, problem["answer"])
    concept = problem.get("concept_slug")
    if concept:
        await session_ctx.state.update_mastery(concept, correct=correct, weight=1.0)
    if correct:
        session_ctx.clear_problem()
        return json.dumps(
            {
                "correct": True,
                "hint": "Nice work! What strategy did you use?",
            }
        )
    return json.dumps(
        {
            "correct": False,
            "hint": f"Not quite. {problem['answer']['reason']} Try re-reading the question.",
        }
    )


@lka.function_tool
async def record_observation(ctx: RunContext, concept_slug: str, signal: str) -> str:
    """Record soft evidence that the student got it or is struggling."""
    if concept_slug not in CONCEPT_BY_SLUG:
        return json.dumps({"error": f"Unknown concept: {concept_slug}"})
    session_ctx = _ctx(ctx)
    await session_ctx.state.record_observation(concept_slug, signal)
    return json.dumps({"recorded": True, "concept_slug": concept_slug, "signal": signal})


@lka.function_tool
async def get_mastery(ctx: RunContext) -> str:
    """Read the student's current mastery snapshot."""
    session_ctx = _ctx(ctx)
    mastery = await session_ctx.state.get_mastery()
    return json.dumps(mastery)
