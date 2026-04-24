"""Phase 2: Simulated annealing refinement of beehouse layouts."""

from __future__ import annotations

import math
import multiprocessing.synchronize
import random
import time
from collections.abc import Callable

from beehouse_layout.constants import BEEHOUSE_TILES
from beehouse_layout.solver.constraints import (
    check_connectivity,
    check_flower_coverage,
    check_flower_safety,
    classify_beehouse_access,
)
from beehouse_layout.solver.greedy import _rollback, _try_place_flower_group
from beehouse_layout.solver.scoring import score_solution
from beehouse_layout.solver.tile_info import TileInfo, is_walkable
from beehouse_layout.solver.tour import optimize_tour
from beehouse_layout.solver.types import Solution, TileState

# SA parameters
INITIAL_TEMP = 100.0
COOLING_RATE = 0.9999
MIN_TEMP = 0.01
REPORT_INTERVAL_SECS = 2


def _cascade_remove_unsafe(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
    freed_pos: tuple[int, int],
    changeset: dict[tuple[int, int], TileState | None] | None = None,
) -> None:
    """Remove flowers that became unsafe after freed_pos became walkable, and cascade."""
    for nb in tile_info.all_neighbors[freed_pos]:
        if assignments.get(nb) == TileState.FLOWER:
            if not check_flower_safety(nb, tile_info, assignments):
                if changeset is not None and nb not in changeset:
                    changeset[nb] = assignments[nb]
                del assignments[nb]
                _cascade_remove_unsafe(tile_info, assignments, nb, changeset)
    # Remove beehouses that lost flower coverage (only those in range of freed_pos)
    to_remove = [
        nb for nb in tile_info.flower_diamond[freed_pos]
        if assignments.get(nb) == TileState.BEEHOUSE
        and not check_flower_coverage(nb, tile_info, assignments)
    ]
    for p in to_remove:
        if changeset is not None and p not in changeset:
            changeset[p] = assignments[p]
        del assignments[p]
    # Removed beehouses are now walkable — cascade for each
    for p in to_remove:
        _cascade_remove_unsafe(tile_info, assignments, p, changeset)


def _try_add_beehouse(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
    *,
    no_hard: bool = False,
) -> dict[tuple[int, int], TileState | None] | None:
    """Try to place a beehouse on a random empty beehouse-eligible tile.

    Returns changeset on success (for rollback), or None on failure.
    """
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
    access = classify_beehouse_access(pos, tile_info, assignments)
    if access is None or (no_hard and access == "hard"):
        del assignments[pos]
        return None
    # Check flower safety of adjacent flowers (all 8 directions)
    for nb in tile_info.all_neighbors[pos]:
        if assignments.get(nb) == TileState.FLOWER:
            if not check_flower_safety(nb, tile_info, assignments):
                del assignments[pos]
                return None
    # Check that adjacent beehouses still have access
    for nb in tile_info.all_neighbors[pos]:
        if assignments.get(nb) == TileState.BEEHOUSE:
            access_nb = classify_beehouse_access(nb, tile_info, assignments)
            if access_nb is None or (no_hard and access_nb == "hard"):
                del assignments[pos]
                return None
    # Check connectivity (placing beehouse removes walkable tile)
    if not check_connectivity(tile_info, assignments, removed_walkable={pos}):
        del assignments[pos]
        return None
    return {pos: None}


def _try_remove_beehouse(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
) -> dict[tuple[int, int], TileState | None] | None:
    """Remove a random beehouse. Cascade-removes exposed flowers and uncovered beehouses.

    Returns changeset on success (for rollback), or None on failure.
    """
    beehouses = [
        pos for pos, state in assignments.items() if state == TileState.BEEHOUSE
    ]
    if not beehouses:
        return None
    pos = random.choice(beehouses)
    changeset: dict[tuple[int, int], TileState | None] = {pos: assignments[pos]}
    del assignments[pos]
    # pos is now walkable — check if any adjacent flowers are exposed
    _cascade_remove_unsafe(tile_info, assignments, pos, changeset)
    return changeset


