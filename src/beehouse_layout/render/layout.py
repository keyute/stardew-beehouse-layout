"""Render a solution layout as a PNG image with sprites and metrics."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from beehouse_layout.constants import (
    ASSET_DIR,
    BEEHOUSE_SPRITE,
    FLOOR_SPRITE,
    FLOWER_SPRITE,
    TILE_ENTRANCE,
    TILE_OBSTACLE,
    TILE_PATH,
    TILE_POT,
    TILE_SIZE,
    TILE_SOIL,
)
from beehouse_layout.solver.constraints import TileInfo
from beehouse_layout.solver.types import Solution, TileState

# Colors for base tile layer (RGBA)
TILE_COLORS: dict[str, tuple[int, int, int, int]] = {
    TILE_POT: (0, 200, 0, 100),
    TILE_SOIL: (139, 90, 43, 120),
    TILE_OBSTACLE: (200, 0, 0, 100),
    TILE_PATH: (0, 100, 200, 100),
    TILE_ENTRANCE: (255, 200, 0, 150),
}

# Metrics bar height
METRICS_BAR_HEIGHT = 60


def _load_sprite(name: str) -> Image.Image:
    path = Path(ASSET_DIR) / name
    return Image.open(path).convert("RGBA")


def render_layout(tile_info: TileInfo, solution: Solution) -> Image.Image:
    """Render the full layout with tile colors, sprites, and metrics bar."""
    width = tile_info.width
    height = tile_info.height

    img_w = width * TILE_SIZE
    img_h = height * TILE_SIZE + METRICS_BAR_HEIGHT

    image = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Load sprites
    beehouse_sprite = _load_sprite(BEEHOUSE_SPRITE)
    flower_sprite = _load_sprite(FLOWER_SPRITE)
    floor_sprite = _load_sprite(FLOOR_SPRITE)

    # Pass 1: Draw base tile colors
    for pos, tt in tile_info.tile_type.items():
        x, y = pos
        color = TILE_COLORS.get(tt)
        if color is None:
            continue
        x0 = x * TILE_SIZE
        y0 = y * TILE_SIZE
        draw.rectangle(
            [x0, y0, x0 + TILE_SIZE - 1, y0 + TILE_SIZE - 1], fill=color
        )

    # Pass 2: Draw floor under placed objects
    for pos, state in solution.assignments.items():
        if state in (TileState.BEEHOUSE, TileState.FLOWER):
            x, y = pos
            x0 = x * TILE_SIZE
            y0 = y * TILE_SIZE
            image.paste(floor_sprite, (x0, y0), floor_sprite)

    # Pass 3: Draw flowers
    for pos, state in solution.assignments.items():
        if state == TileState.FLOWER:
            x, y = pos
            x0 = x * TILE_SIZE
            y0 = y * TILE_SIZE
            image.paste(flower_sprite, (x0, y0), flower_sprite)

    # Pass 4: Draw beehouses (2-tile tall sprite, bottom aligned to tile)
    bh_w, bh_h = beehouse_sprite.size
    for pos, state in solution.assignments.items():
        if state == TileState.BEEHOUSE:
            x, y = pos
            x0 = x * TILE_SIZE
            # Offset up by the extra height (sprite is 2 tiles tall)
            y0 = y * TILE_SIZE - (bh_h - TILE_SIZE)
            image.paste(beehouse_sprite, (x0, y0), beehouse_sprite)

    # Pass 5: Draw metrics bar at bottom
    bar_y = height * TILE_SIZE
    draw.rectangle(
        [0, bar_y, img_w, bar_y + METRICS_BAR_HEIGHT],
        fill=(40, 40, 40, 230),
    )

    metrics_text = (
        f"Beehouses: {solution.beehouse_count}  |  "
        f"Flowers: {solution.flower_count} ({solution.pot_count} pots)  |  "
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
