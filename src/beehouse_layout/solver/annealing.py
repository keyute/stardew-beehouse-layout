"""Phase 2: Simulated annealing refinement of beehouse layouts."""

from __future__ import annotations

import math
import random
import time
from collections.abc import Callable

from beehouse_layout.solver.constraints import (
    TileInfo,
    check_connectivity,
    check_flower_coverage,
    check_flower_safety,
    classify_beehouse_access,
    is_walkable,
    score_solution,
)
from beehouse_layout.solver.tour import optimize_tour
from beehouse_layout.solver.types import Solution, TileState

# SA parameters
INITIAL_TEMP = 100.0
COOLING_RATE = 0.9999
MIN_TEMP = 0.01
REPORT_INTERVAL_SECS = 10


def _try_add_beehouse(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
) -> tuple[int, int] | None:
    """Try to place a beehouse on a random empty beehouse-eligible tile."""
    candidates = [
        pos
        for pos in tile_info.beehouse_tiles
        if assignments.get(pos, TileState.EMPTY) == TileState.EMPTY
    ]
    if not candidates:
        return None
    pos = random.choice(candidates)
    assignments[pos] = TileState.BEEHOUSE

    # Validate
    if not check_flower_coverage(pos, tile_info, assignments):
        del assignments[pos]
        return None
    if classify_beehouse_access(pos, tile_info, assignments) is None:
        del assignments[pos]
        return None
    # Check flower safety of adjacent flowers
    for nb in tile_info.cardinal_neighbors[pos]:
        if assignments.get(nb) == TileState.FLOWER:
            if not check_flower_safety(nb, tile_info, assignments):
                del assignments[pos]
                return None
    # Check that adjacent beehouses still have access
    for nb in tile_info.all_neighbors[pos]:
        if assignments.get(nb) == TileState.BEEHOUSE:
            if classify_beehouse_access(nb, tile_info, assignments) is None:
                del assignments[pos]
                return None
    # Check connectivity (placing beehouse removes walkable tile)
    if not check_connectivity(tile_info, assignments):
        del assignments[pos]
        return None
    return pos


def _try_remove_beehouse(
    assignments: dict[tuple[int, int], TileState],
) -> tuple[int, int] | None:
    """Remove a random beehouse."""
    beehouses = [
        pos for pos, state in assignments.items() if state == TileState.BEEHOUSE
    ]
    if not beehouses:
        return None
    pos = random.choice(beehouses)
    del assignments[pos]
    return pos


def _try_add_flower_cluster(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
) -> bool:
    """Place a flower + beehouses on all cardinal neighbors as a unit.

    This solves the chicken-and-egg problem: flowers need shielding beehouses,
    beehouses need flowers in range. Placing them together ensures both
    constraints are satisfied from the start.
    """
    candidates = [
        pos
        for pos in tile_info.flower_tiles
        if assignments.get(pos, TileState.EMPTY) == TileState.EMPTY
    ]
    if not candidates:
        return False
    pos = random.choice(candidates)

    # Check all cardinal neighbors can be shielded (beehouse-eligible or obstacle)
    shield_positions: list[tuple[int, int]] = []
    for nb in tile_info.cardinal_neighbors[pos]:
        if nb in tile_info.obstacle_tiles:
            continue  # obstacles shield naturally
        if nb not in tile_info.beehouse_tiles:
            return False  # can't shield this side
        if assignments.get(nb, TileState.EMPTY) == TileState.EMPTY:
            shield_positions.append(nb)
        elif assignments.get(nb) in (TileState.BEEHOUSE, TileState.FLOWER):
            continue  # already shielded
        else:
            return False

    # Save state
    saved = dict(assignments)

    # Place flower and shielding beehouses
    assignments[pos] = TileState.FLOWER
    for sp in shield_positions:
        assignments[sp] = TileState.BEEHOUSE

    # Validate flower safety
    if not check_flower_safety(pos, tile_info, assignments):
        assignments.clear()
        assignments.update(saved)
        return False

    # Validate all new beehouses are accessible
    for sp in shield_positions:
        if classify_beehouse_access(sp, tile_info, assignments) is None:
            assignments.clear()
            assignments.update(saved)
            return False

    # Check adjacent existing beehouses still have access
    all_placed = {pos} | set(shield_positions)
    for placed in all_placed:
        for nb in tile_info.all_neighbors[placed]:
            if nb not in all_placed and assignments.get(nb) == TileState.BEEHOUSE:
                if classify_beehouse_access(nb, tile_info, assignments) is None:
                    assignments.clear()
                    assignments.update(saved)
                    return False

    # Check connectivity (multiple tiles removed from walkable set)
    if not check_connectivity(tile_info, assignments):
        assignments.clear()
        assignments.update(saved)
        return False

    return True


def _try_remove_flower(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
) -> tuple[int, int] | None:
    """Remove a random flower. Removes dependent beehouses that lose coverage."""
    flowers = [
        pos for pos, state in assignments.items() if state == TileState.FLOWER
    ]
    if not flowers:
        return None
    pos = random.choice(flowers)
    del assignments[pos]

    # Remove beehouses that lost flower coverage
    to_remove = []
    for bh_pos, state in assignments.items():
        if state == TileState.BEEHOUSE:
            if not check_flower_coverage(bh_pos, tile_info, assignments):
                to_remove.append(bh_pos)
    for bh_pos in to_remove:
        del assignments[bh_pos]

    return pos


