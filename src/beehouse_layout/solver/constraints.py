"""Individual constraint checking functions."""

from __future__ import annotations

from collections import deque

from beehouse_layout.constants import WALKABLE_TILES
from beehouse_layout.solver.constants import ALL_OFFSETS, CARDINAL_OFFSETS
from beehouse_layout.solver.tile_info import TileInfo, get_walkable_set, is_walkable
from beehouse_layout.solver.types import TileState


def check_flower_coverage(
    pos: tuple[int, int],
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
) -> bool:
    """Check if a beehouse at `pos` has at least one flower in range."""
    for nb in tile_info.flower_diamond[pos]:
        if assignments.get(nb) == TileState.FLOWER:
            return True
    return False


def check_flower_safety(
    pos: tuple[int, int],
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
) -> bool:
    """Check that a flower at `pos` has no adjacent walkable tile (all 8 directions)."""
    for nb in tile_info.all_neighbors[pos]:
        if is_walkable(nb, tile_info, assignments):
            return False
    return True


def classify_beehouse_access(
    pos: tuple[int, int],
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
) -> str | None:
    """Classify beehouse accessibility. Returns 'easy', 'ok', 'hard', or None (inaccessible).

    'hard' only applies when a diagonal-only walkable neighbor has an adjacent
    interactable obstacle (chests, machines) — non-interactable obstacles (rocks,
    walls) are not penalized.
    """
    x, y = pos
    has_ok = False
    has_hard = False

    for dx, dy in ALL_OFFSETS:
        nb = (x + dx, y + dy)
        if not is_walkable(nb, tile_info, assignments):
            continue

        # Cardinal adjacency = easy
        if dx == 0 or dy == 0:
            return "easy"

        # Diagonal adjacency: check if the two "squeeze" tiles (cardinally adjacent
        # to both beehouse and player) are interactable obstacles
        squeeze1 = (x + dx, y)
        squeeze2 = (x, y + dy)
        nb_has_interactable = (
            squeeze1 in tile_info.interactable_tiles
            or squeeze2 in tile_info.interactable_tiles
        )
        if nb_has_interactable:
            has_hard = True
        else:
            has_ok = True

    if has_ok:
        return "ok"
    if has_hard:
        return "hard"
    return None


def check_connectivity(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
    *,
    removed_walkable: set[tuple[int, int]] | None = None,
) -> bool:
    """Check all beehouses are reachable from an entrance via connected walkable tiles.

    We don't require ALL walkable tiles to be connected — only that every beehouse
    has at least one adjacent walkable tile reachable from an entrance.
    All entrance tiles must also be reachable.

    If removed_walkable is provided (tiles that just became non-walkable), a fast
    heuristic is tried first: if every removed tile had at most 1 cardinal walkable
    neighbor, or a bounded local BFS confirms its neighbors are still connected,
    the full BFS is skipped.
    """
    if removed_walkable is not None:
        result = _check_connectivity_fast(tile_info, assignments, removed_walkable)
        if result is not None:
            return result

    return _check_connectivity_full(tile_info, assignments)


def _check_connectivity_fast(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
    removed_walkable: set[tuple[int, int]],
) -> bool | None:
    """Fast connectivity heuristic after tiles became non-walkable.

    Returns True if connectivity is confirmed, None if inconclusive (need full BFS).
    Assumes connectivity was established before the change.

    Collects all walkable cardinal neighbors of the entire removed set, then checks
    if they're all still connected. This correctly handles multi-tile removals where
    individual tiles look like leaves but collectively form a bridge.
    """
    if not removed_walkable:
        return True  # No tiles became non-walkable — can't disconnect

    # Collect all walkable cardinal neighbors of the removed set
    exterior_neighbors: set[tuple[int, int]] = set()
    for pos in removed_walkable:
        for nb in tile_info.cardinal_neighbors[pos]:
            if is_walkable(nb, tile_info, assignments):
                exterior_neighbors.add(nb)

    if len(exterior_neighbors) <= 1:
        return True  # 0-1 exterior neighbors — can't disconnect

    # Check all exterior neighbors are still connected via bounded local BFS
    start = next(iter(exterior_neighbors))
    targets = exterior_neighbors - {start}
    visited = {start}
    queue = deque([start])
    steps = 0

    while queue and targets and steps < 50:
        current = queue.popleft()
        steps += 1
        for nb in tile_info.cardinal_neighbors[current]:
            if nb not in visited and is_walkable(nb, tile_info, assignments):
                visited.add(nb)
                queue.append(nb)
                targets.discard(nb)

    if targets:
        return None  # Inconclusive — fall back to full BFS

    return True


def _check_connectivity_full(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
) -> bool:
    """Full BFS connectivity check."""
    walkable = get_walkable_set(tile_info, assignments)
    if not walkable:
        # No walkable tiles: OK only if no beehouses exist
        return not any(s == TileState.BEEHOUSE for s in assignments.values())

    # Start BFS from any entrance tile
    start = None
    for e in tile_info.entrance_tiles:
        if e in walkable:
            start = e
            break
    if start is None:
        return False

    visited: set[tuple[int, int]] = set()
    queue = deque([start])
    visited.add(start)
    while queue:
        current = queue.popleft()
        for nb in tile_info.cardinal_neighbors[current]:
            if nb in walkable and nb not in visited:
                visited.add(nb)
                queue.append(nb)

    # Check all entrance tiles are reachable
    for e in tile_info.entrance_tiles:
        if e in walkable and e not in visited:
            return False

    # Check every beehouse has at least one adjacent walkable tile in visited set
    for pos, state in assignments.items():
        if state != TileState.BEEHOUSE:
            continue
        has_reachable = False
        for nb in tile_info.all_neighbors[pos]:
            if nb in visited:
                has_reachable = True
                break
        if not has_reachable:
            return False

    return True


def check_entrance_connectivity(tile_info: TileInfo) -> list[str]:
    """Check that every entrance has at least one cardinal neighbor that is walkable.

    This is a static map validation check (independent of assignments).
    Returns a list of violation descriptions (empty = OK).
    """
    violations: list[str] = []
    for pos in tile_info.entrance_tiles:
        has_connectable = any(
            tile_info.tile_type.get(nb) in WALKABLE_TILES
            for nb in tile_info.cardinal_neighbors[pos]
        )
        if not has_connectable:
            violations.append(
                f"Entrance at {pos} has no adjacent walkable tile"
            )
    return violations
