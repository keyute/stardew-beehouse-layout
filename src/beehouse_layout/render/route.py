"""Render a tour route overlay on top of a layout image."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from beehouse_layout.render.constants import TILE_SIZE
from beehouse_layout.solver.tour import TourPath

# Route rendering colors (RGBA)
PATH_LINE_COLOR = (255, 80, 80, 200)
PATH_HIGHLIGHT_COLOR = (255, 100, 100, 80)
STOP_CIRCLE_COLOR = (40, 40, 40, 220)
STOP_TEXT_COLOR = (255, 255, 255, 255)
START_COLOR = (80, 200, 80, 220)

LINE_WIDTH = 3
STOP_RADIUS = 10


def _tile_center(x: int, y: int, top_padding: int) -> tuple[int, int]:
    return x * TILE_SIZE + TILE_SIZE // 2, top_padding + y * TILE_SIZE + TILE_SIZE // 2


def render_route(base_image: Image.Image, tour_path: TourPath, top_padding: int) -> Image.Image:
    """Overlay the tour route on a copy of the layout image."""
    image = base_image.copy()

    if not tour_path.tiles:
        return image

    # Draw on a transparent overlay for semi-transparent effects
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 12)
    except (OSError, AttributeError):
        font = ImageFont.load_default()

    # Highlight walked tiles
    for x, y in tour_path.tiles:
        x0 = x * TILE_SIZE
        y0 = top_padding + y * TILE_SIZE
        draw.rectangle(
            [x0, y0, x0 + TILE_SIZE, y0 + TILE_SIZE],
            fill=PATH_HIGHLIGHT_COLOR,
        )

    # Draw path lines between consecutive tiles
    centers = [_tile_center(x, y, top_padding) for x, y in tour_path.tiles]
    for i in range(len(centers) - 1):
        draw.line([centers[i], centers[i + 1]], fill=PATH_LINE_COLOR, width=LINE_WIDTH)

    # Draw start marker
    sx, sy = centers[0]
    draw.ellipse(
        [sx - STOP_RADIUS, sy - STOP_RADIUS, sx + STOP_RADIUS, sy + STOP_RADIUS],
        fill=START_COLOR,
    )
    bbox = draw.textbbox((0, 0), "S", font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((sx - tw // 2, sy - th // 2), "S", fill=STOP_TEXT_COLOR, font=font)

    # Draw numbered collection stops
    for i, stop_idx in enumerate(tour_path.collection_stops, start=1):
        cx, cy = centers[stop_idx]
        draw.ellipse(
            [cx - STOP_RADIUS, cy - STOP_RADIUS, cx + STOP_RADIUS, cy + STOP_RADIUS],
            fill=STOP_CIRCLE_COLOR,
        )
        label = str(i)
        bbox = draw.textbbox((0, 0), label, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text((cx - tw // 2, cy - th // 2), label, fill=STOP_TEXT_COLOR, font=font)

    image = Image.alpha_composite(image, overlay)
    return image
