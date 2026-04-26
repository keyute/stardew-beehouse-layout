"""Machine-readable text rendering of a solution layout."""

from pathlib import Path

from beehouse_layout.constants import (
    TILE_ENTRANCE,
    TILE_INTERACTABLE,
    TILE_OBSTACLE,
    TILE_PATH,
    TILE_POT,
    TILE_SOIL,
    TILE_WALKWAY,
)
from beehouse_layout.solver.tile_info import TileInfo
from beehouse_layout.solver.types import Solution, TileState

_TILE_CHAR: dict[str | None, str] = {
    TILE_PATH: ".",
    TILE_ENTRANCE: "E",
    TILE_WALKWAY: "W",
    TILE_OBSTACLE: "X",
    TILE_INTERACTABLE: "I",
    TILE_POT: "P",
    TILE_SOIL: "S",
    None: " ",
}


def render_text(tile_info: TileInfo, solution: Solution) -> str:
    """Render solution as a text grid with a metadata header."""
    lines: list[str] = [
        f"# Beehouses: {solution.beehouse_count}",
        f"# Flowers: {solution.flower_count} ({solution.pot_count} garden pots)",
        f"# Steps: {solution.tour_steps}",
        f"# Hard collect: {solution.obstacle_diagonal_count}",
        f"# Score: {solution.score}",
    ]

    for y in range(tile_info.height):
        row_chars: list[str] = []
        for x in range(len(tile_info.grid[y])):
            pos = (x, y)
            state = solution.assignments.get(pos, TileState.EMPTY)
            if state == TileState.BEEHOUSE:
                row_chars.append("B")
            elif state == TileState.FLOWER:
                base = tile_info.tile_type.get(pos)
                row_chars.append("f" if base == TILE_POT else "F")
            else:
                row_chars.append(_TILE_CHAR.get(tile_info.grid[y][x], " "))
        lines.append("".join(row_chars))

    return "\n".join(lines) + "\n"


def save_text(text: str, path: str) -> None:
    """Save text layout to file, creating directories as needed."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