def _try_move_flower(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
) -> bool:
    """Try to move a flower to a nearby position."""
    flowers = [
        pos for pos, state in assignments.items() if state == TileState.FLOWER
    ]
    if not flowers:
        return False
    old_pos = random.choice(flowers)

    # Find nearby empty flower-eligible tiles
    candidates = []
    for nb in tile_info.flower_diamond[old_pos]:
        if nb in tile_info.flower_tiles:
            if assignments.get(nb, TileState.EMPTY) == TileState.EMPTY:
                candidates.append(nb)
    if not candidates:
        return False

    new_pos = random.choice(candidates)

    # Save state for rollback
    saved = dict(assignments)

    # Move
    del assignments[old_pos]
    assignments[new_pos] = TileState.FLOWER

    # Validate flower safety
    if not check_flower_safety(new_pos, tile_info, assignments):
        assignments.clear()
        assignments.update(saved)
        return False

    # Remove beehouses that lost coverage
    to_remove = []
    for bh_pos, state in assignments.items():
        if state == TileState.BEEHOUSE:
            if not check_flower_coverage(bh_pos, tile_info, assignments):
                to_remove.append(bh_pos)
    for bh_pos in to_remove:
        del assignments[bh_pos]

    # Check connectivity (new_pos became non-walkable, old_pos became walkable)
    if not check_connectivity(tile_info, assignments):
        assignments.clear()
        assignments.update(saved)
        return False

    return True


def _quick_score(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
) -> float:
    """Fast score without tour computation (for SA acceptance)."""
    return score_solution(tile_info, assignments, tour_steps=0).score


def anneal(
    tile_info: TileInfo,
    initial_assignments: dict[tuple[int, int], TileState],
    duration_secs: float = 300.0,
    on_improvement: Callable[[Solution], None] | None = None,
) -> Solution:
    """Run simulated annealing to improve the layout.

    Args:
        tile_info: Precomputed map data.
        initial_assignments: Starting layout from greedy phase.
        duration_secs: Maximum time to run in seconds.
        on_improvement: Callback when a new best solution is found.

    Returns:
        Best solution found.
    """
    assignments = dict(initial_assignments)
    current_score = _quick_score(tile_info, assignments)

    best_assignments = dict(assignments)
    best_score = current_score

    temp = INITIAL_TEMP
    start_time = time.monotonic()
    last_report = start_time
    iterations = 0
    improvements = 0

    moves = [
        ("add_beehouse", 0.35),
        ("remove_beehouse", 0.1),
        ("add_flower_cluster", 0.2),
        ("remove_flower", 0.05),
        ("move_flower", 0.3),
    ]
    move_names = [m[0] for m in moves]
    move_weights = [m[1] for m in moves]

    while True:
        elapsed = time.monotonic() - start_time
        if elapsed >= duration_secs:
            break
        if temp < MIN_TEMP:
            temp = INITIAL_TEMP  # reheat

        # Save state for rollback
        saved = dict(assignments)

        # Pick a random move
        move = random.choices(move_names, weights=move_weights, k=1)[0]

        success = True
        if move == "add_beehouse":
            success = _try_add_beehouse(tile_info, assignments) is not None
        elif move == "remove_beehouse":
            success = _try_remove_beehouse(assignments) is not None
        elif move == "add_flower_cluster":
            success = _try_add_flower_cluster(tile_info, assignments)
        elif move == "remove_flower":
            success = _try_remove_flower(tile_info, assignments) is not None
        elif move == "move_flower":
            success = _try_move_flower(tile_info, assignments)

        if not success:
            iterations += 1
            temp *= COOLING_RATE
            continue

        new_score = _quick_score(tile_info, assignments)
        delta = new_score - current_score

        # Accept or reject
        if delta > 0 or random.random() < math.exp(delta / temp):
            current_score = new_score
            if new_score > best_score:
                best_score = new_score
                best_assignments = dict(assignments)
                improvements += 1

                if on_improvement is not None:
                    tour_steps = optimize_tour(tile_info, assignments)
                    solution = score_solution(tile_info, assignments, tour_steps)
                    on_improvement(solution)
        else:
            # Rollback
            assignments.clear()
            assignments.update(saved)

        iterations += 1
        temp *= COOLING_RATE

        # Periodic progress report
        now = time.monotonic()
        if now - last_report >= REPORT_INTERVAL_SECS:
            bh_count = sum(
                1 for s in assignments.values() if s == TileState.BEEHOUSE
            )
            print(
                f"  SA: {iterations} iters, {elapsed:.0f}s, "
                f"temp={temp:.2f}, beehouses={bh_count}, "
                f"improvements={improvements}"
            )
            last_report = now

    # Final scoring with tour
    tour_steps = optimize_tour(tile_info, best_assignments)
    return score_solution(tile_info, best_assignments, tour_steps)