def _try_add_flower_cluster(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
    *,
    no_hard: bool = False,
) -> dict[tuple[int, int], TileState | None] | None:
    """Place a flower + beehouses on all 8 neighbors as a unit.

    This solves the chicken-and-egg problem: flowers need shielding beehouses,
    beehouses need flowers in range. Placing them together ensures both
    constraints are satisfied from the start.

    Returns changeset on success (for rollback), or None on failure.
    """
    candidates = [
        pos
        for pos in tile_info.flower_tiles
        if assignments.get(pos, TileState.EMPTY) == TileState.EMPTY
    ]
    if not candidates:
        return None
    pos = random.choice(candidates)

    # Check all 8 neighbors can be shielded (beehouse-eligible, obstacle, or map edge)
    shield_positions: list[tuple[int, int]] = []
    for nb in tile_info.all_neighbors[pos]:
        if nb in tile_info.obstacle_tiles:
            continue  # obstacles shield naturally
        if nb not in tile_info.beehouse_tiles:
            return None  # can't shield this side (e.g. entrance, walkway)
        if assignments.get(nb, TileState.EMPTY) == TileState.EMPTY:
            shield_positions.append(nb)
        elif assignments.get(nb) in (TileState.BEEHOUSE, TileState.FLOWER):
            continue  # already shielded
        else:
            return None

    # Build changeset (record old states before modification)
    changeset: dict[tuple[int, int], TileState | None] = {pos: assignments.get(pos)}
    for sp in shield_positions:
        changeset[sp] = assignments.get(sp)

    # Place flower and shielding beehouses
    assignments[pos] = TileState.FLOWER
    for sp in shield_positions:
        assignments[sp] = TileState.BEEHOUSE

    # Validate flower safety
    if not check_flower_safety(pos, tile_info, assignments):
        _rollback(assignments, changeset)
        return None

    # Validate all new beehouses are accessible
    for sp in shield_positions:
        access = classify_beehouse_access(sp, tile_info, assignments)
        if access is None or (no_hard and access == "hard"):
            _rollback(assignments, changeset)
            return None

    # Check adjacent existing beehouses still have access
    all_placed = {pos} | set(shield_positions)
    for placed in all_placed:
        for nb in tile_info.all_neighbors[placed]:
            if nb not in all_placed and assignments.get(nb) == TileState.BEEHOUSE:
                access = classify_beehouse_access(nb, tile_info, assignments)
                if access is None or (no_hard and access == "hard"):
                    _rollback(assignments, changeset)
                    return None

    # Check connectivity (multiple tiles removed from walkable set)
    removed = {pos} | set(shield_positions)
    if not check_connectivity(tile_info, assignments, removed_walkable=removed):
        _rollback(assignments, changeset)
        return None

    return changeset


def _try_remove_flower(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
) -> dict[tuple[int, int], TileState | None] | None:
    """Remove a random flower. Cascade-removes exposed flowers and uncovered beehouses.

    Returns changeset on success (for rollback), or None on failure.
    """
    flowers = [
        pos for pos, state in assignments.items() if state == TileState.FLOWER
    ]
    if not flowers:
        return None
    pos = random.choice(flowers)
    changeset: dict[tuple[int, int], TileState | None] = {pos: assignments[pos]}
    del assignments[pos]
    # pos is now walkable — cascade-remove exposed flowers and uncovered beehouses
    _cascade_remove_unsafe(tile_info, assignments, pos, changeset)
    return changeset


