from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from beehouse_layout.constants import (
    ALL_OFFSETS,
    BEEHOUSE_TILES,
    CARDINAL_OFFSETS,
    FLOWER_RANGE,
    FLOWER_TILES,
    SCORE_BEEHOUSE,
    SCORE_OBSTACLE_DIAGONAL,
    SCORE_POT,
    SCORE_STEP,
    TILE_ENTRANCE,
    TILE_OBSTACLE,
    TILE_POT,
    WALKABLE_TILES,
)
from beehouse_layout.map.parser import MapData
from beehouse_layout.solver.types import Solution, TileState


@dataclass
class TileInfo:
    """Precomputed spatial data for the map."""

    grid: list[list[str | None]]
    height: int
    width: int
    # Per-tile lookups
    tile_type: dict[tuple[int, int], str]
    cardinal_neighbors: dict[tuple[int, int], list[tuple[int, int]]]
    all_neighbors: dict[tuple[int, int], list[tuple[int, int]]]
    flower_diamond: dict[tuple[int, int], list[tuple[int, int]]]
    # Tile classification sets
    beehouse_tiles: set[tuple[int, int]]
    flower_tiles: set[tuple[int, int]]
    walkable_tiles: set[tuple[int, int]]
    entrance_tiles: set[tuple[int, int]]
    obstacle_tiles: set[tuple[int, int]]


def precompute(map_data: MapData) -> TileInfo:
    grid = map_data.grid
    height = len(grid)
    width = max(len(row) for row in grid)

    tile_type: dict[tuple[int, int], str] = {}
    cardinal_neighbors: dict[tuple[int, int], list[tuple[int, int]]] = {}
    all_neighbors: dict[tuple[int, int], list[tuple[int, int]]] = {}
    flower_diamond: dict[tuple[int, int], list[tuple[int, int]]] = {}
    beehouse_set: set[tuple[int, int]] = set()
    flower_set: set[tuple[int, int]] = set()
    walkable_set: set[tuple[int, int]] = set()
    entrance_set: set[tuple[int, int]] = set()
    obstacle_set: set[tuple[int, int]] = set()

    # First pass: classify tiles
    for y, row in enumerate(grid):
        for x, tt in enumerate(row):
            if tt is None:
                continue
            pos = (x, y)
            tile_type[pos] = tt
            if tt in BEEHOUSE_TILES:
                beehouse_set.add(pos)
            if tt in FLOWER_TILES:
                flower_set.add(pos)
            if tt in WALKABLE_TILES:
                walkable_set.add(pos)
            if tt == TILE_ENTRANCE:
                entrance_set.add(pos)
            if tt == TILE_OBSTACLE:
                obstacle_set.add(pos)

    # Second pass: precompute neighbors and flower diamonds
    for pos in tile_type:
        x, y = pos
        cardinal_neighbors[pos] = [
            (x + dx, y + dy)
            for dx, dy in CARDINAL_OFFSETS
            if (x + dx, y + dy) in tile_type
        ]
        all_neighbors[pos] = [
            (x + dx, y + dy)
            for dx, dy in ALL_OFFSETS
            if (x + dx, y + dy) in tile_type
        ]
        # Manhattan distance <= FLOWER_RANGE diamond
        diamond = []
        for dy in range(-FLOWER_RANGE, FLOWER_RANGE + 1):
            max_dx = FLOWER_RANGE - abs(dy)
            for dx in range(-max_dx, max_dx + 1):
                if dx == 0 and dy == 0:
                    continue
                nb = (x + dx, y + dy)
                if nb in tile_type:
                    diamond.append(nb)
        flower_diamond[pos] = diamond

    return TileInfo(
        grid=grid,
        height=height,
        width=width,
        tile_type=tile_type,
        cardinal_neighbors=cardinal_neighbors,
        all_neighbors=all_neighbors,
        flower_diamond=flower_diamond,
        beehouse_tiles=beehouse_set,
        flower_tiles=flower_set,
        walkable_tiles=walkable_set,
        entrance_tiles=entrance_set,
        obstacle_tiles=obstacle_set,
    )


def is_walkable(
    pos: tuple[int, int],
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
) -> bool:
    """A tile is walkable if its base type is walkable AND no object is placed on it."""
    tt = tile_info.tile_type.get(pos)
    if tt is None or tt not in WALKABLE_TILES:
        return False
    state = assignments.get(pos, TileState.EMPTY)
    return state == TileState.EMPTY


def get_walkable_set(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
) -> set[tuple[int, int]]:
    """Return all currently walkable tiles."""
    return {
        pos
        for pos in tile_info.walkable_tiles
        if assignments.get(pos, TileState.EMPTY) == TileState.EMPTY
    }


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
    """Check that a flower at `pos` has no cardinally adjacent walkable tile."""
    for nb in tile_info.cardinal_neighbors[pos]:
        if is_walkable(nb, tile_info, assignments):
            return False
    return True


def classify_beehouse_access(
    pos: tuple[int, int],
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
) -> str | None:
    """Classify beehouse accessibility. Returns 'easy', 'ok', 'hard', or None (inaccessible)."""
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

        # Diagonal adjacency: check if walkable tile has cardinally adjacent obstacle
        nb_has_obstacle = any(
            tile_info.tile_type.get(cn) == TILE_OBSTACLE
            for cn in tile_info.cardinal_neighbors.get(nb, [])
        )
        if nb_has_obstacle:
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
) -> bool:
    """Check all beehouses are reachable from an entrance via connected walkable tiles.

    We don't require ALL walkable tiles to be connected — only that every beehouse
    has at least one adjacent walkable tile reachable from an entrance.
    """
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



def cleanup_assignments(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
) -> None:
    """Remove invalid beehouses and flowers until all constraints are satisfied."""
    changed = True
    while changed:
        changed = False
        # Remove inaccessible beehouses
        for pos in [
            p for p, s in assignments.items()
            if s == TileState.BEEHOUSE and classify_beehouse_access(p, tile_info, assignments) is None
        ]:
            del assignments[pos]
            changed = True
        # Remove unsafe flowers
        for pos in [
            p for p, s in assignments.items()
            if s == TileState.FLOWER and not check_flower_safety(p, tile_info, assignments)
        ]:
            del assignments[pos]
            changed = True
        # Remove uncovered beehouses
        for pos in [
            p for p, s in assignments.items()
            if s == TileState.BEEHOUSE and not check_flower_coverage(p, tile_info, assignments)
        ]:
            del assignments[pos]
            changed = True


def validate_solution(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
) -> list[str]:
    """Validate all constraints. Returns list of violation descriptions."""
    violations: list[str] = []

    for pos, state in assignments.items():
        if state == TileState.BEEHOUSE:
            # Must be on a valid tile
            if pos not in tile_info.beehouse_tiles:
                violations.append(f"Beehouse at {pos} on invalid tile")
            # Must have flower in range
            if not check_flower_coverage(pos, tile_info, assignments):
                violations.append(f"Beehouse at {pos} has no flower in range")
            # Must be accessible
            access = classify_beehouse_access(pos, tile_info, assignments)
            if access is None:
                violations.append(f"Beehouse at {pos} is inaccessible")

        elif state == TileState.FLOWER:
            # Must be on a valid tile
            if pos not in tile_info.flower_tiles:
                violations.append(f"Flower at {pos} on invalid tile")
            # Must not have cardinally adjacent walkable tile
            if not check_flower_safety(pos, tile_info, assignments):
                violations.append(f"Flower at {pos} has adjacent walkable tile")

    # Connectivity
    if not check_connectivity(tile_info, assignments):
        violations.append("Walkable tiles are not fully connected")

    return violations


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
