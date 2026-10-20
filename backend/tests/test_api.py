import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from fastapi.testclient import TestClient

from api import main as api_main
from lib.config import Settings, set_settings
from lib.state import StateService


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
    )
    set_settings(settings)
    api_main.state_service = state

    with TestClient(api_main.app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_token(client):
    r = client.post("/api/token", json={"room": "test-room", "identity": "student"})
    assert r.status_code == 200
    data = r.json()
    assert "token" in data
    assert data["url"] == "wss://test.livekit.cloud"
    assert "dispatch_error" in data
    parts = data["token"].split(".")
    assert len(parts) == 3


def test_dispatch_reports_failure_for_fake_credentials(client):
    r = client.post("/api/dispatch", json={"room": "test-room"})
    assert r.status_code == 200
    data = r.json()
    assert data["dispatched"] is False
    assert data["error"]


def test_mastery_and_sessions(client):
    r = client.get("/api/mastery")
    assert r.status_code == 200
    assert "concepts" in r.json()

    r = client.get("/api/sessions")
    assert r.status_code == 200
    assert r.json() == []
