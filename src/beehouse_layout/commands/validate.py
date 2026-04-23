from pathlib import Path

import click

from beehouse_layout.map.parser import parse_map
from beehouse_layout.render.overlay import render_overlay, save_overlay

_OUTPUT_DIR = "outputs"
_OVERLAY_SUFFIX = "_overlay.png"


@click.command()
@click.argument("map_file", type=click.Path(exists=True))
def validate(map_file: str) -> None:
    """Generate overlay image to verify map data."""
    map_data = parse_map(map_file)
    image = render_overlay(map_data)

    stem = Path(map_file).stem
    output_path = f"{_OUTPUT_DIR}/{stem}{_OVERLAY_SUFFIX}"
    save_overlay(image, output_path)
    click.echo(f"Overlay saved to {output_path}")
