# Tile types (must match map YAML legend values)
TILE_POT = "pot"
TILE_SOIL = "soil"
TILE_PATH = "path"
TILE_OBSTACLE = "obstacle"
TILE_INTERACTABLE = "interactable"
TILE_ENTRANCE = "entrance"
TILE_WALKWAY = "walkway"

# Tiles that are walkable when empty (no object placed on them)
WALKABLE_TILES = frozenset({TILE_POT, TILE_SOIL, TILE_PATH, TILE_ENTRANCE, TILE_WALKWAY})
