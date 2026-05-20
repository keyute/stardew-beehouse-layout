"""Convert optimized layout images and text layouts."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from beehouse_layout.constants import TILE_POT, TILE_SOIL
from beehouse_layout.map.parser import MapData
from beehouse_layout.render.constants import TILE_SIZE
from beehouse_layout.render.fonts import load_font
from beehouse_layout.render.layout import (
    BEEHOUSE_SPRITE,
    CROP_IN_POT_OFFSET,
    CROP_ON_SOIL_OFFSET,
    FLOWER_SPRITE,
    _load_sprite,
    render_layout,
)
from beehouse_layout.render.text import render_text
from beehouse_layout.solver.scoring import score_solution
from beehouse_layout.solver.tile_info import TileInfo, precompute
from beehouse_layout.solver.tour import optimize_tour_metrics
from beehouse_layout.solver.types import Solution, TileState

_MIN_BAND_MATCH = 0.95
_TOP_PADDING_CANDIDATES = (0, 8, 16, TILE_SIZE)
_BEEHOUSE_VISIBLE_BAND = (0, TILE_SIZE)
_FLOWER_VISIBLE_BAND = (0, 8)


class ConversionError(ValueError):
    """Raised when a layout cannot be converted."""


def _score_assignments(tile_info: TileInfo, assignments: dict[tuple[int, int], TileState]) -> Solution:
    route = optimize_tour_metrics(tile_info, assignments)
    return score_solution(
        tile_info,
        assignments,
        route.steps,
        route_turns=route.turns,
        route_revisits=route.revisits,
    )


def _sprite_match(
    image: Image.Image,
    sprite: Image.Image,
    x0: int,
    y0: int,
    *,
    y_range: tuple[int, int] | None = None,
) -> float:
    width, height = image.size
    matches = 0
    checked = 0
    sprite_pixels = sprite.load()
    image_pixels = image.load()
    sy_start, sy_end = y_range or (0, sprite.height)

    for sy in range(sy_start, sy_end):
        iy = y0 + sy
        if iy < 0 or iy >= height:
            continue
        for sx in range(sprite.width):
            ix = x0 + sx
            if ix < 0 or ix >= width:
                continue
            pixel = sprite_pixels[sx, sy]
            if pixel[3] == 0:
                continue
            checked += 1
            if image_pixels[ix, iy] == pixel:
                matches += 1

    if checked == 0:
        return 0.0
    return matches / checked


def _detect_assignments(
    image: Image.Image,
    tile_info: TileInfo,
    top_padding: int,
) -> dict[tuple[int, int], TileState]:
    assignments: dict[tuple[int, int], TileState] = {}
    beehouse = _load_sprite(BEEHOUSE_SPRITE)
    flower = _load_sprite(FLOWER_SPRITE)

    for y, row in enumerate(tile_info.grid):
        for x, base in enumerate(row):
            if base is None:
                continue
            pos = (x, y)
            x0 = x * TILE_SIZE
            y0 = top_padding + y * TILE_SIZE

            bee_y = y0 - (beehouse.height - TILE_SIZE)
            if (
                pos in tile_info.beehouse_tiles
                and _sprite_match(
                    image,
                    beehouse,
                    x0,
                    bee_y,
                    y_range=_BEEHOUSE_VISIBLE_BAND,
                ) >= _MIN_BAND_MATCH
            ):
                assignments[pos] = TileState.BEEHOUSE
                continue

            if base == TILE_SOIL:
                flower_y = y0 + CROP_ON_SOIL_OFFSET
                if _sprite_match(
                    image,
                    flower,
                    x0,
                    flower_y,
                    y_range=_FLOWER_VISIBLE_BAND,
                ) >= _MIN_BAND_MATCH:
                    assignments[pos] = TileState.FLOWER
            elif base == TILE_POT:
                flower_y = y0 + CROP_IN_POT_OFFSET
                if _sprite_match(
                    image,
                    flower,
                    x0,
                    flower_y,
                    y_range=_FLOWER_VISIBLE_BAND,
                ) >= _MIN_BAND_MATCH:
                    assignments[pos] = TileState.FLOWER

    return assignments


def _image_difference_score(left: Image.Image, right: Image.Image) -> int:
    if left.size != right.size:
        return 10**18
    diff = ImageChops.difference(left, right)
    return sum(
        (value % 256) * count
        for value, count in enumerate(diff.convert("RGBA").histogram())
    )


def _layout_difference_score(
    left: Image.Image,
    right: Image.Image,
    width: int,
    height: int,
) -> int:
    return _image_difference_score(
        left.crop((0, 0, width, height)),
        right.crop((0, 0, width, height)),
    )


def convert_image_to_text(image_path: str, map_data: MapData) -> str:
    """Convert an optimized layout PNG back to machine-readable text."""
    image = Image.open(image_path).convert("RGBA")
    tile_info = precompute(map_data)
    grid_w = tile_info.width * TILE_SIZE
    layout_h = tile_info.height * TILE_SIZE

    if image.width < grid_w or image.height < layout_h:
        raise ConversionError("image is smaller than the map grid")

    best: tuple[int, str, Solution] | None = None
    for top_padding in _TOP_PADDING_CANDIDATES:
        layout_h = top_padding + tile_info.height * TILE_SIZE
        if layout_h > image.height:
            continue
        assignments = _detect_assignments(image, tile_info, top_padding)
        solution = _score_assignments(tile_info, assignments)
        rendered, rendered_top_padding = render_layout(tile_info, solution)
        if rendered_top_padding != top_padding:
            continue
        score = _layout_difference_score(image, rendered, grid_w, layout_h)
        text = render_text(tile_info, solution)
        if best is None or score < best[0]:
            best = (score, text, solution)
        if score == 0:
            return text

    if best is None:
        raise ConversionError("image does not look like an optimized layout for this map")
    if best[0] != 0:
        solution = best[2]
        raise ConversionError(
            "image does not exactly match an optimized layout for this map "
            f"(decoded {solution.beehouse_count} beehouses, "
            f"{solution.flower_count} flowers)"
        )
    return best[1]


def parse_layout_text(text: str) -> list[str]:
    """Parse a text layout, dropping metadata comments."""
    rows = [line.rstrip("\n") for line in text.splitlines() if not line.startswith("#")]
    while rows and rows[-1] == "":
        rows.pop()
    if not rows:
        raise ConversionError("layout text does not contain a grid")

    for row in rows:
        invalid = sorted({ch for ch in row if ch not in ".EWXIPSBFf "})
        if invalid:
            raise ConversionError(f"layout text contains unsupported character: {invalid[0]!r}")
    return rows


def read_layout_grid(path: str, map_data: MapData | None = None) -> list[str]:
    """Read a layout grid from text or PNG."""
    suffix = Path(path).suffix.lower()
    if suffix == ".png":
        if map_data is None:
            raise ConversionError("--map is required when diffing PNG inputs")
        return parse_layout_text(convert_image_to_text(path, map_data))
    return parse_layout_text(Path(path).read_text())


def render_diff_image(left: list[str], right: list[str]) -> Image.Image:
    """Render a PNG showing differences between two text layout grids."""
    if len(left) != len(right):
        raise ConversionError("layout heights differ")
    if any(len(a) != len(b) for a, b in zip(left, right)):
        raise ConversionError("layout row widths differ")

    width = max(len(row) for row in left)
    height = len(left)
    font = load_font(14)
    image = Image.new("RGBA", (width * TILE_SIZE, height * TILE_SIZE), (28, 28, 28, 255))
    draw = ImageDraw.Draw(image)

    for y, (left_row, right_row) in enumerate(zip(left, right)):
        for x, (old, new) in enumerate(zip(left_row, right_row)):
            x0 = x * TILE_SIZE
            y0 = y * TILE_SIZE
            if old == new:
                fill = (48, 56, 60, 255)
                text = old
                text_fill = (170, 178, 178, 255)
            else:
                fill = (140, 35, 35, 255)
                text = f"{old}>{new}"
                text_fill = (255, 245, 210, 255)
            draw.rectangle([x0, y0, x0 + TILE_SIZE - 1, y0 + TILE_SIZE - 1], fill=fill)
            draw.rectangle([x0, y0, x0 + TILE_SIZE - 1, y0 + TILE_SIZE - 1], outline=(95, 95, 95, 255))
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            draw.text(
                (x0 + (TILE_SIZE - tw) // 2, y0 + (TILE_SIZE - th) // 2),
                text,
                fill=text_fill,
                font=font,
            )

    return image
