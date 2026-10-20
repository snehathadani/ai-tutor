from __future__ import annotations

from typing import Any

CONCEPTS: list[dict[str, Any]] = [
    {"slug": "chance-words", "label": "Chance words and likelihood"},
    {"slug": "sample-space", "label": "Sample space and outcomes"},
    {"slug": "probability-fraction", "label": "Probability as a fraction"},
    {"slug": "fairness-comparing", "label": "Fairness and comparing chances"},
    {"slug": "experiment-vs-theory", "label": "Experiment vs theory"},
    {"slug": "complementary-events", "label": "Complementary events"},
    {"slug": "two-coin-events", "label": "Two-coin compound events"},
    {"slug": "expected-value", "label": "Expected value (stretch)"},
]

CONCEPT_BY_SLUG = {c["slug"]: c for c in CONCEPTS}

SYSTEM_INSTRUCTIONS = """You are a warm, patient voice tutor helping a 12-year-old learn probability. Keep every reply to 2-3 short sentences, kid-friendly, and spoken aloud.

Rules:
1. Stay in probability. If the student asks something else, gently redirect back to probability.
2. Be Socratic: ask a leading question or give a hint, but NEVER say the final answer when the student is supposed to figure it out.
3. Use the get_problem tool to pick practice problems and grade_answer to check answers.
4. Use get_mastery to adapt: if a concept is level 0, give more scaffolding; if level 2-3, move forward.
5. If the student seems unsafe or off-topic, redirect kindly and, if needed, end the turn.
6. Keep responses short because this is real-time voice.

Current concepts in order:
"""

for i, concept in enumerate(CONCEPTS, 1):
    SYSTEM_INSTRUCTIONS += f"{i}. {concept['slug']} - {concept['label']}\n"


def build_dynamic_prompt(mastery: dict[str, dict[str, Any]]) -> str:
    lines = ["Current student mastery:"]
    for concept in CONCEPTS:
        slug = concept["slug"]
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
