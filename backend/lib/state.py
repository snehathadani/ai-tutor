from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import redis.asyncio as redis
from livekit.agents.llm import ChatContext

logger = logging.getLogger(__name__)

NAMESPACE = "tutor"


def _mastery_key(tutor_id: str) -> str:
    return f"{NAMESPACE}:{tutor_id}:mastery"


def _sessions_zset_key(tutor_id: str) -> str:
    return f"{NAMESPACE}:{tutor_id}:sessions"


def _session_transcript_key(tutor_id: str, sid: str) -> str:
    return f"{NAMESPACE}:{tutor_id}:session:{sid}:transcript"


def _session_meta_key(tutor_id: str, sid: str) -> str:
    return f"{NAMESPACE}:{tutor_id}:session:{sid}:meta"


def _session_summary_key(tutor_id: str, sid: str) -> str:
    return f"{NAMESPACE}:{tutor_id}:session:{sid}:summary"


def _session_chat_key(tutor_id: str, sid: str) -> str:
    return f"{NAMESPACE}:{tutor_id}:session:{sid}:chat_ctx"


class StateError(Exception):
    pass


def _default_concept() -> dict[str, Any]:
    return {
        "level": 0,
        "correct": 0,
        "total": 0,
        "streak": 0,
        "weighted_correct": 0.0,
        "weighted_total": 0.0,
        "updated_ts": 0.0,
    }


def _compute_level(record: dict[str, Any]) -> int:
    weighted_total = record.get("weighted_total", 0.0)
    if weighted_total < 1.0:
        return 0
    ratio = record.get("weighted_correct", 0.0) / weighted_total
    streak = record.get("streak", 0)
    if streak >= 5 and ratio >= 0.8:
        return 3
    if streak >= 3 and ratio >= 0.7:
        return 2
    if ratio >= 0.5:
        return 1
    return 0


