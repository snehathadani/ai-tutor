from __future__ import annotations

from typing import Any

from lib.tutors import Tutor


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
        + build_dynamic_prompt(tutor, mastery)
    )


def build_dynamic_prompt(tutor: Tutor, mastery: dict[str, dict[str, Any]]) -> str:
    lines = ["Current student mastery:"]
    for concept in tutor.concepts:
        slug = concept.slug
        record = mastery.get(slug, {})
        level = record.get("level", 0)
        lines.append(f"- {slug}: level {level}/3")
    if not mastery:
        lines.append("(no mastery data yet)")
    lines.append(
        "Pick the next concept to work on based on these levels. "
        "Start with the first concept that is not yet at level 2."
    )
    return "\n".join(lines)
