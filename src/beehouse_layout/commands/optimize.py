import multiprocessing
import os
import queue
import random
import re
import shutil
import time
from pathlib import Path

import click

from beehouse_layout.map.parser import parse_map
from beehouse_layout.render.layout import render_layout, save_layout
from beehouse_layout.solver.annealing import anneal
from beehouse_layout.solver.scoring import score_solution
from beehouse_layout.solver.tile_info import TileInfo, precompute
from beehouse_layout.solver.tour import optimize_tour
from beehouse_layout.solver.types import Solution
from beehouse_layout.solver.validator import cleanup_assignments, validate_solution
from beehouse_layout.solver.greedy import build_greedy


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


def _validate_and_save(tile_info: TileInfo, solution: Solution, map_name: str) -> str | None:
    """Validate a solution, save if valid, return path or None."""
    violations = validate_solution(tile_info, solution.assignments)
    if violations:
        return None
    image = render_layout(tile_info, solution)
    path = _output_path(map_name, solution)
    save_layout(image, path)
    return path


def _process_improvement(
    tile_info: TileInfo,
    solution: Solution,
    best_so_far: Solution,
    map_name: str,
) -> Solution:
    """Clean up, validate, and save an improvement. Returns updated best."""
    clean_assignments = dict(solution.assignments)
    cleanup_assignments(tile_info, clean_assignments)
    tour_steps = optimize_tour(tile_info, clean_assignments)
    solution = score_solution(tile_info, clean_assignments, tour_steps)

    if solution.score <= best_so_far.score:
        return best_so_far

    path = _validate_and_save(tile_info, solution, map_name)
    if path:
        click.echo(
            f"  Improved: {solution.beehouse_count} beehouses, "
            f"{solution.flower_count} flowers "
            f"({solution.pot_count} garden pots), "
            f"{solution.tour_steps} steps -> {path}"
        )
        return solution
    return best_so_far


def _sa_worker(
    tile_info: TileInfo,
    initial_assignments: dict,
    duration_secs: float,
    seed: int,
    improvement_queue: multiprocessing.Queue,
    stop_event: multiprocessing.Event,
) -> None:
    """SA worker process. Sends improvements to the queue."""
    random.seed(seed)

    def on_improvement(solution: Solution) -> None:
        improvement_queue.put(solution)

    try:
        anneal(
            tile_info,
            initial_assignments,
            duration_secs=duration_secs,
            on_improvement=on_improvement,
            stop_event=stop_event,
        )
    except KeyboardInterrupt:
        pass


def _run_single(
    tile_info: TileInfo,
    assignments: dict,
    sa_duration: float,
    best_so_far: Solution,
    map_name: str,
) -> Solution:
    """Run SA in a single process."""

    def on_improvement(solution: Solution) -> None:
        nonlocal best_so_far
        best_so_far = _process_improvement(tile_info, solution, best_so_far, map_name)

    try:
        final = anneal(
            tile_info,
            assignments,
            duration_secs=sa_duration,
            on_improvement=on_improvement,
        )
    except KeyboardInterrupt:
        click.echo("\nStopped by user.")
        return best_so_far

    # Final cleanup attempt
    cleanup_assignments(tile_info, final.assignments)
    tour_steps = optimize_tour(tile_info, final.assignments)
    final = score_solution(tile_info, final.assignments, tour_steps)

    if final.score > best_so_far.score:
        path = _validate_and_save(tile_info, final, map_name)
        if path:
            click.echo(
                f"Final: {final.beehouse_count} beehouses, "
                f"{final.flower_count} flowers ({final.pot_count} garden pots), "
                f"{final.tour_steps} steps -> {path}"
            )
            best_so_far = final

    return best_so_far


def _run_parallel(
    tile_info: TileInfo,
    assignments: dict,
    sa_duration: float,
    best_so_far: Solution,
    map_name: str,
    workers: int,
    stagnation: int,
) -> Solution:
    """Run SA across multiple processes."""
    improvement_queue: multiprocessing.Queue = multiprocessing.Queue()
    stop_event = multiprocessing.Event()
    processes: list[multiprocessing.Process] = []

    for _ in range(workers):
        seed = random.randint(0, 2**63)
        p = multiprocessing.Process(
            target=_sa_worker,
            args=(tile_info, assignments, sa_duration, seed, improvement_queue, stop_event),
        )
        p.start()
        processes.append(p)

    click.echo(f"  Started {workers} worker processes")
    last_improvement_time = time.monotonic()

    try:
        while any(p.is_alive() for p in processes):
            try:
                solution = improvement_queue.get(timeout=1)
                new_best = _process_improvement(tile_info, solution, best_so_far, map_name)
                if new_best.score > best_so_far.score:
                    best_so_far = new_best
                    last_improvement_time = time.monotonic()
            except queue.Empty:
                pass

            if stagnation > 0:
                stagnation_elapsed = time.monotonic() - last_improvement_time
                if stagnation_elapsed >= stagnation:
                    click.echo(f"  No improvement for {stagnation}s, stopping.")
                    stop_event.set()
                    break
    except KeyboardInterrupt:
        click.echo("\nStopped by user.")
    finally:
        stop_event.set()
        for p in processes:
            p.terminate()
        for p in processes:
            p.join(timeout=5)

    return best_so_far


@click.command()
@click.argument("map_file", type=click.Path(exists=True))
@click.option(
    "--duration",
    default=0,
    type=int,
    help="Optimization duration in seconds (0 = unlimited).",
)
@click.option(
    "--workers",
    default=os.cpu_count() or 1,
    type=int,
    help="Number of parallel SA processes.",
)
@click.option(
    "--stagnation",
    default=60,
    type=int,
    help="Auto-stop after N seconds without improvement (0 = disabled).",
)
def optimize(map_file: str, duration: int, workers: int, stagnation: int) -> None:
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
            f"({greedy_solution.pot_count} garden pots), "
            f"{greedy_solution.tour_steps} steps -> {path}"
        )
    else:
        click.echo("  Greedy: invalid solution (skipped)")

    # Phase 2: Simulated annealing
    sa_duration = float(duration) if duration > 0 else float("inf")
    stop_label = []
    if duration > 0:
        stop_label.append(f"{duration}s")
    if stagnation > 0:
        stop_label.append(f"stagnation {stagnation}s")
    if workers > 1:
        stop_label.append(f"{workers} workers")
    if not stop_label and workers <= 1:
        stop_label.append("unlimited, Ctrl+C to stop")
    click.echo(f"Phase 2: Simulated annealing ({', '.join(stop_label)})...")

    if workers <= 1:
        best = _run_single(tile_info, assignments, sa_duration, greedy_solution, map_data.name)
    else:
        best = _run_parallel(
            tile_info, assignments, sa_duration, greedy_solution, map_data.name,
            workers, stagnation,
        )

    click.echo(
        f"Best: {best.beehouse_count} beehouses, "
        f"{best.flower_count} flowers ({best.pot_count} garden pots), "
        f"{best.tour_steps} steps"
    )