@dataclass
class StateService:
    redis_url: str = ""
    redis_client: redis.Redis | None = None
    _redis: redis.Redis | None = None

    async def connect(self, retries: int = 10, delay: float = 1.0) -> None:
        if self.redis_client is not None:
            self._redis = self.redis_client
            try:
                await self._redis.ping()
            except Exception as exc:
                raise StateError(f"Could not ping provided Redis client: {exc}") from exc
            return

        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                self._redis = redis.from_url(self.redis_url, decode_responses=True)
                await self._redis.ping()
                logger.info("Connected to Redis at %s", self.redis_url)
                return
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Redis connection attempt %d/%d failed: %s", attempt + 1, retries, exc
                )
                if attempt < retries - 1:
                    await asyncio.sleep(delay)
        raise StateError(f"Could not connect to Redis after {retries} attempts: {last_exc}")

    async def close(self) -> None:
        if self._redis is not None:
            try:
                await self._redis.aclose()
            finally:
                self._redis = None

    def _ensure(self) -> redis.Redis:
        if self._redis is None:
            raise StateError("Redis client is not connected")
        return self._redis

    async def _safe(self, coro: Any, operation: str) -> Any:
        try:
            return await coro
        except redis.RedisError as exc:
            logger.error("Redis error during %s: %s", operation, exc)
            raise StateError(f"Redis unavailable ({operation}): {exc}") from exc

    async def get_mastery(self, tutor_id: str) -> dict[str, dict[str, Any]]:
        r = self._ensure()
        data = await self._safe(r.hgetall(_mastery_key(tutor_id)), "get_mastery")
        result: dict[str, dict[str, Any]] = {}
        for slug, raw in data.items():
            record = json.loads(raw)
            record["level"] = _compute_level(record)
            result[slug] = record
        return result

    async def update_mastery(
        self, tutor_id: str, slug: str, correct: bool, weight: float = 1.0
    ) -> None:
        r = self._ensure()
        key = _mastery_key(tutor_id)
        raw = await self._safe(r.hget(key, slug), "update_mastery")
        record = json.loads(raw) if raw else _default_concept()
        record["total"] = record.get("total", 0) + 1
        record["weighted_total"] = record.get("weighted_total", 0.0) + weight
        record["updated_ts"] = time.time()
        if correct:
            record["correct"] = record.get("correct", 0) + 1
            record["weighted_correct"] = record.get("weighted_correct", 0.0) + weight
            record["streak"] = record.get("streak", 0) + 1
        else:
            record["streak"] = 0
        record["level"] = _compute_level(record)
        await self._safe(r.hset(key, slug, json.dumps(record)), "update_mastery")

    async def record_observation(self, tutor_id: str, slug: str, signal: str) -> None:
        if signal not in ("got_it", "struggling"):
            return
        correct = signal == "got_it"
        await self.update_mastery(tutor_id, slug, correct=correct, weight=0.5)

    async def add_transcript_turn(
        self, tutor_id: str, sid: str, role: str, text: str, concept: str | None = None
    ) -> None:
        r = self._ensure()
        turn = {
            "role": role,
            "text": text,
            "ts": time.time(),
            "concept": concept,
        }
        key = _session_transcript_key(tutor_id, sid)
        await self._safe(r.rpush(key, json.dumps(turn)), "add_transcript_turn")
        await self._safe(r.expire(key, 7 * 24 * 60 * 60), "expire_transcript")

    async def get_transcript(self, tutor_id: str, sid: str) -> list[dict[str, Any]]:
        r = self._ensure()
        raw = await self._safe(
            r.lrange(_session_transcript_key(tutor_id, sid), 0, -1), "get_transcript"
        )
        return [json.loads(item) for item in raw]

    async def set_session_meta(
        self, tutor_id: str, sid: str, **fields: Any
    ) -> None:
        r = self._ensure()
        key = _session_meta_key(tutor_id, sid)
        await self._safe(r.hset(key, mapping=fields), "set_session_meta")
        await self._safe(r.expire(key, 7 * 24 * 60 * 60), "expire_meta")

    async def get_session_meta(self, tutor_id: str, sid: str) -> dict[str, Any]:
        r = self._ensure()
        data = await self._safe(r.hgetall(_session_meta_key(tutor_id, sid)), "get_session_meta")
        return dict(data)

    async def start_session(self, tutor_id: str, sid: str) -> None:
        now = time.time()
        await self.set_session_meta(tutor_id, sid, started_ts=now, status="active", concept_count=0)
        await self._safe(
            self._ensure().zadd(_sessions_zset_key(tutor_id), {sid: now}),
            "start_session",
        )

    async def end_session(
        self, tutor_id: str, sid: str, summary: dict[str, Any] | None = None
    ) -> None:
        r = self._ensure()
        now = time.time()
        await self.set_session_meta(tutor_id, sid, ended_ts=now, status="ended")
        if summary is not None:
            await self.set_summary(tutor_id, sid, summary)

    async def set_summary(
        self, tutor_id: str, sid: str, summary: dict[str, Any]
    ) -> None:
        r = self._ensure()
        key = _session_summary_key(tutor_id, sid)
        await self._safe(r.set(key, json.dumps(summary)), "set_summary")
        await self._safe(r.expire(key, 30 * 24 * 60 * 60), "expire_summary")

    async def get_summary(self, tutor_id: str, sid: str) -> dict[str, Any] | None:
        r = self._ensure()
        raw = await self._safe(r.get(_session_summary_key(tutor_id, sid)), "get_summary")
        return json.loads(raw) if raw else None

    async def list_sessions(self, tutor_id: str) -> list[dict[str, Any]]:
        r = self._ensure()
        sids = await self._safe(
            r.zrevrange(_sessions_zset_key(tutor_id), 0, -1),
            "list_sessions",
        )
        result = []
        for sid in sids:
            meta = await self.get_session_meta(tutor_id, sid)
            summary = await self.get_summary(tutor_id, sid)
            result.append(
                {
                    "sid": sid,
                    "started_ts": meta.get("started_ts"),
                    "ended_ts": meta.get("ended_ts"),
                    "status": meta.get("status"),
                    "summary": summary,
                }
            )
        return result

    async def save_chat_context(
        self, tutor_id: str, sid: str, chat_ctx: ChatContext
    ) -> None:
        r = self._ensure()
        key = _session_chat_key(tutor_id, sid)
        payload = json.dumps(chat_ctx.to_dict())
        await self._safe(r.set(key, payload), "save_chat_context")
        await self._safe(r.expire(key, 7 * 24 * 60 * 60), "expire_chat_ctx")

    async def load_chat_context(self, tutor_id: str, sid: str) -> ChatContext:
        r = self._ensure()
        raw = await self._safe(r.get(_session_chat_key(tutor_id, sid)), "load_chat_context")
        if not raw:
            return ChatContext.empty()
        try:
            return ChatContext.from_dict(json.loads(raw))
        except Exception as exc:
            logger.error("Failed to load chat context for %s/%s: %s", tutor_id, sid, exc)
            return ChatContext.empty()
