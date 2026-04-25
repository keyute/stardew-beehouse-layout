"""Render a solution layout as a PNG image with sprites and metrics."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from beehouse_layout.constants import (
    TILE_ENTRANCE,
    TILE_INTERACTABLE,
    TILE_OBSTACLE,
    TILE_POT,
    TILE_SOIL,
    TILE_WALKWAY,
    WALKABLE_TILES,
)
from beehouse_layout.render.constants import TILE_SIZE
from beehouse_layout.render.fonts import load_font
from beehouse_layout.solver.tile_info import TileInfo
from beehouse_layout.solver.types import Solution, TileState

# Sprite asset paths
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
    TILE_OBSTACLE: FLOOR_SPRITE,
    TILE_INTERACTABLE: FLOOR_SPRITE,
}
DEFAULT_FLOOR_SPRITE = STONE_FLOOR_SPRITE

# Tall sprites (bottom-aligned, Y-sorted) — map tile types and solution states
TALL_SPRITES: dict[str, str] = {
    TILE_OBSTACLE: STONE_SPRITE,
    TILE_INTERACTABLE: CHEST_SPRITE,
    "beehouse": BEEHOUSE_SPRITE,
}

# Rendering offsets for garden pot flowers
POT_Y_OFFSET = -15  # pot sprite extends 15px above tile (63 - 48)
CROP_IN_POT_OFFSET = -16  # flower shifts up 16px when growing from pot
CROP_ON_SOIL_OFFSET = -8  # flower shifts up so beehouse doesn't fully cover it

# Metrics bar height
METRICS_BAR_HEIGHT = 60

# Legend bar
LEGEND_BAR_HEIGHT = 40
LEGEND_THUMB_SIZE = 20
LEGEND_ITEMS: list[tuple[str, str]] = [
    ("Beehouse", BEEHOUSE_SPRITE),
    ("Fairy Rose", FLOWER_SPRITE),
    ("Garden Pot", POT_SPRITE),
    ("Obstacle", STONE_SPRITE),
    ("Interactable", CHEST_SPRITE),
    ("Entrance", CRYSTAL_FLOOR_SPRITE),
    ("Walkway", BRICK_FLOOR_SPRITE),
]


def _load_sprite(name: str) -> Image.Image:
    path = Path(ASSET_DIR) / name
    return Image.open(path).convert("RGBA")


def _compute_top_padding(
    tile_info: TileInfo,
    solution: Solution,
    pot_sprite: Image.Image,
    tall_sprite_cache: dict[str, Image.Image],
) -> int:
    """Calculate the minimum top padding needed for sprites that extend above row 0."""
    top_padding = 0

    for pos, tt in tile_info.tile_type.items():
        if pos[1] != 0:
            continue
        sprite_name = TALL_SPRITES.get(tt)
        if sprite_name:
            sprite = tall_sprite_cache[sprite_name]
            top_padding = max(top_padding, sprite.size[1] - TILE_SIZE)

    for pos, state in solution.assignments.items():
        if pos[1] != 0:
            continue
        if state == TileState.FLOWER:
            if tile_info.tile_type.get(pos) == TILE_POT:
                top_padding = max(
                    top_padding,
                    pot_sprite.size[1] - TILE_SIZE,
                    abs(CROP_IN_POT_OFFSET),
                )
            elif tile_info.tile_type.get(pos) == TILE_SOIL:
                top_padding = max(top_padding, abs(CROP_ON_SOIL_OFFSET))
        sprite_name = TALL_SPRITES.get(state.value)
        if sprite_name:
            sprite = tall_sprite_cache[sprite_name]
            top_padding = max(top_padding, sprite.size[1] - TILE_SIZE)

    return top_padding


def render_layout(tile_info: TileInfo, solution: Solution) -> tuple[Image.Image, int]:
    """Render the full layout with tile colors, sprites, and metrics bar.

    Returns the rendered image and the top padding used.
    """
    width = tile_info.width
    height = tile_info.height

    # Load fonts early so we can measure text before creating the image
    font = load_font(20)
    legend_font = load_font(14)

    # Pre-calculate metrics text width
    metrics_text = (
        f"Beehouses: {solution.beehouse_count}  |  "
        f"Flowers: {solution.flower_count} ({solution.pot_count} garden pots)  |  "
        f"Steps: {solution.tour_steps}  |  "
        f"Hard collect: {solution.obstacle_diagonal_count}"
    )
    metrics_bbox = font.getbbox(metrics_text)
    metrics_w = metrics_bbox[2] - metrics_bbox[0]

    # Pre-calculate legend width
    legend_padding = 12
    legend_w = 0
    for label, _ in LEGEND_ITEMS:
        label_bbox = legend_font.getbbox(label)
        legend_w += LEGEND_THUMB_SIZE + 4 + (label_bbox[2] - label_bbox[0]) + legend_padding
    legend_w -= legend_padding

    # Load sprites
    flower_sprite = _load_sprite(FLOWER_SPRITE)
    pot_sprite = _load_sprite(POT_SPRITE)
    gravel_path_sprite = _load_sprite(GRAVEL_PATH_SPRITE)
    default_floor = _load_sprite(DEFAULT_FLOOR_SPRITE)
    floor_sprite_cache = {name: _load_sprite(name) for name in FLOOR_SPRITES.values()}
    tall_sprite_cache = {name: _load_sprite(name) for name in TALL_SPRITES.values()}

    # Compute dynamic top padding based on actual sprite overflow
    top_padding = _compute_top_padding(tile_info, solution, pot_sprite, tall_sprite_cache)

    # Ensure image is wide enough for grid and metrics
    content_padding = 20
    img_w = max(width * TILE_SIZE, metrics_w + content_padding, legend_w + content_padding)
    img_h = top_padding + height * TILE_SIZE + METRICS_BAR_HEIGHT + LEGEND_BAR_HEIGHT

    image = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Pass 1: Floor textures (data-driven)
    for pos, tt in tile_info.tile_type.items():
        x, y = pos
        x0 = x * TILE_SIZE
        y0 = top_padding + y * TILE_SIZE
        floor_name = FLOOR_SPRITES.get(tt)
        if floor_name:
            sprite = floor_sprite_cache[floor_name]
            image.paste(sprite, (x0, y0), sprite)
        elif tt in WALKABLE_TILES:
            image.paste(default_floor, (x0, y0), default_floor)

    # Pass 2: Gravel path under ground-planted flowers
    for pos, state in solution.assignments.items():
        if state == TileState.FLOWER and tile_info.tile_type.get(pos) == TILE_SOIL:
            x, y = pos
            x0 = x * TILE_SIZE
            y0 = top_padding + y * TILE_SIZE
            image.paste(gravel_path_sprite, (x0, y0), gravel_path_sprite)

    # Pass 3: All Y-sorted objects (flowers, pots, beehouses, obstacles, chests)
    render_ops: list[tuple[int, list[tuple[Image.Image, int, int]]]] = []

    for pos, state in solution.assignments.items():
        if state == TileState.FLOWER:
            x, y = pos
            x0 = x * TILE_SIZE
            y0 = top_padding + y * TILE_SIZE
            if tile_info.tile_type.get(pos) == TILE_POT:
                render_ops.append((y, [
                    (pot_sprite, x0, y0 + POT_Y_OFFSET),
                    (flower_sprite, x0, y0 + CROP_IN_POT_OFFSET),
                ]))
            else:
                render_ops.append((y, [(flower_sprite, x0, y0 + CROP_ON_SOIL_OFFSET)]))

    for pos, tt in tile_info.tile_type.items():
        sprite_name = TALL_SPRITES.get(tt)
        if sprite_name:
            x, y = pos
            sprite = tall_sprite_cache[sprite_name]
            x0 = x * TILE_SIZE
            y0 = top_padding + y * TILE_SIZE - (sprite.size[1] - TILE_SIZE)
            render_ops.append((y, [(sprite, x0, y0)]))

    for pos, state in solution.assignments.items():
        sprite_name = TALL_SPRITES.get(state.value)
        if sprite_name:
            x, y = pos
            sprite = tall_sprite_cache[sprite_name]
            x0 = x * TILE_SIZE
            y0 = top_padding + y * TILE_SIZE - (sprite.size[1] - TILE_SIZE)
            render_ops.append((y, [(sprite, x0, y0)]))

    render_ops.sort(key=lambda op: op[0])
    for _, draw_calls in render_ops:
        for sprite, px, py in draw_calls:
            image.paste(sprite, (px, py), sprite)

    # Pass 4: Draw metrics bar at bottom
    bar_y = top_padding + height * TILE_SIZE
    draw.rectangle(
        [0, bar_y, img_w, bar_y + METRICS_BAR_HEIGHT],
        fill=(40, 40, 40, 230),
    )

    bbox = draw.textbbox((0, 0), metrics_text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    text_x = (img_w - text_w) // 2
    text_y = bar_y + (METRICS_BAR_HEIGHT - text_h) // 2

    draw.text((text_x, text_y), metrics_text, fill=(255, 255, 255, 255), font=font)

    # Pass 5: Draw legend bar below metrics
    legend_y = bar_y + METRICS_BAR_HEIGHT
    draw.rectangle(
        [0, legend_y, img_w, legend_y + LEGEND_BAR_HEIGHT],
        fill=(40, 40, 40, 230),
    )

    lx = (img_w - legend_w) // 2
    ly_center = legend_y + (LEGEND_BAR_HEIGHT - LEGEND_THUMB_SIZE) // 2

    for label, sprite_name in LEGEND_ITEMS:
        thumb = _load_sprite(sprite_name).resize(
            (LEGEND_THUMB_SIZE, LEGEND_THUMB_SIZE), Image.LANCZOS
        )
        image.paste(thumb, (lx, ly_center), thumb)
        lx += LEGEND_THUMB_SIZE + 4
        label_bbox = draw.textbbox((0, 0), label, font=legend_font)
        label_h = label_bbox[3] - label_bbox[1]
        draw.text(
            (lx, ly_center + (LEGEND_THUMB_SIZE - label_h) // 2),
            label,
            fill=(200, 200, 200, 255),
            font=legend_font,
        )
        lx += (label_bbox[2] - label_bbox[0]) + legend_padding

    return image, top_padding


def save_layout(image: Image.Image, path: str) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
