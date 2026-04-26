from dataclasses import dataclass, field
from enum import StrEnum


class TileState(StrEnum):
    EMPTY = "empty"
    BEEHOUSE = "beehouse"
    FLOWER = "flower"


@dataclass
class WorkerStatus:
    worker_id: int
    iterations: int
    elapsed_secs: float
    temperature: float
    beehouse_count: int
    improvements: int


@dataclass
class Solution:
    assignments: dict[tuple[int, int], TileState] = field(default_factory=dict)
    beehouse_count: int = 0
    flower_count: int = 0
    pot_count: int = 0
    tour_steps: int = 0
    obstacle_diagonal_count: int = 0
    score: float = 0.0


@dataclass
class MoveStats:
    attempts: int = 0
    valid: int = 0
    accepted: int = 0
    rejected: int = 0
    improvements: int = 0


@dataclass
class AnnealStats:
    move_stats: dict[str, MoveStats] = field(default_factory=dict)
    trajectory: list[dict] = field(default_factory=list)
