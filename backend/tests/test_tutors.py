import os
import time
from pathlib import Path

import pytest

from lib.tutors import TutorNotFound, TutorRegistry


def _repo_tutors_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "tutors"


def _write_tutor(tutors_dir: Path, tutor_id: str, body: str) -> None:
    """Write a tutor.yaml with the given YAML body (indented under the header)."""
    tutor_dir = tutors_dir / tutor_id
    tutor_dir.mkdir(parents=True)
    (tutor_dir / "tutor.yaml").write_text(
        f"title: {tutor_id} Tutor\n"
        f"subject: Math\n"
        f"description: {tutor_id}\n"
        + body
    )


_GOOD_BODY = (
    "persona: You are a tutor.\n"
    "concepts:\n"
    "  - slug: concept-a\n"
    "    label: Concept A\n"
)


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


def test_empty_concepts_rejected(tmp_path):
    tutors_dir = tmp_path / "tutors"
    _write_tutor(tutors_dir, "good", _GOOD_BODY)
    _write_tutor(
        tutors_dir,
        "bad",
        "persona: You are a tutor.\n"
        "concepts: []\n",
    )
    registry = TutorRegistry(tutors_dir)
    tutors, invalid = registry.load()
    assert "good" in tutors
    assert "bad" not in tutors
    assert any(
        item["id"] == "bad" and item["field"] == "concepts" for item in invalid
    )


def test_blank_persona_rejected(tmp_path):
    tutors_dir = tmp_path / "tutors"
    _write_tutor(tutors_dir, "good", _GOOD_BODY)
    _write_tutor(
        tutors_dir,
        "bad",
        'persona: "   "\n'
        "concepts:\n"
        "  - slug: concept-a\n"
        "    label: Concept A\n",
    )
    registry = TutorRegistry(tutors_dir)
    tutors, invalid = registry.load()
    assert "good" in tutors
    assert "bad" not in tutors
    assert any(
        item["id"] == "bad" and item["field"] == "persona" for item in invalid
    )


def test_bad_reference_url_rejected_naming_concept_slug(tmp_path):
    tutors_dir = tmp_path / "tutors"
    _write_tutor(tutors_dir, "good", _GOOD_BODY)
    _write_tutor(
        tutors_dir,
        "bad",
        "persona: You are a tutor.\n"
        "concepts:\n"
        "  - slug: concept-a\n"
        "    label: Concept A\n"
        "    references:\n"
        "      - title: Lesson\n"
        "        url: ftp://example.com/lesson\n"
        "  - slug: concept-b\n"
        "    label: Concept B\n"
        "    references:\n"
        "      - title: Lesson\n"
        "        url: example.com/lesson\n",
    )
    registry = TutorRegistry(tutors_dir)
    tutors, invalid = registry.load()
    assert "good" in tutors
    assert "bad" not in tutors
    url_errors = [item for item in invalid if item["field"].endswith(".url")]
    assert len(url_errors) == 2
    slugs = {item["field"].split("[")[1].split("]")[0] for item in url_errors}
    assert slugs == {"concept-a", "concept-b"}
    for item in url_errors:
        slug = item["field"].split("[")[1].split("]")[0]
        assert slug in item["error"]
        assert "http(s)" in item["error"]


def test_empty_reference_entry_rejected_naming_concept_slug(tmp_path):
    tutors_dir = tmp_path / "tutors"
    _write_tutor(tutors_dir, "good", _GOOD_BODY)
    _write_tutor(
        tutors_dir,
        "bad",
        "persona: You are a tutor.\n"
        "concepts:\n"
        "  - slug: concept-a\n"
        "    label: Concept A\n"
        "    references:\n"
        "      - title: \"\"\n"
        "        url: https://example.com/lesson\n"
        "      - title: Lesson\n"
        "        url: \"\"\n",
    )
    registry = TutorRegistry(tutors_dir)
    tutors, invalid = registry.load()
    assert "good" in tutors
    assert "bad" not in tutors
    assert len(invalid) == 2
    for item in invalid:
        assert "concept-a" in item["field"]
        assert "concept-a" in item["error"]


def test_hot_reload_serves_edits_within_same_second(tmp_path):
    tutors_dir = tmp_path / "tutors"
    _write_tutor(tutors_dir, "hot", _GOOD_BODY)
    tutor_yaml = tutors_dir / "hot" / "tutor.yaml"
    registry = TutorRegistry(tutors_dir)

    # Stamp, then cache the first version at that stamp.
    stamp = time.time()
    os.utime(tutor_yaml, (stamp, stamp))
    assert registry.get("hot").age_range is None

    # Rewrite with a new field and force the exact same mtime so only the
    # size half of the (mtime_ns, size) cache key can notice the edit.
    tutor_yaml.write_text(
        "title: hot Tutor\n"
        "subject: Math\n"
        "description: hot\n"
        'age_range: "9"\n'
        + _GOOD_BODY
    )
    os.utime(tutor_yaml, (stamp, stamp))

    assert registry.get("hot").age_range == "9"
