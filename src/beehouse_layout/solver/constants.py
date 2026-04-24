"""Constants shared across solver package modules."""

from beehouse_layout.constants import TILE_PATH, TILE_POT, TILE_SOIL

# Tiles where beehouses can be placed
BEEHOUSE_TILES = frozenset({TILE_POT, TILE_SOIL, TILE_PATH})

# Cardinal direction offsets (dx, dy)
CARDINAL_OFFSETS = ((0, -1), (0, 1), (-1, 0), (1, 0))
# All 8-direction offsets (dx, dy) for adjacency checks
ALL_OFFSETS = (
    (-1, -1), (0, -1), (1, -1),
    (-1, 0),           (1, 0),
    (-1, 1),  (0, 1),  (1, 1),
)