def _try_move_flower(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
    *,
    no_hard: bool = False,
) -> dict[tuple[int, int], TileState | None] | None:
    """Try to move a flower to a nearby position.

    Returns changeset on success (for rollback), or None on failure.
    """
    flowers = [
        pos for pos, state in assignments.items() if state == TileState.FLOWER
    ]
    if not flowers:
        return None
    old_pos = random.choice(flowers)

    # Find nearby empty flower-eligible tiles
    candidates = []
    for nb in tile_info.flower_diamond[old_pos]:
        if nb in tile_info.flower_tiles:
            if assignments.get(nb, TileState.EMPTY) == TileState.EMPTY:
                candidates.append(nb)
    if not candidates:
        return None

    new_pos = random.choice(candidates)

    # Build changeset (record old states before modification)
    changeset: dict[tuple[int, int], TileState | None] = {
        old_pos: assignments[old_pos],
        new_pos: assignments.get(new_pos),
    }

    # Move
    del assignments[old_pos]
    assignments[new_pos] = TileState.FLOWER

    # Validate new flower safety
    if not check_flower_safety(new_pos, tile_info, assignments):
        _rollback(assignments, changeset)
        return None

    # old_pos is now walkable — cascade-remove exposed neighbor flowers
    _cascade_remove_unsafe(tile_info, assignments, old_pos, changeset)

    # Check that beehouses adjacent to new_pos still have access
    # (new_pos became non-walkable, so adjacent beehouses may have lost access)
    for nb in tile_info.all_neighbors[new_pos]:
        if assignments.get(nb) == TileState.BEEHOUSE:
            access = classify_beehouse_access(nb, tile_info, assignments)
            if access is None or (no_hard and access == "hard"):
                _rollback(assignments, changeset)
                return None

    # Check connectivity (new_pos became non-walkable, old_pos became walkable)
    if not check_connectivity(tile_info, assignments, removed_walkable={new_pos}):
        _rollback(assignments, changeset)
        return None

    return changeset


def _try_add_multi_flower_cluster(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
    *,
    no_hard: bool = False,
) -> dict[tuple[int, int], TileState | None] | None:
    """Place 2-4 adjacent flowers as a group with shared shielding.

    Returns changeset on success (for rollback), or None on failure.
    """
    candidates = [
        pos
        for pos in tile_info.flower_tiles
        if assignments.get(pos, TileState.EMPTY) == TileState.EMPTY
    ]
    if not candidates:
        return None
    seed = random.choice(candidates)

    # Random walk to find 1-3 more adjacent empty flower-eligible tiles
    group = {seed}
    frontier = [seed]
    target_size = random.randint(2, 4)
    while len(group) < target_size and frontier:
        pos = random.choice(frontier)
        neighbors = [
            nb for nb in tile_info.all_neighbors[pos]
            if nb in tile_info.flower_tiles
            and nb not in group
            and assignments.get(nb, TileState.EMPTY) == TileState.EMPTY
        ]
        if not neighbors:
            frontier.remove(pos)
            continue
        nb = random.choice(neighbors)
        group.add(nb)
        frontier.append(nb)

    if len(group) < 2:
        return None

    return _try_place_flower_group(group, tile_info, assignments, no_hard=no_hard)


