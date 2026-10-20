from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any, Optional

import livekit.api as lkapi
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agent.prompts import CONCEPT_BY_SLUG, CONCEPTS
from lib.config import AGENT_NAME, Settings, get_settings
from lib.state import StateError, StateService

logger = logging.getLogger(__name__)

state_service: StateService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global state_service
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    if state_service is None:
        state_service = StateService(settings.redis_url)
        try:
            await state_service.connect(retries=10, delay=1.0)
        except StateError as exc:
            logger.error("Redis not reachable at startup: %s", exc)
            logger.warning("API will serve health but state endpoints will return 503 until Redis is back.")
    yield
    if state_service is not None:
        try:
            await state_service.close()
        except Exception as exc:
            logger.warning("Error closing Redis: %s", exc)


app = FastAPI(title="Probability Voice Tutor", lifespan=lifespan)


class TokenRequest(BaseModel):
    room: str
    identity: str


class TokenResponse(BaseModel):
    token: str
    url: str
    dispatch_error: Optional[str] = None


class DispatchRequest(BaseModel):
    room: str


class DispatchResponse(BaseModel):
    dispatched: bool
    error: Optional[str] = None


def _get_settings() -> Settings:
    return get_settings()


async def _dispatch_agent(room: str, settings: Settings) -> Optional[str]:
    """Request an explicit agent dispatch for a room. Returns an error message
    on failure, or None on success."""
    try:
        async with lkapi.LiveKitAPI(
            settings.livekit_url,
            settings.livekit_api_key,
            settings.livekit_api_secret,
        ) as api:
            dispatch = await asyncio.wait_for(
                api.agent_dispatch.create_dispatch(
                    lkapi.CreateAgentDispatchRequest(room=room, agent_name=AGENT_NAME)
                ),
                timeout=5.0,
            )
            logger.info("Dispatched agent %s to room %s: dispatch_id=%s", AGENT_NAME, room, dispatch.id)
            return None
    except asyncio.TimeoutError:
        msg = "Agent dispatch timed out"
        logger.error(msg)
        return msg
    except Exception as exc:
        msg = f"Agent dispatch failed: {exc}"
        logger.error(msg)
        return msg


@app.exception_handler(StateError)
async def _state_error_handler(request: Request, exc: StateError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": f"State store unavailable: {exc}"},
    )


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"ok": True}


@app.post("/api/token", response_model=TokenResponse)
async def mint_token(
    body: TokenRequest,
    settings: Settings = Depends(_get_settings),
) -> TokenResponse:
    try:
        token = (
            lkapi.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
            .with_identity(body.identity)
            .with_ttl(timedelta(seconds=3600))
            .with_grants(
                lkapi.VideoGrants(
                    room_join=True,
                    room=body.room,
                    can_publish=True,
                    can_subscribe=True,
                    can_publish_data=True,
                )
            )
            .to_jwt()
        )
    except Exception as exc:
        logger.error("Failed to mint token: %s", exc)
        raise HTTPException(status_code=500, detail="Could not mint LiveKit token") from exc
    dispatch_error = await _dispatch_agent(body.room, settings)
    return TokenResponse(token=token, url=settings.livekit_url, dispatch_error=dispatch_error)


@app.post("/api/dispatch", response_model=DispatchResponse)
async def dispatch_agent(
    body: DispatchRequest,
    settings: Settings = Depends(_get_settings),
) -> DispatchResponse:
    error = await _dispatch_agent(body.room, settings)
    if error:
        return DispatchResponse(dispatched=False, error=error)
    return DispatchResponse(dispatched=True)


@app.get("/api/mastery")
async def get_mastery() -> dict[str, Any]:
    if state_service is None:
        raise StateError("State service not initialized")
    raw = await state_service.get_mastery()
    concepts = []
    for concept in CONCEPTS:
        slug = concept["slug"]
        record = raw.get(slug, {})
        concepts.append(
            {
                "slug": slug,
                "label": concept["label"],
                "level": record.get("level", 0),
                "correct": record.get("correct", 0),
                "total": record.get("total", 0),
            }
        )
    return {"concepts": concepts}


@app.get("/api/sessions")
async def list_sessions() -> list[dict[str, Any]]:
    if state_service is None:
        raise StateError("State service not initialized")
    return await state_service.list_sessions()


@app.get("/api/sessions/{sid}/summary")
async def get_session_summary(sid: str) -> dict[str, Any]:
    if state_service is None:
        raise StateError("State service not initialized")
    summary = await state_service.get_summary(sid)
    if summary is None:
        raise HTTPException(status_code=404, detail="Summary not found")
    return summary


@app.get("/api/sessions/{sid}/transcript")
async def get_session_transcript(sid: str) -> list[dict[str, Any]]:
    if state_service is None:
        raise StateError("State service not initialized")
    return await state_service.get_transcript(sid)


@app.get("/api/concepts")
async def list_concepts() -> dict[str, Any]:
    return {"concepts": CONCEPTS}
