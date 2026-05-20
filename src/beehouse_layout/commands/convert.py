from pathlib import Path

import click

from beehouse_layout.map.parser import parse_map
from beehouse_layout.render.convert import ConversionError, convert_image_to_text


@click.command()
@click.argument("layout_png", type=click.Path(exists=True))
@click.option(
    "--map",
    "map_file",
    required=True,
    type=click.Path(exists=True),
    help="Source map YAML used to generate the optimized layout.",
)
@click.option(
    "--output",
    type=click.Path(),
    default=None,
    help="Text output path. Prints to stdout when omitted.",
)
def convert(layout_png: str, map_file: str, output: str | None) -> None:
    """Convert an optimized layout PNG to text."""
    try:
        text = convert_image_to_text(layout_png, parse_map(map_file))
    except ConversionError as exc:
        raise click.ClickException(str(exc)) from exc

    if output is None:
        click.echo(text, nl=False)
        return

    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    click.echo(f"Text layout saved to {output}")
