from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


class Reference(BaseModel):
    title: str
    url: str


class Concept(BaseModel):
    slug: str
    label: str
    references: list[Reference] = Field(default_factory=list)


class Answer(BaseModel):
    acceptable: list[str]
    reason: str
    hint: str


class Problem(BaseModel):
    id: str
    concept_slug: str
    question: str
    answer: Answer


class Tutor(BaseModel):
    id: str
    title: str
    subject: str
    description: str
    age_range: str | None = None
    persona: str
    level_labels: dict[int, str] | None = None
    concepts: list[Concept]
    problems: list[Problem] = Field(default_factory=list)

    @property
    def concept_by_slug(self) -> dict[str, Concept]:
        return {c.slug: c for c in self.concepts}

    @property
    def problems_by_concept(self) -> dict[str, list[Problem]]:
        groups: dict[str, list[Problem]] = {}
        for p in self.problems:
            groups.setdefault(p.concept_slug, []).append(p)
        return groups


class TutorNotFound(Exception):
    def __init__(self, tutor_id: str, available: list[str]):
        self.tutor_id = tutor_id
        self.available = available
        super().__init__(
            f"Tutor '{tutor_id}' not found. Available: {', '.join(sorted(available))}"
        )


class TutorRegistry:
    """Load, validate, and cache tutors from a directory layout.

    Layout: <tutors_dir>/<id>/tutor.yaml and optional <id>/problems.yaml.
    The directory name is the canonical tutor id. The registry caches by
    file (mtime_ns, size) and reloads automatically when files change, so
    a same-second edit with a different size is still picked up. One invalid
    tutor does not break loading of the others.
    """

    def __init__(self, tutors_dir: str | Path) -> None:
        self.tutors_dir = Path(tutors_dir)
        self._tutors: dict[str, Tutor] = {}
        self._invalid: list[dict[str, Any]] = []
        self._stamps: dict[Path, tuple[int, int]] = {}

    def _scan(self) -> dict[Path, tuple[int, int]]:
        """Return {path: (mtime_ns, size)} for all tutor content files."""
        stamps: dict[Path, tuple[int, int]] = {}
        if not self.tutors_dir.exists() or not self.tutors_dir.is_dir():
            return stamps
        for subdir in sorted(self.tutors_dir.iterdir()):
            if not subdir.is_dir():
                continue
            for name in ("tutor.yaml", "problems.yaml"):
                path = subdir / name
                if path.exists():
                    st = path.stat()
                    stamps[path] = (st.st_mtime_ns, st.st_size)
        return stamps

    def load(self) -> tuple[dict[str, Tutor], list[dict[str, Any]]]:
        """Load all valid tutors and return (tutors, invalid).

        Performs a single directory scan per call; reloads the cached tutors
        only when the scan differs from the cached stamps.
        """
        current = self._scan()
        if current == self._stamps:
            return self._tutors.copy(), list(self._invalid)
        tutors: dict[str, Tutor] = {}
        invalid: list[dict[str, Any]] = []

        if self.tutors_dir.exists() and self.tutors_dir.is_dir():
            for subdir in sorted(self.tutors_dir.iterdir()):
                if not subdir.is_dir():
                    continue
                tutor_id = subdir.name
                tutor_yaml = subdir / "tutor.yaml"
                if not tutor_yaml.exists():
                    continue
                problems_yaml = subdir / "problems.yaml"
                try:
                    with open(tutor_yaml, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f) or {}
                    data["id"] = tutor_id

                    problems: list[dict[str, Any]] = []
                    if problems_yaml.exists():
                        with open(problems_yaml, "r", encoding="utf-8") as f:
                            pdata = yaml.safe_load(f) or {}
                        problems = pdata.get("problems", []) or []

                    tutor = Tutor(**data, problems=problems)
                    errors = self._validate(tutor, tutor_yaml)
                    if errors:
                        for field, reason in errors:
                            logger.warning(
                                "Invalid tutor %s: %s - %s",
                                tutor_yaml,
                                field,
                                reason,
                            )
                            invalid.append(
                                {"id": tutor_id, "file": str(tutor_yaml), "field": field, "error": reason}
                            )
                    else:
                        tutors[tutor_id] = tutor
                except ValidationError as exc:
                    logger.warning("Invalid tutor %s: %s", tutor_yaml, exc)
                    invalid.append(
                        {"id": tutor_id, "file": str(tutor_yaml), "field": "", "error": str(exc)}
                    )
                except Exception as exc:
                    logger.warning("Invalid tutor %s: %s", tutor_yaml, exc)
                    invalid.append(
                        {"id": tutor_id, "file": str(tutor_yaml), "field": "", "error": f"{type(exc).__name__}: {exc}"}
                    )

        self._tutors = tutors
        self._invalid = invalid
        self._stamps = current
        return tutors.copy(), list(invalid)

    def _validate(
        self, tutor: Tutor, tutor_yaml: Path
    ) -> list[tuple[str, str]]:
        errors: list[tuple[str, str]] = []

        if not tutor.persona or not tutor.persona.strip():
            errors.append(("persona", "persona must be non-empty"))

        # At least one concept; all([]) is True, so an empty list needs an
        # explicit check.
        if not tutor.concepts:
            errors.append(("concepts", "tutor must define at least one concept"))

        # Unique, non-empty concept slugs.
        slugs = [c.slug for c in tutor.concepts]
        if not all(slugs):
            errors.append(("concepts[].slug", "concept slugs must be non-empty"))
        if len(slugs) != len(set(slugs)):
            errors.append(("concepts[].slug", "concept slugs must be unique"))

        # Reference entries must be non-empty and point at http(s) URLs.
        # Reference.url is a plain string so this check can name the concept.
        for concept in tutor.concepts:
            for i, ref in enumerate(concept.references):
                if not ref.title.strip():
                    errors.append(
                        (
                            f"concepts[{concept.slug}].references[{i}].title",
                            f"reference title must be non-empty (concept '{concept.slug}')",
                        )
                    )
                url = ref.url.strip().lower()
                if not url.startswith(("http://", "https://")):
                    errors.append(
                        (
                            f"concepts[{concept.slug}].references[{i}].url",
                            f"reference url must be an http(s) URL (concept '{concept.slug}')",
                        )
                    )

        # Problem references must resolve and ids must be unique.
        problem_ids = [p.id for p in tutor.problems]
        if len(problem_ids) != len(set(problem_ids)):
            errors.append(("problems[].id", "problem ids must be unique"))

        concept_slugs = set(slugs)
        for p in tutor.problems:
            if p.concept_slug not in concept_slugs:
                errors.append(
                    (
                        f"problems[].concept_slug",
                        f"problem '{p.id}' references unknown concept '{p.concept_slug}'",
                    )
                )
            if not p.answer.acceptable:
                errors.append(
                    (
                        f"problems[{p.id}].answer.acceptable",
                        "acceptable answers must be non-empty",
                    )
                )

        return errors

    def get(self, tutor_id: str) -> Tutor:
        self.load()
        if tutor_id not in self._tutors:
            raise TutorNotFound(tutor_id, list(self._tutors.keys()))
        return self._tutors[tutor_id]

    def list(self) -> list[Tutor]:
        self.load()
        return sorted(self._tutors.values(), key=lambda t: t.id)

    def invalid(self) -> list[dict[str, Any]]:
        self.load()
        return list(self._invalid)
