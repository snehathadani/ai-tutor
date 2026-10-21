from __future__ import annotations

from typing import Any

from lib.tutors import Tutor

# The tool rules are the part of the prompt the model most often skips, so
# they are spelled out as explicit obligations rather than hints.
TRACKING_RULES = (
    "Track the student's progress with your tools. This is required, not optional:\n"
    "- Before you ask a question, call get_problem(concept_slug, difficulty) and keep "
    "the problem_id it returns.\n"
    "- When the student answers your question, call grade_answer(problem_id, student_answer) "
    "with that exact problem_id. Never skip this call; it is the only way the answer is "
    "graded and recorded.\n"
    '- When the student shows they understand a concept, call '
    'record_observation(concept_slug, signal="got_it").\n'
    "- When the student struggles, hesitates, or says they do not understand, call "
    'record_observation(concept_slug, signal="struggling").\n'
    "Call one of these tools in every turn where the student said or did something that "
    "says how well they are doing."
)


def build_system_prompt(tutor: Tutor, mastery: dict[str, dict[str, Any]]) -> str:
    """Build the agent system prompt from the tutor persona, concept list, and mastery.

    The prompt intentionally never includes reference URLs; those are UI-only.
    """
    concept_lines = [
        f"{i}. {concept.slug} - {concept.label}" for i, concept in enumerate(tutor.concepts, 1)
    ]
    return (
        tutor.persona
        + "\n\nCurrent concepts in order:\n"
        + "\n".join(concept_lines)
        + "\n\n"
        + TRACKING_RULES
        + "\n\n"
        + build_dynamic_prompt(tutor, mastery)
    )


def build_dynamic_prompt(tutor: Tutor, mastery: dict[str, dict[str, Any]]) -> str:
    lines = ["Current student mastery:"]
    for concept in tutor.concepts:
        slug = concept.slug
        record = mastery.get(slug, {})
        level = record.get("level", 0)
        covered = " (covered)" if record.get("covered") else ""
        lines.append(f"- {slug}: level {level}/3{covered}")
    if not mastery:
        lines.append("(no mastery data yet)")
    lines.append(
        "Pick the next concept to work on based on these levels. "
        "Start with the first concept that is not yet at level 2."
    )
    return "\n".join(lines)
