import click


@click.command()
@click.argument("map_file", type=click.Path(exists=True))
def optimize(map_file: str) -> None:
    """Calculate optimal beehouse layout."""
    click.echo("Not implemented yet.")
