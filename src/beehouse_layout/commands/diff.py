import click

from beehouse_layout.map.parser import parse_map
from beehouse_layout.render.convert import ConversionError, read_layout_grid, render_diff_image
from beehouse_layout.render.utils import save_image


@click.command()
@click.argument("left", type=click.Path(exists=True))
@click.argument("right", type=click.Path(exists=True))
@click.option(
    "--output",
    required=True,
    type=click.Path(),
    help="Diff image output path.",
)
@click.option(
    "--map",
    "map_file",
    type=click.Path(exists=True),
    default=None,
    help="Source map YAML. Required when either input is a PNG.",
)
def diff(left: str, right: str, output: str, map_file: str | None) -> None:
    """Render an image showing layout differences."""
    map_data = parse_map(map_file) if map_file is not None else None
    try:
        left_grid = read_layout_grid(left, map_data)
        right_grid = read_layout_grid(right, map_data)
        image = render_diff_image(left_grid, right_grid)
    except ConversionError as exc:
        raise click.ClickException(str(exc)) from exc

    save_image(image, output)
    click.echo(f"Diff saved to {output}")