def _try_convert_beehouse_to_flower(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
    *,
    no_hard: bool = False,
) -> dict[tuple[int, int], TileState | None] | None:
    """Convert a beehouse adjacent to a flower into a flower, adding shield beehouses.

    Returns changeset on success (for rollback), or None on failure.
    """
    # Find beehouses on flower-eligible tiles adjacent to an existing flower
    candidates = [
        pos for pos, state in assignments.items()
        if state == TileState.BEEHOUSE
        and pos in tile_info.flower_tiles
        and any(
            assignments.get(nb) == TileState.FLOWER
            for nb in tile_info.all_neighbors[pos]
        )
    ]
    if not candidates:
        return None
    pos = random.choice(candidates)

    # Build changeset (record old states before modification)
    changeset: dict[tuple[int, int], TileState | None] = {pos: assignments.get(pos)}

    # Remove beehouse and convert to flower
    del assignments[pos]
    assignments[pos] = TileState.FLOWER

    # Find shield positions needed for the new flower
    shield_needed: list[tuple[int, int]] = []
    for nb in tile_info.all_neighbors[pos]:
        if nb in tile_info.obstacle_tiles:
            continue
        tt = tile_info.tile_type.get(nb)
        if tt is None:
            continue  # map edge
        if tt not in BEEHOUSE_TILES:
            _rollback(assignments, changeset)
            return None
        state = assignments.get(nb, TileState.EMPTY)
        if state == TileState.BEEHOUSE or state == TileState.FLOWER:
            continue
        if state != TileState.EMPTY:
            _rollback(assignments, changeset)
            return None
        shield_needed.append(nb)
        changeset[nb] = assignments.get(nb)

    # Place shield beehouses
    for sp in shield_needed:
        assignments[sp] = TileState.BEEHOUSE

    # Validate flower safety
    if not check_flower_safety(pos, tile_info, assignments):
        _rollback(assignments, changeset)
        return None

    # Validate new beehouse accessibility
    for sp in shield_needed:
        access = classify_beehouse_access(sp, tile_info, assignments)
        if access is None or (no_hard and access == "hard"):
            _rollback(assignments, changeset)
            return None

    # Check adjacent existing beehouses still accessible
    all_changed = {pos} | set(shield_needed)
    for changed in all_changed:
        for nb in tile_info.all_neighbors[changed]:
            if nb not in all_changed and assignments.get(nb) == TileState.BEEHOUSE:
                access = classify_beehouse_access(nb, tile_info, assignments)
                if access is None or (no_hard and access == "hard"):
                    _rollback(assignments, changeset)
                    return None

    # Validate connectivity (shield positions became non-walkable; pos was already occupied)
    if not check_connectivity(tile_info, assignments, removed_walkable=set(shield_needed)):
        _rollback(assignments, changeset)
        return None

    return changeset


