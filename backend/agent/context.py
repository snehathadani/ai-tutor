from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lib.state import StateService


@dataclass
class SessionContext:
    session_id: str
    state: StateService
    current_problem_id: str | None = None
    current_problem: dict[str, Any] | None = None
    current_concept: str | None = None
    started: bool = False

    def set_problem(self, problem: dict[str, Any]) -> None:
        self.current_problem = problem
        self.current_problem_id = problem.get("id")
        self.current_concept = problem.get("concept_slug")

    def clear_problem(self) -> None:
        self.current_problem = None
        self.current_problem_id = None
        self.current_concept = None
