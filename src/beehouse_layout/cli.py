import click

from beehouse_layout.commands.optimize import optimize
from beehouse_layout.commands.validate import validate


@click.group()
def cli() -> None:
    """Stardew Valley beehouse layout tool."""


cli.add_command(validate)
cli.add_command(optimize)
