"""Unit tests for the agent's tutor_id resolution from dispatch metadata.

No live room or worker process is started; only the metadata helper runs.
"""

import json
from pathlib import Path

import pytest

from agent.worker import _tutor_from_metadata
from lib.tutors import TutorRegistry


class _FakeJob:
    def __init__(self, metadata: str | None):
        self.metadata = metadata


class _FakeJobContext:
    def __init__(self, metadata: str | None):
        self.job = _FakeJob(metadata)


def _repo_registry() -> TutorRegistry:
    return TutorRegistry(Path(__file__).resolve().parents[2] / "tutors")


def test_tutor_id_parsed_from_job_metadata():
    ctx = _FakeJobContext(json.dumps({"tutor_id": "probability"}))
    tutor = _tutor_from_metadata(ctx, _repo_registry())
    assert tutor.id == "probability"
    assert tutor.concepts


def test_missing_tutor_id_in_metadata_raises():
    ctx = _FakeJobContext(json.dumps({"room": "x"}))
    with pytest.raises(RuntimeError, match="No tutor_id in dispatch metadata"):
        _tutor_from_metadata(ctx, _repo_registry())


def test_empty_metadata_raises():
    ctx = _FakeJobContext(None)
    with pytest.raises(RuntimeError, match="No tutor_id in dispatch metadata"):
        _tutor_from_metadata(ctx, _repo_registry())


def test_malformed_metadata_json_raises():
    ctx = _FakeJobContext("not-json")
    with pytest.raises(RuntimeError, match="Could not parse dispatch metadata"):
        _tutor_from_metadata(ctx, _repo_registry())


def test_unknown_tutor_id_raises_with_available():
    ctx = _FakeJobContext(json.dumps({"tutor_id": "nope"}))
    with pytest.raises(RuntimeError, match="Available"):
        _tutor_from_metadata(ctx, _repo_registry())
