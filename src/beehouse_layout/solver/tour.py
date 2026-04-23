"""Tour optimization: find shortest walk to collect all beehouses."""

from __future__ import annotations

from collections import deque

from beehouse_layout.constants import CARDINAL_OFFSETS
from beehouse_layout.solver.constraints import TileInfo, get_walkable_set
from beehouse_layout.solver.types import TileState


def _bfs_distances(
    start: tuple[int, int],
    walkable: set[tuple[int, int]],
    tile_info: TileInfo,
) -> dict[tuple[int, int], int]:
    """BFS shortest distances from start to all reachable walkable tiles."""
    dist: dict[tuple[int, int], int] = {start: 0}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        d = dist[current]
        for nb in tile_info.cardinal_neighbors[current]:
            if nb in walkable and nb not in dist:
                dist[nb] = d + 1
                queue.append(nb)
    return dist


def _find_collection_points(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
    walkable: set[tuple[int, int]],
) -> dict[tuple[int, int], set[tuple[int, int]]]:
    """For each beehouse, find walkable tiles the player can stand on to collect.

    Returns: mapping of beehouse_pos -> set of collection walkable tiles.
    """
    result: dict[tuple[int, int], set[tuple[int, int]]] = {}
    for pos, state in assignments.items():
        if state != TileState.BEEHOUSE:
            continue
        collectors = set()
        for nb in tile_info.all_neighbors[pos]:
            if nb in walkable:
                collectors.add(nb)
        if collectors:
            result[pos] = collectors
    return result


def compute_tour_steps(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
) -> int:
    """Compute approximate minimum steps to collect all beehouses and return to entrance.

    Uses a greedy nearest-unvisited approach on walkable tiles.
    Each tile traversed counts as one step, including backtracking.
    """
    walkable = get_walkable_set(tile_info, assignments)
    if not walkable:
        return 0

    collection_points = _find_collection_points(tile_info, assignments, walkable)
    if not collection_points:
        return 0

    # Find the set of walkable tiles that can collect at least one beehouse
    collector_to_beehouses: dict[tuple[int, int], set[tuple[int, int]]] = {}
    for bh, collectors in collection_points.items():
        for c in collectors:
            collector_to_beehouses.setdefault(c, set()).add(bh)

    # Choose best entrance tile
    best_entrance = None
    best_entrance_dist = None
    for e in tile_info.entrance_tiles:
        if e in walkable:
            d = _bfs_distances(e, walkable, tile_info)
            if best_entrance_dist is None or (
                len(d) > len(best_entrance_dist)  # type: ignore[arg-type]
            ):
                best_entrance = e
                best_entrance_dist = d

    if best_entrance is None or best_entrance_dist is None:
        return 0

    # Greedy nearest-collector tour
    uncollected = set(collection_points.keys())
    current = best_entrance
    total_steps = 0
    current_dist = best_entrance_dist

    while uncollected:
        # Find nearest walkable tile that collects at least one uncollected beehouse
        best_tile = None
        best_d = float("inf")
        best_collected: set[tuple[int, int]] = set()

        for tile, beehouses in collector_to_beehouses.items():
            reachable_uncollected = beehouses & uncollected
            if not reachable_uncollected:
                continue
            d = current_dist.get(tile, float("inf"))
            if d < best_d:  # type: ignore[operator]
                best_d = d
                best_tile = tile
                best_collected = reachable_uncollected

        if best_tile is None:
            break

        total_steps += best_d  # type: ignore[arg-type]
        uncollected -= best_collected
        current = best_tile
        current_dist = _bfs_distances(current, walkable, tile_info)

    # Return to entrance
    return_dist = current_dist.get(best_entrance, 0)
    total_steps += return_dist

    return total_steps


def optimize_tour(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
) -> int:
    """Compute tour steps with 2-opt improvement attempt."""
    # For now, the greedy tour is our best estimate
    # 2-opt would require building a full distance matrix between collection points
    # which we can add later if performance warrants it
    return compute_tour_steps(tile_info, assignments)
