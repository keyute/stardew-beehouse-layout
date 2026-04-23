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
