import re
import shutil
from pathlib import Path

import click

from beehouse_layout.map.parser import parse_map
from beehouse_layout.render.layout import render_layout, save_layout
from beehouse_layout.solver.annealing import anneal
from beehouse_layout.solver.constraints import (
    cleanup_assignments,
    precompute,
    score_solution,
    validate_solution,
)
from beehouse_layout.solver.greedy import build_greedy
from beehouse_layout.solver.tour import optimize_tour
from beehouse_layout.solver.types import Solution


def _slugify(name: str) -> str:
    """Convert map name to filesystem-safe slug."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _output_path(map_name: str, solution: Solution) -> str:
    slug = _slugify(map_name)
    filename = (
        f"{solution.beehouse_count}bh_"
        f"{solution.flower_count}fl_"
        f"{solution.pot_count}pt_"
        f"{solution.tour_steps}st"
    )
    base = Path("outputs") / slug / filename
    path = base.with_suffix(".png")

    # Handle duplicate names
    counter = 2
    while path.exists():
        path = base.parent / f"{filename}_{counter}.png"
        counter += 1

    return str(path)


def _validate_and_save(tile_info, solution: Solution, map_name: str) -> str | None:
    """Validate a solution, save if valid, return path or None."""
    violations = validate_solution(tile_info, solution.assignments)
    if violations:
        return None
    image = render_layout(tile_info, solution)
    path = _output_path(map_name, solution)
    save_layout(image, path)
    return path


@click.command()
@click.argument("map_file", type=click.Path(exists=True))
@click.option(
    "--duration",
    default=0,
    type=int,
    help="Optimization duration in seconds (0 = unlimited, stop with Ctrl+C).",
)
def optimize(map_file: str, duration: int) -> None:
    """Calculate optimal beehouse layout."""
    map_data = parse_map(map_file)
    click.echo(f"Map: {map_data.name}")

    # Clear previous outputs for this map
    output_dir = Path("outputs") / _slugify(map_data.name)
    if output_dir.exists():
        shutil.rmtree(output_dir)
        click.echo(f"Cleared {output_dir}/")

    tile_info = precompute(map_data)
    click.echo(
        f"Tiles: {len(tile_info.beehouse_tiles)} beehouse-eligible, "
        f"{len(tile_info.flower_tiles)} flower-eligible, "
        f"{len(tile_info.entrance_tiles)} entrances"
    )

    # Phase 1: Greedy construction
    click.echo("Phase 1: Greedy construction...")
    assignments = build_greedy(tile_info)
    cleanup_assignments(tile_info, assignments)
    tour_steps = optimize_tour(tile_info, assignments)
    greedy_solution = score_solution(tile_info, assignments, tour_steps)

    path = _validate_and_save(tile_info, greedy_solution, map_data.name)
    if path:
        click.echo(
            f"  Greedy: {greedy_solution.beehouse_count} beehouses, "
            f"{greedy_solution.flower_count} flowers "
            f"({greedy_solution.pot_count} pots), "
            f"{greedy_solution.tour_steps} steps -> {path}"
        )
    else:
        click.echo("  Greedy: invalid solution (skipped)")

    # Phase 2: Simulated annealing
    duration_label = f"{duration}s" if duration > 0 else "unlimited (Ctrl+C to stop)"
    sa_duration = float(duration) if duration > 0 else float("inf")
    click.echo(f"Phase 2: Simulated annealing ({duration_label})...")
    best_so_far = greedy_solution

    def on_improvement(solution: Solution) -> None:
        nonlocal best_so_far
        # Validate before accepting as improvement
        cleanup_assignments(tile_info, solution.assignments)
        tour_steps = optimize_tour(tile_info, solution.assignments)
        solution = score_solution(tile_info, solution.assignments, tour_steps)

        if solution.score <= best_so_far.score:
            return

        path = _validate_and_save(tile_info, solution, map_data.name)
        if path:
            best_so_far = solution
            click.echo(
                f"  Improved: {solution.beehouse_count} beehouses, "
                f"{solution.flower_count} flowers "
                f"({solution.pot_count} pots), "
                f"{solution.tour_steps} steps -> {path}"
            )

    final = anneal(
        tile_info,
        assignments,
        duration_secs=sa_duration,
        on_improvement=on_improvement,
    )

    # Final cleanup and validation
    cleanup_assignments(tile_info, final.assignments)
    tour_steps = optimize_tour(tile_info, final.assignments)
    final = score_solution(tile_info, final.assignments, tour_steps)

    if final.score > best_so_far.score:
        path = _validate_and_save(tile_info, final, map_data.name)
        if path:
            click.echo(
                f"Final: {final.beehouse_count} beehouses, "
                f"{final.flower_count} flowers ({final.pot_count} pots), "
                f"{final.tour_steps} steps -> {path}"
            )

    click.echo(
        f"Best: {best_so_far.beehouse_count} beehouses, "
        f"{best_so_far.flower_count} flowers ({best_so_far.pot_count} pots), "
        f"{best_so_far.tour_steps} steps"
    )