def _try_swap_beehouse(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
    *,
    no_hard: bool = False,
) -> dict[tuple[int, int], TileState | None] | None:
    """Swap a beehouse with an adjacent empty beehouse-eligible tile.

    Only swaps beehouses that are NOT adjacent to a flower, to avoid
    exposing shielded flowers. Returns changeset on success, None on failure.
    """
    beehouses = [
        pos
        for pos, state in assignments.items()
        if state == TileState.BEEHOUSE
        and not any(
            assignments.get(nb) == TileState.FLOWER
            for nb in tile_info.all_neighbors[pos]
        )
    ]
    if not beehouses:
        return None
    bh_pos = random.choice(beehouses)

    # Find adjacent empty beehouse-eligible tiles
    candidates = [
        nb
        for nb in tile_info.all_neighbors[bh_pos]
        if is_walkable(nb, tile_info, assignments) and nb in tile_info.beehouse_tiles
    ]
    if not candidates:
        return None
    empty_pos = random.choice(candidates)

    changeset: dict[tuple[int, int], TileState | None] = {
        bh_pos: assignments[bh_pos],
        empty_pos: assignments.get(empty_pos),
    }

    # Atomic swap
    del assignments[bh_pos]
    assignments[empty_pos] = TileState.BEEHOUSE

    # Validate new beehouse has flower coverage
    if not check_flower_coverage(empty_pos, tile_info, assignments):
        _rollback(assignments, changeset)
        return None

    # Validate accessibility of new beehouse
    access = classify_beehouse_access(empty_pos, tile_info, assignments)
    if access is None or (no_hard and access == "hard"):
        _rollback(assignments, changeset)
        return None

    # Check flower safety (bh_pos became walkable, could expose adjacent flowers)
    for nb in tile_info.all_neighbors[bh_pos]:
        if assignments.get(nb) == TileState.FLOWER:
            if not check_flower_safety(nb, tile_info, assignments):
                _rollback(assignments, changeset)
                return None

    # Check adjacent beehouses still accessible
    all_changed = {bh_pos, empty_pos}
    for changed in all_changed:
        for nb in tile_info.all_neighbors[changed]:
            if nb not in all_changed and assignments.get(nb) == TileState.BEEHOUSE:
                access_nb = classify_beehouse_access(nb, tile_info, assignments)
                if access_nb is None or (no_hard and access_nb == "hard"):
                    _rollback(assignments, changeset)
                    return None

    # Check connectivity (empty_pos became non-walkable)
    if not check_connectivity(tile_info, assignments, removed_walkable={empty_pos}):
        _rollback(assignments, changeset)
        return None

    return changeset


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
    on_progress: Callable[[int, float, float, int, int], None] | None = None,
    stop_event: multiprocessing.synchronize.Event | None = None,
    *,
    no_hard: bool = False,
) -> Solution:
    """Run simulated annealing to improve the layout.

    Args:
        tile_info: Precomputed map data.
        initial_assignments: Starting layout from greedy phase.
        duration_secs: Maximum time to run in seconds.
        on_improvement: Callback when a new best solution is found.
        on_progress: Callback(iterations, elapsed, temp, bh_count, improvements).
        stop_event: If set, signals the annealing loop to stop.
        no_hard: If True, reject solutions with hard-to-access beehouses.

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
        ("add_beehouse", 0.20),
        ("remove_beehouse", 0.10),
        ("add_flower_cluster", 0.10),
        ("add_multi_flower_cluster", 0.10),
        ("convert_beehouse_to_flower", 0.10),
        ("remove_flower", 0.05),
        ("move_flower", 0.15),
        ("swap_beehouse", 0.20),
    ]
    move_names = [m[0] for m in moves]
    move_weights = [m[1] for m in moves]

    while True:
        elapsed = time.monotonic() - start_time
        if elapsed >= duration_secs:
            break
        if stop_event is not None and stop_event.is_set():
            break
        if temp < MIN_TEMP:
            temp = INITIAL_TEMP  # reheat

        # Pick a random move (each returns changeset on success, None on failure)
        move = random.choices(move_names, weights=move_weights, k=1)[0]

        changeset = None
        if move == "add_beehouse":
            changeset = _try_add_beehouse(tile_info, assignments, no_hard=no_hard)
        elif move == "remove_beehouse":
            changeset = _try_remove_beehouse(tile_info, assignments)
        elif move == "add_flower_cluster":
            changeset = _try_add_flower_cluster(tile_info, assignments, no_hard=no_hard)
        elif move == "add_multi_flower_cluster":
            changeset = _try_add_multi_flower_cluster(tile_info, assignments, no_hard=no_hard)
        elif move == "convert_beehouse_to_flower":
            changeset = _try_convert_beehouse_to_flower(tile_info, assignments, no_hard=no_hard)
        elif move == "remove_flower":
            changeset = _try_remove_flower(tile_info, assignments)
        elif move == "move_flower":
            changeset = _try_move_flower(tile_info, assignments, no_hard=no_hard)
        elif move == "swap_beehouse":
            changeset = _try_swap_beehouse(tile_info, assignments, no_hard=no_hard)

        if changeset is None:
            iterations += 1
            continue  # Don't cool on failed moves — preserves exploration budget

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
                    # Pass a copy so callback doesn't mutate SA state
                    tour_steps = optimize_tour(tile_info, best_assignments)
                    solution = score_solution(tile_info, best_assignments, tour_steps)
                    on_improvement(solution)
        else:
            # Rollback using targeted changeset instead of full dict copy
            _rollback(assignments, changeset)

        iterations += 1
        temp *= COOLING_RATE

        # Periodic progress report
        now = time.monotonic()
        if now - last_report >= REPORT_INTERVAL_SECS:
            if on_progress is not None:
                bh_count = sum(
                    1 for s in assignments.values() if s == TileState.BEEHOUSE
                )
                on_progress(iterations, elapsed, temp, bh_count, improvements)
            last_report = now

    # Final scoring with tour
    tour_steps = optimize_tour(tile_info, best_assignments)
    return score_solution(tile_info, best_assignments, tour_steps)
