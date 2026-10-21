from pathlib import Path

import pytest

from lib.tutors import TutorNotFound, TutorRegistry


def _repo_tutors_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "tutors"


def test_registry_loads_probability():
    registry = TutorRegistry(_repo_tutors_dir())
    tutor = registry.get("probability")
    assert tutor.id == "probability"
    assert len(tutor.concepts) == 8


def test_registry_resolves_every_problem_concept():
    registry = TutorRegistry(_repo_tutors_dir())
    tutor = registry.get("probability")
    concept_slugs = {c.slug for c in tutor.concepts}
    for problem in tutor.problems:
        assert problem.concept_slug in concept_slugs


def test_broken_tutor_excluded_while_probability_loads(tmp_path):
    tutors_dir = tmp_path / "tutors"
    good_dir = tutors_dir / "good"
    good_dir.mkdir(parents=True)
    (good_dir / "tutor.yaml").write_text(
        "id: good\n"
        "title: Good Tutor\n"
        "subject: Math\n"
        "description: works\n"
        "persona: You are a tutor.\n"
        "concepts:\n"
        "  - slug: concept-a\n"
        "    label: Concept A\n"
    )
    bad_dir = tutors_dir / "bad"
    bad_dir.mkdir(parents=True)
    (bad_dir / "tutor.yaml").write_text(
        "id: bad\n"
        "title: Bad Tutor\n"
        "subject: Math\n"
        "description: broken\n"
        "persona: You are a tutor.\n"
        "concepts:\n"
        "  - slug: concept-a\n"
        "    label: Concept A\n"
    )
    (bad_dir / "problems.yaml").write_text(
        "problems:\n"
        "  - id: p1\n"
        "    concept_slug: does-not-exist\n"
        "    question: What?\n"
        "    answer:\n"
        "      acceptable:\n"
        "        - 'yes'\n"
        "      reason: Because.\n"
        "      hint: Think.\n"
    )

    registry = TutorRegistry(tutors_dir)
    tutors, invalid = registry.load()
    assert "good" in tutors
    assert "bad" not in tutors
    assert any(item["id"] == "bad" for item in invalid)


def test_unknown_tutor_raises_with_available(tmp_path):
    tutors_dir = tmp_path / "tutors"
    t_dir = tutors_dir / "only"
    t_dir.mkdir(parents=True)
    (t_dir / "tutor.yaml").write_text(
        "id: only\n"
        "title: Only Tutor\n"
        "subject: Math\n"
        "description: only\n"
        "persona: You are a tutor.\n"
        "concepts:\n"
        "  - slug: x\n"
        "    label: X\n"
    )
    registry = TutorRegistry(tutors_dir)
    with pytest.raises(TutorNotFound) as exc_info:
        registry.get("missing")
    assert exc_info.value.tutor_id == "missing"
    assert exc_info.value.available == ["only"]
