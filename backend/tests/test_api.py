from pathlib import Path

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from fastapi.testclient import TestClient

from api import main as api_main
from lib.config import Settings, set_settings
from lib.state import StateService


def _repo_tutors_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "tutors"


@pytest_asyncio.fixture
async def state():
    state = StateService(redis_client=FakeRedis(decode_responses=True))
    await state.connect()
    return state


@pytest.fixture
def client(state):
    settings = Settings(
        livekit_url="wss://test.livekit.cloud",
        livekit_api_key="test-key",
        livekit_api_secret="test-secret",
        llm_provider="openai",
        llm_base_url="https://api.test.example",
        llm_api_key="test-llm",
        llm_model="test-model",
        redis_url="redis://unused",
        tutors_dir=str(_repo_tutors_dir()),
    )
    set_settings(settings)
    api_main.state_service = state
    api_main.tutor_registry = None

    with TestClient(api_main.app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_list_tutors(client):
    r = client.get("/api/tutors")
    assert r.status_code == 200
    data = r.json()
    assert "tutors" in data
    assert "invalid" in data
    ids = [t["id"] for t in data["tutors"]]
    assert "probability" in ids


def test_list_tutors_includes_concepts_references_and_level_labels(client):
    r = client.get("/api/tutors")
    assert r.status_code == 200
    data = r.json()
    probability = next(t for t in data["tutors"] if t["id"] == "probability")

    # concept_count stays consistent with the embedded concepts list.
    assert probability["concept_count"] == len(probability["concepts"])

    # A concept's references array is present so the frontend LinkCard can
    # render without a second fetch.
    sample_space = next(
        c for c in probability["concepts"] if c["slug"] == "sample-space"
    )
    assert sample_space["label"] == "Sample space and outcomes"
    assert sample_space["references"], "expected at least one reference"
    for ref in sample_space["references"]:
        assert set(ref) == {"title", "url"}
        assert ref["url"].startswith(("http://", "https://"))

    # level_labels comes through for the mastery panel.
    assert probability["level_labels"] == {
        "0": "Not started",
        "1": "Getting started",
        "2": "Building confidence",
        "3": "Ready to move on",
    }


def test_get_tutor(client):
    r = client.get("/api/tutors/probability")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "probability"
    assert len(data["concepts"]) == 8


def test_get_tutor_not_found(client):
    r = client.get("/api/tutors/unknown")
    assert r.status_code == 404
    data = r.json()
    assert data["detail"]["tutor_id"] == "unknown"
    assert "probability" in data["detail"]["available"]


def test_token(client):
    r = client.post(
        "/api/token",
        json={"room": "probability-test-room", "identity": "student", "tutor_id": "probability"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "token" in data
    assert data["url"] == "wss://test.livekit.cloud"
    assert "dispatch_error" in data
    parts = data["token"].split(".")
    assert len(parts) == 3


def test_token_requires_tutor_room_prefix(client):
    r = client.post(
        "/api/token",
        json={"room": "math-room", "identity": "student", "tutor_id": "probability"},
    )
    assert r.status_code == 400


def test_token_unknown_tutor(client):
    r = client.post(
        "/api/token",
        json={"room": "unknown-room", "identity": "student", "tutor_id": "unknown"},
    )
    assert r.status_code == 404
    data = r.json()
    assert data["detail"]["tutor_id"] == "unknown"
    assert "probability" in data["detail"]["available"]


def test_dispatch_reports_failure_for_fake_credentials(client):
    r = client.post(
        "/api/dispatch",
        json={"room": "probability-test-room", "tutor_id": "probability"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["dispatched"] is False
    assert data["error"]


def test_mastery_and_sessions(client):
    r = client.get("/api/mastery?tutor=probability&student=parth")
    assert r.status_code == 200
    assert "concepts" in r.json()

    r = client.get("/api/sessions?tutor=probability")
    assert r.status_code == 200
    assert r.json() == []


def test_mastery_requires_tutor(client):
    r = client.get("/api/mastery")
    assert r.status_code == 422
