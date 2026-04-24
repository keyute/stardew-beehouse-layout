"""Solution scoring."""

from __future__ import annotations

from beehouse_layout.constants import TILE_POT

# Scoring weights (lexicographic: beehouse >> steps >> pots >> obstacle penalty)
SCORE_BEEHOUSE = 10000
SCORE_STEP = -1
SCORE_POT = -50
SCORE_OBSTACLE_DIAGONAL = -100
from beehouse_layout.solver.constraints import classify_beehouse_access
from beehouse_layout.solver.tile_info import TileInfo
from beehouse_layout.solver.types import Solution, TileState


def score_solution(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
    tour_steps: int = 0,
) -> Solution:
    """Compute full metrics and score for a layout."""
    beehouse_count = 0
    flower_count = 0
    pot_count = 0
    obstacle_diagonal_count = 0

    for pos, state in assignments.items():
        if state == TileState.BEEHOUSE:
            beehouse_count += 1
            access = classify_beehouse_access(pos, tile_info, assignments)
            if access == "hard":
                obstacle_diagonal_count += 1
        elif state == TileState.FLOWER:
            flower_count += 1
            if tile_info.tile_type[pos] == TILE_POT:
                pot_count += 1

    score = (
        SCORE_BEEHOUSE * beehouse_count
        + SCORE_STEP * tour_steps
        + SCORE_POT * pot_count
        + SCORE_OBSTACLE_DIAGONAL * obstacle_diagonal_count
    )

    return Solution(
        assignments=dict(assignments),
        beehouse_count=beehouse_count,
        flower_count=flower_count,
        pot_count=pot_count,
        tour_steps=tour_steps,
        obstacle_diagonal_count=obstacle_diagonal_count,
        score=score,
    )
