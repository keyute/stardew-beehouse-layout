from pathlib import Path

import click

from beehouse_layout.map.parser import parse_map
from beehouse_layout.render.overlay import render_overlay
from beehouse_layout.render.utils import save_image
from beehouse_layout.commands.constants import OUTPUT_DIR
from beehouse_layout.solver.constraints import check_entrance_connectivity
from beehouse_layout.solver.tile_info import precompute
_OVERLAY_SUFFIX = "_overlay.png"


@click.command()
@click.argument("map_file", type=click.Path(exists=True))
def validate(map_file: str) -> None:
    """Generate overlay image to verify map data."""
    map_data = parse_map(map_file)
    image = render_overlay(map_data)

    stem = Path(map_file).stem
    output_path = f"{OUTPUT_DIR}/{stem}{_OVERLAY_SUFFIX}"
    save_image(image, output_path)
    click.echo(f"Overlay saved to {output_path}")

    # Check entrance connectivity
    tile_info = precompute(map_data)
    violations = check_entrance_connectivity(tile_info)
    if violations:
        for v in violations:
            click.echo(f"WARNING: {v}")
    else:
        click.echo("Entrance connectivity: OK")
