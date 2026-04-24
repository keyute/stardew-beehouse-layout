# Tile types (must match map YAML legend values)
TILE_POT = "pot"
TILE_SOIL = "soil"
TILE_PATH = "path"
TILE_OBSTACLE = "obstacle"
TILE_INTERACTABLE = "interactable"
TILE_ENTRANCE = "entrance"
TILE_WALKWAY = "walkway"

# Tiles where beehouses can be placed
BEEHOUSE_TILES = frozenset({TILE_POT, TILE_SOIL, TILE_PATH})
# Tiles where flowers can be planted (soil = cheap/direct, pot = expensive/garden pot)
FLOWER_TILES = frozenset({TILE_POT, TILE_SOIL})
# Tiles that are walkable when empty (no object placed on them)
WALKABLE_TILES = frozenset({TILE_POT, TILE_SOIL, TILE_PATH, TILE_ENTRANCE, TILE_WALKWAY})

# Game mechanics
FLOWER_RANGE = 5  # Manhattan distance for beehouse flower detection

# Rendering
TILE_SIZE = 48
ASSET_DIR = "assets"
BEEHOUSE_SPRITE = "bee_house.png"
FLOWER_SPRITE = "fairy_rose.png"
FLOOR_SPRITE = "wood_floor.png"
POT_SPRITE = "garden_pot.png"
STONE_SPRITE = "stone.png"
GRAVEL_PATH_SPRITE = "gravel_path.png"
CHEST_SPRITE = "chest.png"
BRICK_FLOOR_SPRITE = "brick_floor.png"
STONE_FLOOR_SPRITE = "stone_floor.png"
CRYSTAL_FLOOR_SPRITE = "crystal_floor.png"

# Floor-level sprites (1-tile, no Y-sorting needed)
FLOOR_SPRITES: dict[str, str] = {
    TILE_ENTRANCE: CRYSTAL_FLOOR_SPRITE,
    TILE_WALKWAY: BRICK_FLOOR_SPRITE,
    TILE_OBSTACLE: STONE_FLOOR_SPRITE,
    TILE_INTERACTABLE: STONE_FLOOR_SPRITE,
}
DEFAULT_FLOOR_SPRITE = FLOOR_SPRITE

# Tall sprites (bottom-aligned, Y-sorted) — map tile types and solution states
TALL_SPRITES: dict[str, str] = {
    TILE_OBSTACLE: STONE_SPRITE,
    TILE_INTERACTABLE: CHEST_SPRITE,
    "beehouse": BEEHOUSE_SPRITE,
}

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
SCORE_POT = -50
SCORE_OBSTACLE_DIAGONAL = -100

# Tile colors for rendering (RGBA)
TILE_COLORS: dict[str, tuple[int, int, int, int]] = {
    TILE_POT: (0, 200, 0, 100),
    TILE_SOIL: (139, 90, 43, 120),
    TILE_OBSTACLE: (200, 0, 0, 100),
    TILE_INTERACTABLE: (255, 130, 0, 120),
    TILE_PATH: (0, 100, 200, 100),
    TILE_ENTRANCE: (255, 200, 0, 150),
    TILE_WALKWAY: (0, 200, 200, 100),
}
