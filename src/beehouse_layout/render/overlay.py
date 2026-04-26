from PIL import Image, ImageDraw

from beehouse_layout.constants import (
    TILE_ENTRANCE,
    TILE_INTERACTABLE,
    TILE_OBSTACLE,
    TILE_PATH,
    TILE_POT,
    TILE_SOIL,
    TILE_WALKWAY,
)
from beehouse_layout.render.constants import TILE_SIZE
from beehouse_layout.render.fonts import load_font

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
from beehouse_layout.map.parser import MapData

LEGEND_BAR_HEIGHT = 40
GRID_LINE_COLOR = (255, 255, 255, 60)


def render_overlay(map_data: MapData) -> Image.Image:
    height = len(map_data.grid)
    width = max(len(row) for row in map_data.grid)

    # Load font early to measure legend width before creating the image
    font = load_font(14)

    used_types: set[str] = set()
    for row in map_data.grid:
        for cell in row:
            if cell is not None:
                used_types.add(cell)

    legend_items = [
        (name.capitalize(), color)
        for name, color in TILE_COLORS.items()
        if name in used_types
    ]
    swatch_size = 16
    padding = 12
    legend_w = 0
    for label, _ in legend_items:
        label_bbox = font.getbbox(label)
        legend_w += swatch_size + 4 + (label_bbox[2] - label_bbox[0]) + padding
    if legend_items:
        legend_w -= padding

    legend_bar_h = LEGEND_BAR_HEIGHT if legend_items else 0
    content_padding = 20
    img_w = max(width * TILE_SIZE, legend_w + content_padding)
    img_h = height * TILE_SIZE + legend_bar_h

    image = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    for y, row in enumerate(map_data.grid):
        for x, tile_type in enumerate(row):
            if tile_type is None:
                continue
            color = TILE_COLORS.get(tile_type)
            if color is None:
                continue
            x0 = x * TILE_SIZE
            y0 = y * TILE_SIZE
            draw.rectangle([x0, y0, x0 + TILE_SIZE - 1, y0 + TILE_SIZE - 1], fill=color)

    # Draw grid lines
    grid_h = height * TILE_SIZE
    for x in range(width + 1):
        lx = x * TILE_SIZE
        draw.line([(lx, 0), (lx, grid_h - 1)], fill=GRID_LINE_COLOR)
    for y in range(height + 1):
        ly = y * TILE_SIZE
        draw.line([(0, ly), (img_w - 1, ly)], fill=GRID_LINE_COLOR)

    # Draw legend bar
    if legend_items:
        legend_y = height * TILE_SIZE
        draw.rectangle([0, legend_y, img_w, legend_y + LEGEND_BAR_HEIGHT], fill=(30, 30, 30, 230))

        lx = (img_w - legend_w) // 2
        ly = legend_y + (LEGEND_BAR_HEIGHT - swatch_size) // 2

        for label, color in legend_items:
            draw.rectangle([lx, ly, lx + swatch_size, ly + swatch_size], fill=color)
            lx += swatch_size + 4
            label_bbox = draw.textbbox((0, 0), label, font=font)
            label_h = label_bbox[3] - label_bbox[1]
            draw.text((lx, ly + (swatch_size - label_h) // 2), label, fill=(200, 200, 200, 255), font=font)
            lx += (label_bbox[2] - label_bbox[0]) + padding

    return image


