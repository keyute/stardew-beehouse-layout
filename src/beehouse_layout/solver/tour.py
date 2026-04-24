"""Tour optimization: find shortest walk to collect all beehouses."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from beehouse_layout.solver.constants import CARDINAL_OFFSETS
from beehouse_layout.solver.tile_info import TileInfo, get_walkable_set
from beehouse_layout.solver.types import TileState


@dataclass
class TourPath:
    """Full tile-by-tile tour path with collection stop indices."""

    tiles: list[tuple[int, int]] = field(default_factory=list)
    collection_stops: list[int] = field(default_factory=list)


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


def _greedy_tour_stops(
    entrance: tuple[int, int],
    collector_to_beehouses: dict[tuple[int, int], set[tuple[int, int]]],
    all_beehouses: set[tuple[int, int]],
    walkable: set[tuple[int, int]],
    tile_info: TileInfo,
) -> list[tuple[int, int]]:
    """Run greedy nearest-neighbor to get ordered list of collection stops."""
    uncollected = set(all_beehouses)
    current = entrance
    current_dist = _bfs_distances(current, walkable, tile_info)
    stops: list[tuple[int, int]] = []

    while uncollected:
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

        stops.append(best_tile)
        uncollected -= best_collected
        current = best_tile
        current_dist = _bfs_distances(current, walkable, tile_info)

    return stops


def _tour_distance(
    stops: list[tuple[int, int]],
    entrance: tuple[int, int],
    dist_matrix: dict[tuple[int, int], dict[tuple[int, int], int]],
) -> int:
    """Compute total BFS distance for a stop ordering (entrance -> stops -> entrance)."""
    if not stops:
        return 0
    total = dist_matrix[entrance].get(stops[0], 999999)
    for i in range(len(stops) - 1):
        total += dist_matrix[stops[i]].get(stops[i + 1], 999999)
    total += dist_matrix[stops[-1]].get(entrance, 999999)
    return total


def _two_opt_improve(
    stops: list[tuple[int, int]],
    entrance: tuple[int, int],
    dist_matrix: dict[tuple[int, int], dict[tuple[int, int], int]],
) -> list[tuple[int, int]]:
    """Improve stop ordering using 2-opt edge swaps."""
    if len(stops) <= 2:
        return stops

    best = list(stops)
    best_dist = _tour_distance(best, entrance, dist_matrix)
    improved = True

    while improved:
        improved = False
        for i in range(len(best) - 1):
            for j in range(i + 1, len(best)):
                candidate = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                d = _tour_distance(candidate, entrance, dist_matrix)
                if d < best_dist:
                    best = candidate
                    best_dist = d
                    improved = True

    return best


def optimize_tour(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
) -> int:
    """Compute tour steps with 2-opt improvement."""
    walkable = get_walkable_set(tile_info, assignments)
    if not walkable:
        return 0

    collection_points = _find_collection_points(tile_info, assignments, walkable)
    if not collection_points:
        return 0

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
            if best_entrance_dist is None or len(d) > len(best_entrance_dist):
                best_entrance = e
                best_entrance_dist = d

    if best_entrance is None or best_entrance_dist is None:
        return 0

    # Get greedy tour stops
    all_beehouses = set(collection_points.keys())
    stops = _greedy_tour_stops(
        best_entrance, collector_to_beehouses, all_beehouses, walkable, tile_info,
    )
    if not stops:
        return 0

    # For small enough tours, build distance matrix and run 2-opt
    if len(stops) <= 50:
        all_points = [best_entrance] + stops
        dist_matrix: dict[tuple[int, int], dict[tuple[int, int], int]] = {}
        for p in all_points:
            if p not in dist_matrix:
                dist_matrix[p] = _bfs_distances(p, walkable, tile_info)

        stops = _two_opt_improve(stops, best_entrance, dist_matrix)
        return _tour_distance(stops, best_entrance, dist_matrix)

    # Too many stops — just return greedy distance
    return compute_tour_steps(tile_info, assignments)


def _bfs_with_parents(
    start: tuple[int, int],
    walkable: set[tuple[int, int]],
    tile_info: TileInfo,
) -> tuple[dict[tuple[int, int], int], dict[tuple[int, int], tuple[int, int] | None]]:
    """BFS returning both distances and parent pointers for path reconstruction."""
    dist: dict[tuple[int, int], int] = {start: 0}
    parent: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        d = dist[current]
        for nb in tile_info.cardinal_neighbors[current]:
            if nb in walkable and nb not in dist:
                dist[nb] = d + 1
                parent[nb] = current
                queue.append(nb)
    return dist, parent


def _reconstruct_path(
    parent: dict[tuple[int, int], tuple[int, int] | None],
    target: tuple[int, int],
) -> list[tuple[int, int]]:
    """Trace parent pointers from target back to start, return path start->target."""
    path = []
    current: tuple[int, int] | None = target
    while current is not None:
        path.append(current)
        current = parent[current]
    path.reverse()
    return path


def compute_tour_path(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
) -> TourPath:
    """Compute the greedy nearest-neighbor tour as a full tile-by-tile path.

    Returns TourPath with ordered tile positions and collection stop indices.
    Only called at render time, not during optimization.
    """
    walkable = get_walkable_set(tile_info, assignments)
    if not walkable:
        return TourPath()

    collection_points = _find_collection_points(tile_info, assignments, walkable)
    if not collection_points:
        return TourPath()

    collector_to_beehouses: dict[tuple[int, int], set[tuple[int, int]]] = {}
    for bh, collectors in collection_points.items():
        for c in collectors:
            collector_to_beehouses.setdefault(c, set()).add(bh)

    # Choose best entrance tile
    best_entrance = None
    best_entrance_dist = None
    best_entrance_parent = None
    for e in tile_info.entrance_tiles:
        if e in walkable:
            d, p = _bfs_with_parents(e, walkable, tile_info)
            if best_entrance_dist is None or len(d) > len(best_entrance_dist):
                best_entrance = e
                best_entrance_dist = d
                best_entrance_parent = p

    if best_entrance is None or best_entrance_dist is None or best_entrance_parent is None:
        return TourPath()

    uncollected = set(collection_points.keys())
    current = best_entrance
    current_dist = best_entrance_dist
    current_parent = best_entrance_parent
    full_path: list[tuple[int, int]] = [best_entrance]
    collection_stops: list[int] = []

    while uncollected:
        best_tile = None
        best_d = float("inf")
        best_collected: set[tuple[int, int]] = set()

        for tile, beehouses in collector_to_beehouses.items():
            reachable_uncollected = beehouses & uncollected
            if not reachable_uncollected:
                continue
            d = current_dist.get(tile, float("inf"))
            if d < best_d:
                best_d = d
                best_tile = tile
                best_collected = reachable_uncollected

        if best_tile is None:
            break

        # Reconstruct path segment from current to best_tile
        segment = _reconstruct_path(current_parent, best_tile)
        # Skip first element (it's the current position, already in full_path)
        full_path.extend(segment[1:])
        collection_stops.append(len(full_path) - 1)

        uncollected -= best_collected
        current = best_tile
        current_dist, current_parent = _bfs_with_parents(current, walkable, tile_info)

    # Return to entrance
    if current != best_entrance:
        segment = _reconstruct_path(current_parent, best_entrance)
        full_path.extend(segment[1:])

    return TourPath(tiles=full_path, collection_stops=collection_stops)
