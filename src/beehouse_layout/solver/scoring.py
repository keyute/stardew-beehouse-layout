"""Solution scoring."""

from __future__ import annotations

from beehouse_layout.constants import TILE_POT

# Scoring weights approximate the lexicographic objective:
# beehouses >> steps >> route shape >> pots >> hard access.
SCORE_BEEHOUSE = 1_000_000_000_000
SCORE_STEP = -1_000_000
SCORE_ROUTE_TURN = -1_000
SCORE_ROUTE_REVISIT = -100
SCORE_POT = -10
SCORE_OBSTACLE_DIAGONAL = -1
from beehouse_layout.solver.constraints import classify_beehouse_access
from beehouse_layout.solver.tile_info import TileInfo
from beehouse_layout.solver.types import Solution, TileState


def score_solution(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
    tour_steps: int = 0,
    route_turns: int = 0,
    route_revisits: int = 0,
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
        + SCORE_ROUTE_TURN * route_turns
        + SCORE_ROUTE_REVISIT * route_revisits
        + SCORE_POT * pot_count
        + SCORE_OBSTACLE_DIAGONAL * obstacle_diagonal_count
    )
    score_key = (
        beehouse_count,
        -tour_steps,
        -route_turns,
        -route_revisits,
        -pot_count,
        -obstacle_diagonal_count,
    )

    return Solution(
        assignments=dict(assignments),
        beehouse_count=beehouse_count,
        flower_count=flower_count,
        pot_count=pot_count,
        tour_steps=tour_steps,
        route_turns=route_turns,
        route_revisits=route_revisits,
        obstacle_diagonal_count=obstacle_diagonal_count,
        score=score,
        score_key=score_key,
    )
