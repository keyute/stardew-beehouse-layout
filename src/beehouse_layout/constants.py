# Tile types (must match map YAML legend values)
TILE_POT = "pot"
TILE_SOIL = "soil"
TILE_PATH = "path"
TILE_OBSTACLE = "obstacle"
TILE_ENTRANCE = "entrance"

# Tiles where beehouses can be placed
BEEHOUSE_TILES = frozenset({TILE_POT, TILE_SOIL, TILE_PATH})
# Tiles where flowers can be planted (soil = cheap/direct, pot = expensive/garden pot)
FLOWER_TILES = frozenset({TILE_POT, TILE_SOIL})
# Tiles that are walkable when empty (no object placed on them)
WALKABLE_TILES = frozenset({TILE_POT, TILE_SOIL, TILE_PATH, TILE_ENTRANCE})

# Game mechanics
FLOWER_RANGE = 5  # Manhattan distance for beehouse flower detection

# Rendering
TILE_SIZE = 48
ASSET_DIR = "assets"
BEEHOUSE_SPRITE = "bee_house.png"
FLOWER_SPRITE = "fairy_rose.png"
FLOOR_SPRITE = "wood_floor.png"

# Cardinal direction offsets (dx, dy)
CARDINAL_OFFSETS = ((0, -1), (0, 1), (-1, 0), (1, 0))
# All 8-direction offsets (dx, dy) for adjacency checks
ALL_OFFSETS = (
    (-1, -1), (0, -1), (1, -1),
    (-1, 0),           (1, 0),
    (-1, 1),  (0, 1),  (1, 1),
)

# Scoring weights (lexicographic: beehouse >> steps >> pots >> obstacle penalty)
SCORE_BEEHOUSE = 10000
SCORE_STEP = -1
SCORE_POT = -100
SCORE_OBSTACLE_DIAGONAL = -50
