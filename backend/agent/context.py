from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from lib.state import StateService
from lib.tutors import Tutor

logger = logging.getLogger(__name__)


@dataclass
class SessionContext:
    session_id: str
    state: StateService
    tutor: Tutor
    room: Any | None = None
    current_problem: dict[str, Any] | None = None
    current_concept: str | None = field(default=None, init=False)
    # Last concept we actually worked on; it differs from current_concept
    # while no problem is active.
    _active_concept: str | None = field(default=None, init=False, repr=False)
    # Concept we just moved away from; it is marked as covered by the next
    # async flush, because the switch itself is detected synchronously.
    _left_concept: str | None = field(default=None, init=False, repr=False)
    # True when the active concept changed and still has to be published.
    _concept_publish_pending: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        # Every mastery write notifies us, so the browser gets a push on the
        # "tutor:mastery" topic instead of waiting for its next poll.
        self.state.on_mastery_update = self._publish_mastery_update

    def set_problem(self, problem: dict[str, Any]) -> None:
        new_concept = problem.get("concept_slug")
        self.current_problem = problem
        if new_concept != self.current_concept:
            self._switch_concept(new_concept)

    def clear_problem(self) -> None:
        self.current_problem = None
        if self.current_concept is not None:
            self._switch_concept(None)

    def _switch_concept(self, new_concept: str | None) -> None:
        """Record a concept change and remember the concept we are leaving.

        Only a move to a *different* concept counts as leaving one: clearing
        the problem (new_concept=None) just ends the current question, and the
        agent may well come back to the same concept.
        """
        self.current_concept = new_concept
        if new_concept:
            if self._active_concept and self._active_concept != new_concept:
                self._left_concept = self._active_concept
            self._active_concept = new_concept
        self._concept_publish_pending = True

    async def publish_concept(self) -> None:
        """Publish the active concept to the room.

        The SDK's publish_data is a coroutine, so it has to be awaited;
        the publish is therefore driven from the async tool paths and not
        from the synchronous concept switch.
        """
        if not self._concept_publish_pending:
            return
        self._concept_publish_pending = False
        if self.room is None:
            return
        try:
            payload = json.dumps({"type": "concept_active", "slug": self.current_concept})
            await self.room.local_participant.publish_data(
                payload,
                topic="tutor:concept",
                reliable=True,
            )
            logger.debug("Published concept change: %s", self.current_concept)
        except Exception as exc:
            logger.warning("Failed to publish concept change: %s", exc)

    async def flush_covered(self) -> None:
        """Mark the concept we just left as covered.

        Called after a concept switch so a concept that was finished shows
        progress in the UI even when no answer was ever graded for it.
        """
        slug = self._left_concept
        if not slug:
            return
        self._left_concept = None
        try:
            await self.state.mark_covered(self.tutor.id, slug)
        except Exception as exc:
            logger.warning("Failed to mark concept %s as covered: %s", slug, exc)

    async def _publish_mastery_update(self, tutor_id: str, slug: str) -> None:
        """Push a mastery change to the room so the UI updates right away."""
        if self.room is None:
            return
        try:
            payload = json.dumps({"type": "mastery_updated", "slug": slug})
            await self.room.local_participant.publish_data(
                payload,
                topic="tutor:mastery",
                reliable=True,
            )
        except Exception as exc:
            logger.warning("Failed to publish mastery update for %s: %s", slug, exc)
