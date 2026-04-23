from pathlib import Path

from PIL import Image, ImageDraw

from beehouse_layout.constants import TILE_COLORS, TILE_SIZE
from beehouse_layout.map.parser import MapData


def render_overlay(map_data: MapData) -> Image.Image:
    height = len(map_data.grid)
    width = max(len(row) for row in map_data.grid)

    image = Image.new("RGBA", (width * TILE_SIZE, height * TILE_SIZE), (0, 0, 0, 0))
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

    return image


def save_overlay(image: Image.Image, path: str) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
