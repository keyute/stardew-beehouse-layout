from pathlib import Path

from click.testing import CliRunner
from PIL import Image

from beehouse_layout.cli import cli
from beehouse_layout.map.parser import MapData, parse_map
from beehouse_layout.render.convert import convert_image_to_text, parse_layout_text, render_diff_image
from beehouse_layout.render.layout import render_layout
from beehouse_layout.render.text import render_text
from beehouse_layout.solver.scoring import score_solution
from beehouse_layout.solver.tile_info import precompute
from beehouse_layout.solver.tour import optimize_tour_metrics
from beehouse_layout.solver.types import TileState


ROOT = Path(__file__).resolve().parents[1]


def _solution(tile_info, assignments):
    route = optimize_tour_metrics(tile_info, assignments)
    return score_solution(
        tile_info,
        assignments,
        route.steps,
        route_turns=route.turns,
        route_revisits=route.revisits,
    )


def _save_layout(tmp_path, map_data, assignments, name="layout.png"):
    tile_info = precompute(map_data)
    solution = _solution(tile_info, assignments)
    image, _ = render_layout(tile_info, solution)
    path = tmp_path / name
    image.save(path)
    return path, render_text(tile_info, solution)


def _write_map(tmp_path, map_data):
    char_by_type = {
        "path": ".",
        "entrance": "E",
        "walkway": "W",
        "obstacle": "X",
        "interactable": "I",
        "pot": "P",
        "soil": "S",
        None: " ",
    }
    path = tmp_path / "map.yml"
    rows = ["".join(char_by_type[cell] for cell in row) for row in map_data.grid]
    path.write_text(
        "name: Test Map\n"
        "legend:\n"
        '  ".": path\n'
        "  E: entrance\n"
        "  W: walkway\n"
        "  X: obstacle\n"
        "  I: interactable\n"
        "  P: pot\n"
        "  S: soil\n"
        "map: |-\n"
        + "\n".join(f"  {row}" for row in rows)
        + "\n"
    )
    return path


def test_convert_image_to_text_round_trips_mixed_tiles(tmp_path):
    map_data = MapData(
        name="Mixed",
        grid=[
            ["entrance", "path", "pot", "soil", "walkway", "interactable"],
            ["path", "path", "pot", "soil", "path", "obstacle"],
            ["path", "soil", "path", "pot", "path", "path"],
        ],
    )
    assignments = {
        (1, 0): TileState.BEEHOUSE,
        (2, 0): TileState.FLOWER,
        (3, 0): TileState.FLOWER,
        (0, 1): TileState.BEEHOUSE,
        (3, 2): TileState.BEEHOUSE,
    }
    image_path, expected = _save_layout(tmp_path, map_data, assignments)

    assert convert_image_to_text(str(image_path), map_data) == expected


def test_convert_image_to_text_round_trips_overlapping_dense_rows(tmp_path):
    map_data = MapData(
        name="Dense",
        grid=[
            ["entrance", "path", "path", "path", "path", "path"],
            ["path", "path", "path", "path", "path", "path"],
            ["path", "soil", "path", "pot", "path", "path"],
            ["path", "path", "path", "path", "path", "path"],
            ["path", "path", "path", "path", "path", "path"],
        ],
    )
    assignments = {
        (1, 1): TileState.BEEHOUSE,
        (2, 1): TileState.BEEHOUSE,
        (3, 1): TileState.BEEHOUSE,
        (1, 2): TileState.FLOWER,
        (2, 2): TileState.BEEHOUSE,
        (3, 2): TileState.FLOWER,
        (4, 2): TileState.BEEHOUSE,
        (1, 3): TileState.BEEHOUSE,
        (2, 3): TileState.BEEHOUSE,
        (3, 3): TileState.BEEHOUSE,
        (4, 3): TileState.BEEHOUSE,
    }
    image_path, expected = _save_layout(tmp_path, map_data, assignments)

    assert convert_image_to_text(str(image_path), map_data) == expected


def test_convert_image_to_text_round_trips_real_maps(tmp_path):
    cases = [
        ("single_flower", {(6, 6): TileState.FLOWER, (6, 5): TileState.BEEHOUSE}),
        ("sprinkler", {(7, 6): TileState.FLOWER, (6, 6): TileState.BEEHOUSE}),
        ("quality_sprinkler", {(6, 6): TileState.FLOWER, (7, 6): TileState.BEEHOUSE}),
    ]

    for map_name, assignments in cases:
        map_data = parse_map(str(ROOT / "maps" / f"{map_name}.yml"))
        image_path, expected = _save_layout(tmp_path, map_data, assignments, f"{map_name}.png")

        assert convert_image_to_text(str(image_path), map_data) == expected


def test_convert_command_writes_output(tmp_path):
    map_data = parse_map(str(ROOT / "maps" / "single_flower.yml"))
    image_path, expected = _save_layout(
        tmp_path,
        map_data,
        {(6, 6): TileState.FLOWER, (6, 5): TileState.BEEHOUSE},
    )
    map_path = _write_map(tmp_path, map_data)
    output_path = tmp_path / "layout.txt"

    result = CliRunner().invoke(
        cli,
        ["convert", str(image_path), "--map", str(map_path), "--output", str(output_path)],
    )

    assert result.exit_code == 0, result.output
    assert output_path.read_text() == expected


def test_diff_renders_changed_cells(tmp_path):
    left = parse_layout_text(
        "# Beehouses: 1\n"
        "E.B\n"
        "SFP\n"
    )
    right = parse_layout_text(
        "# Beehouses: 2\n"
        "EFB\n"
        "SfP\n"
    )

    image = render_diff_image(left, right)

    assert image.size == (3 * 48, 2 * 48)
    assert image.getpixel((1 * 48 + 4, 4)) == (140, 35, 35, 255)
    assert image.getpixel((0 * 48 + 4, 4)) == (48, 56, 60, 255)


def test_diff_command_accepts_png_and_text(tmp_path):
    map_data = parse_map(str(ROOT / "maps" / "single_flower.yml"))
    png_path, text = _save_layout(
        tmp_path,
        map_data,
        {(6, 6): TileState.FLOWER, (6, 5): TileState.BEEHOUSE},
    )
    text_path = tmp_path / "layout.txt"
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not line.startswith("#") and "B" in line:
            lines[i] = line.replace("B", ".", 1)
            break
    text_path.write_text("\n".join(lines) + "\n")
    map_path = _write_map(tmp_path, map_data)
    output_path = tmp_path / "diff.png"

    result = CliRunner().invoke(
        cli,
        [
            "diff",
            str(png_path),
            str(text_path),
            "--map",
            str(map_path),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert Image.open(output_path).size == (13 * 48, 13 * 48)


def test_diff_command_requires_map_for_png(tmp_path):
    png_path = tmp_path / "layout.png"
    Image.new("RGBA", (48, 48)).save(png_path)
    text_path = tmp_path / "layout.txt"
    text_path.write_text(".\n")

    result = CliRunner().invoke(
        cli,
        ["diff", str(png_path), str(text_path), "--output", str(tmp_path / "diff.png")],
    )

    assert result.exit_code != 0
    assert "--map is required" in result.output
