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

    def set_problem(self, problem: dict[str, Any]) -> None:
        new_concept = problem.get("concept_slug")
        self.current_problem = problem
        if new_concept != self.current_concept:
            self.current_concept = new_concept
            self._publish_concept()

    def clear_problem(self) -> None:
        self.current_problem = None
        if self.current_concept is not None:
            self.current_concept = None
            self._publish_concept()

    def _publish_concept(self) -> None:
        if self.room is None:
            return
        try:
            payload = json.dumps({"type": "concept_active", "slug": self.current_concept})
            self.room.local_participant.publish_data(
                payload,
                topic="tutor:concept",
                reliable=True,
            )
            logger.debug("Published concept change: %s", self.current_concept)
        except Exception as exc:
            logger.warning("Failed to publish concept change: %s", exc)
