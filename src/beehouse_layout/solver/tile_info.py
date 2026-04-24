"""Precomputed spatial data for map tiles."""

from __future__ import annotations

from dataclasses import dataclass

from beehouse_layout.constants import (
    TILE_ENTRANCE,
    TILE_INTERACTABLE,
    TILE_OBSTACLE,
    TILE_POT,
    TILE_SOIL,
    WALKABLE_TILES,
)
from beehouse_layout.solver.constants import ALL_OFFSETS, BEEHOUSE_TILES, CARDINAL_OFFSETS

# Tiles where flowers can be planted (soil = cheap/direct, pot = expensive/garden pot)
FLOWER_TILES = frozenset({TILE_POT, TILE_SOIL})

# Game mechanics
FLOWER_RANGE = 5  # Manhattan distance for beehouse flower detection
from beehouse_layout.map.parser import MapData
from beehouse_layout.solver.types import TileState


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
    interactable_tiles: set[tuple[int, int]]


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
    interactable_set: set[tuple[int, int]] = set()

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
            if tt == TILE_OBSTACLE or tt == TILE_INTERACTABLE:
                obstacle_set.add(pos)
            if tt == TILE_INTERACTABLE:
                interactable_set.add(pos)

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
        interactable_tiles=interactable_set,
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
