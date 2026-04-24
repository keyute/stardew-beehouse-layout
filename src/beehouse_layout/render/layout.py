"""Render a solution layout as a PNG image with sprites and metrics."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from beehouse_layout.constants import (
    ASSET_DIR,
    DEFAULT_FLOOR_SPRITE,
    FLOOR_SPRITES,
    FLOWER_SPRITE,
    GRAVEL_PATH_SPRITE,
    POT_SPRITE,
    TALL_SPRITES,
    TILE_POT,
    TILE_SIZE,
    TILE_SOIL,
    WALKABLE_TILES,
)
from beehouse_layout.solver.tile_info import TileInfo
from beehouse_layout.solver.types import Solution, TileState

# Metrics bar height
METRICS_BAR_HEIGHT = 60
# Extra vertical space for tall sprites (beehouses) at the top row
TOP_PADDING = TILE_SIZE


def _load_sprite(name: str) -> Image.Image:
    path = Path(ASSET_DIR) / name
    return Image.open(path).convert("RGBA")


def render_layout(tile_info: TileInfo, solution: Solution) -> Image.Image:
    """Render the full layout with tile colors, sprites, and metrics bar."""
    width = tile_info.width
    height = tile_info.height

    # Load fonts early so we can measure text before creating the image
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
    except (OSError, AttributeError):
        font = ImageFont.load_default()

    # Pre-calculate metrics text width
    metrics_text = (
        f"Beehouses: {solution.beehouse_count}  |  "
        f"Flowers: {solution.flower_count} ({solution.pot_count} garden pots)  |  "
        f"Steps: {solution.tour_steps}  |  "
        f"Hard collect: {solution.obstacle_diagonal_count}"
    )
    metrics_bbox = font.getbbox(metrics_text)
    metrics_w = metrics_bbox[2] - metrics_bbox[0]

    # Ensure image is wide enough for grid and metrics
    content_padding = 20
    img_w = max(width * TILE_SIZE, metrics_w + content_padding)
    img_h = TOP_PADDING + height * TILE_SIZE + METRICS_BAR_HEIGHT

    image = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Load sprites
    flower_sprite = _load_sprite(FLOWER_SPRITE)
    pot_sprite = _load_sprite(POT_SPRITE)
    gravel_path_sprite = _load_sprite(GRAVEL_PATH_SPRITE)
    default_floor = _load_sprite(DEFAULT_FLOOR_SPRITE)
    floor_sprite_cache = {name: _load_sprite(name) for name in FLOOR_SPRITES.values()}
    tall_sprite_cache = {name: _load_sprite(name) for name in TALL_SPRITES.values()}

    # Pass 1: Floor textures (data-driven)
    for pos, tt in tile_info.tile_type.items():
        x, y = pos
        x0 = x * TILE_SIZE
        y0 = TOP_PADDING + y * TILE_SIZE
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
            y0 = TOP_PADDING + y * TILE_SIZE
            image.paste(gravel_path_sprite, (x0, y0), gravel_path_sprite)

    # Pass 3: Flowers and pots (Y-sorted for correct overlap)
    pot_y_offset = -(pot_sprite.size[1] - TILE_SIZE)  # -15, bottom-aligned
    crop_in_pot_offset = -16  # flower shifts up when growing from pot

    flower_positions = sorted(
        (pos for pos, state in solution.assignments.items() if state == TileState.FLOWER),
        key=lambda p: p[1],
    )
    for pos in flower_positions:
        x, y = pos
        x0 = x * TILE_SIZE
        y0 = TOP_PADDING + y * TILE_SIZE
        if tile_info.tile_type.get(pos) == TILE_POT:
            image.paste(pot_sprite, (x0, y0 + pot_y_offset), pot_sprite)
            image.paste(flower_sprite, (x0, y0 + crop_in_pot_offset), flower_sprite)
        else:
            image.paste(flower_sprite, (x0, y0), flower_sprite)

    # Pass 4: Tall objects (unified Y-sorted pass for map tiles and solution objects)
    tall_objects: list[tuple[int, int, Image.Image]] = []

    for pos, tt in tile_info.tile_type.items():
        sprite_name = TALL_SPRITES.get(tt)
        if sprite_name:
            tall_objects.append((pos[0], pos[1], tall_sprite_cache[sprite_name]))

    for pos, state in solution.assignments.items():
        sprite_name = TALL_SPRITES.get(state.value)
        if sprite_name:
            tall_objects.append((pos[0], pos[1], tall_sprite_cache[sprite_name]))

    tall_objects.sort(key=lambda o: o[1])
    for x, y, sprite in tall_objects:
        x0 = x * TILE_SIZE
        y0 = TOP_PADDING + y * TILE_SIZE - (sprite.size[1] - TILE_SIZE)
        image.paste(sprite, (x0, y0), sprite)

    # Pass 5: Draw metrics bar at bottom
    bar_y = TOP_PADDING + height * TILE_SIZE
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

    return image


def save_layout(image: Image.Image, path: str) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
