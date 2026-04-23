"""Render a solution layout as a PNG image with sprites and metrics."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from beehouse_layout.constants import (
    ASSET_DIR,
    BEEHOUSE_SPRITE,
    FLOOR_SPRITE,
    FLOWER_SPRITE,
    GRAVEL_PATH_SPRITE,
    POT_SPRITE,
    STONE_SPRITE,
    TILE_OBSTACLE,
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

    img_w = width * TILE_SIZE
    img_h = TOP_PADDING + height * TILE_SIZE + METRICS_BAR_HEIGHT

    image = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Load sprites
    beehouse_sprite = _load_sprite(BEEHOUSE_SPRITE)
    flower_sprite = _load_sprite(FLOWER_SPRITE)
    floor_sprite = _load_sprite(FLOOR_SPRITE)
    pot_sprite = _load_sprite(POT_SPRITE)
    stone_sprite = _load_sprite(STONE_SPRITE)
    gravel_path_sprite = _load_sprite(GRAVEL_PATH_SPRITE)

    # Pass 1: Base textures (wood floor on walkable, stone on obstacles)
    for pos, tt in tile_info.tile_type.items():
        x, y = pos
        x0 = x * TILE_SIZE
        y0 = TOP_PADDING + y * TILE_SIZE
        if tt == TILE_OBSTACLE:
            image.paste(stone_sprite, (x0, y0), stone_sprite)
        elif tt in WALKABLE_TILES:
            image.paste(floor_sprite, (x0, y0), floor_sprite)

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

    # Pass 4: Beehouses (Y-sorted for correct overlap of 2-tile tall sprites)
    bh_y_offset = -(beehouse_sprite.size[1] - TILE_SIZE)

    beehouse_positions = sorted(
        (pos for pos, state in solution.assignments.items() if state == TileState.BEEHOUSE),
        key=lambda p: p[1],
    )
    for pos in beehouse_positions:
        x, y = pos
        x0 = x * TILE_SIZE
        y0 = TOP_PADDING + y * TILE_SIZE + bh_y_offset
        image.paste(beehouse_sprite, (x0, y0), beehouse_sprite)

    # Pass 5: Draw metrics bar at bottom
    bar_y = TOP_PADDING + height * TILE_SIZE
    draw.rectangle(
        [0, bar_y, img_w, bar_y + METRICS_BAR_HEIGHT],
        fill=(40, 40, 40, 230),
    )

    metrics_text = (
        f"Beehouses: {solution.beehouse_count}  |  "
        f"Flowers: {solution.flower_count} ({solution.pot_count} garden pots)  |  "
        f"Steps: {solution.tour_steps}  |  "
        f"Hard collect: {solution.obstacle_diagonal_count}"
    )

    # Try to use a reasonable font size
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
    except (OSError, AttributeError):
        font = ImageFont.load_default()

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
