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
from beehouse_layout.render.dashboard import Dashboard
from beehouse_layout.render.layout import render_layout, save_layout
from beehouse_layout.render.route import render_route
from beehouse_layout.solver.annealing import anneal
from beehouse_layout.solver.scoring import score_solution
from beehouse_layout.solver.tile_info import TileInfo, precompute
from beehouse_layout.solver.tour import compute_tour_path, optimize_tour
from beehouse_layout.solver.types import Solution, WorkerStatus
from beehouse_layout.solver.constraints import check_entrance_connectivity
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


def _validate_and_save(
    tile_info: TileInfo, solution: Solution, map_name: str, *, no_hard: bool = False, route: bool = False,
) -> str | None:
    """Validate a solution, save if valid, return path or None."""
    violations = validate_solution(tile_info, solution.assignments, no_hard=no_hard)
    if violations:
        return None
    image, top_padding = render_layout(tile_info, solution)
    path = _output_path(map_name, solution)
    save_layout(image, path)
    if route:
        tour_path = compute_tour_path(tile_info, solution.assignments)
        if tour_path.tiles:
            route_image = render_route(image, tour_path, top_padding)
            save_layout(route_image, path.replace(".png", "_route.png"))
    return path


def _process_improvement(
    tile_info: TileInfo,
    solution: Solution,
    best_so_far: Solution,
    map_name: str,
    *,
    no_hard: bool = False,
    route: bool = False,
) -> tuple[Solution, str | None]:
    """Clean up, validate, and save an improvement. Returns (updated best, message or None)."""
    clean_assignments = dict(solution.assignments)
    cleanup_assignments(tile_info, clean_assignments)
    tour_steps = optimize_tour(tile_info, clean_assignments)
    solution = score_solution(tile_info, clean_assignments, tour_steps)

    if solution.score <= best_so_far.score:
        return best_so_far, None

    path = _validate_and_save(tile_info, solution, map_name, no_hard=no_hard, route=route)
    if path:
        msg = (
            f"  {solution.beehouse_count} bh, "
            f"{solution.flower_count} fl "
            f"({solution.pot_count} pt), "
            f"{solution.tour_steps} steps -> {path}"
        )
        return solution, msg
    return best_so_far, None


def _sa_worker(
    tile_info: TileInfo,
    initial_assignments: dict,
    duration_secs: float,
    seed: int,
    worker_id: int,
    result_queue: multiprocessing.Queue,
    stop_event: multiprocessing.Event,
    *,
    no_hard: bool = False,
) -> None:
    """SA worker process. Sends improvements and status to the queue."""
    random.seed(seed)

    def on_improvement(solution: Solution) -> None:
        result_queue.put(solution)

    def on_progress(iterations: int, elapsed: float, temp: float, bh_count: int, improvements: int) -> None:
        result_queue.put(WorkerStatus(
            worker_id=worker_id,
            iterations=iterations,
            elapsed_secs=elapsed,
            temperature=temp,
            beehouse_count=bh_count,
            improvements=improvements,
        ))

    try:
        anneal(
            tile_info,
            initial_assignments,
            duration_secs=duration_secs,
            on_improvement=on_improvement,
            on_progress=on_progress,
            stop_event=stop_event,
            no_hard=no_hard,
        )
    except KeyboardInterrupt:
        pass


def _run_parallel(
    tile_info: TileInfo,
    assignments: dict,
    sa_duration: float,
    best_so_far: Solution,
    map_name: str,
    workers: int,
    stagnation: int,
    dashboard: Dashboard,
    *,
    no_hard: bool = False,
    route: bool = False,
) -> Solution:
    """Run SA across multiple processes with a live dashboard."""
    result_queue: multiprocessing.Queue = multiprocessing.Queue()
    stop_event = multiprocessing.Event()
    processes: list[multiprocessing.Process] = []

    for i in range(workers):
        seed = random.randint(0, 2**63)
        p = multiprocessing.Process(
            target=_sa_worker,
            args=(tile_info, assignments, sa_duration, seed, i, result_queue, stop_event),
            kwargs={"no_hard": no_hard},
        )
        p.start()
        processes.append(p)

    last_improvement_time = time.monotonic()

    def _handle_msg(msg: WorkerStatus | Solution) -> None:
        nonlocal best_so_far, last_improvement_time
        if isinstance(msg, WorkerStatus):
            dashboard.update_worker(msg)
        elif isinstance(msg, Solution):
            new_best, improvement_msg = _process_improvement(
                tile_info, msg, best_so_far, map_name, no_hard=no_hard, route=route,
            )
            if new_best.score > best_so_far.score:
                best_so_far = new_best
                last_improvement_time = time.monotonic()
                dashboard.update_best(best_so_far)
                if improvement_msg:
                    dashboard.log(improvement_msg)

    try:
        while any(p.is_alive() for p in processes):
            try:
                _handle_msg(result_queue.get(timeout=0.5))
                # Drain remaining queued messages
                while True:
                    try:
                        _handle_msg(result_queue.get_nowait())
                    except queue.Empty:
                        break
            except queue.Empty:
                pass

            if stagnation > 0:
                if time.monotonic() - last_improvement_time >= stagnation:
                    dashboard.log(f"Stopped: no improvement for {stagnation}s")
                    stop_event.set()
                    break
    except KeyboardInterrupt:
        dashboard.log("Stopped by user")
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
@click.option(
    "--no-hard",
    is_flag=True,
    default=False,
    help="Reject solutions with hard-to-access beehouses (near interactable obstacles).",
)
@click.option(
    "--route",
    is_flag=True,
    default=False,
    help="Generate route overlay images alongside layouts.",
)
def optimize(map_file: str, duration: int, workers: int, stagnation: int, no_hard: bool, route: bool) -> None:
    """Calculate optimal beehouse layout."""
    map_data = parse_map(map_file)

    with Dashboard(workers) as dashboard:
        dashboard.log(f"Map: {map_data.name}")

        # Clear previous outputs for this map
        output_dir = Path("outputs") / _slugify(map_data.name)
        if output_dir.exists():
            shutil.rmtree(output_dir)
            dashboard.log(f"Cleared {output_dir}/")

        tile_info = precompute(map_data)

        # Validate entrance connectivity
        entrance_violations = check_entrance_connectivity(tile_info)
        for v in entrance_violations:
            dashboard.log(f"  WARNING: {v}")

        dashboard.log(
            f"Tiles: {len(tile_info.beehouse_tiles)} beehouse-eligible, "
            f"{len(tile_info.flower_tiles)} flower-eligible, "
            f"{len(tile_info.entrance_tiles)} entrances"
        )

        dashboard.log("Greedy construction...")
        assignments = build_greedy(tile_info, no_hard=no_hard)
        cleanup_assignments(tile_info, assignments)
        tour_steps = optimize_tour(tile_info, assignments)
        greedy_solution = score_solution(tile_info, assignments, tour_steps)

        path = _validate_and_save(tile_info, greedy_solution, map_data.name, no_hard=no_hard, route=route)
        if path:
            dashboard.log(
                f"  Greedy: {greedy_solution.beehouse_count} bh, "
                f"{greedy_solution.flower_count} fl "
                f"({greedy_solution.pot_count} pt), "
                f"{greedy_solution.tour_steps} steps"
            )
            dashboard.update_best(greedy_solution)
        else:
            dashboard.log("  Greedy: invalid solution (skipped)")

        sa_duration = float(duration) if duration > 0 else float("inf")
        stop_label = []
        if duration > 0:
            stop_label.append(f"{duration}s")
        if stagnation > 0:
            stop_label.append(f"stagnation {stagnation}s")
        stop_label.append(f"{workers} worker{'s' if workers > 1 else ''}")
        if not duration and not stagnation:
            stop_label.append("Ctrl+C to stop")
        dashboard.log(f"SA: {', '.join(stop_label)}")

        best = _run_parallel(
            tile_info, assignments, sa_duration, greedy_solution, map_data.name,
            workers, stagnation, dashboard, no_hard=no_hard, route=route,
        )

        # Always save best layout on exit (including Ctrl+C)
        best_path = str(Path("outputs") / _slugify(map_data.name) / "best_layout.png")
        best_image, best_top_padding = render_layout(tile_info, best)
        save_layout(best_image, best_path)
        if route:
            tour_path = compute_tour_path(tile_info, best.assignments)
            if tour_path.tiles:
                route_image = render_route(best_image, tour_path, best_top_padding)
                save_layout(route_image, best_path.replace(".png", "_route.png"))

        dashboard.log(
            f"Done: {best.beehouse_count} bh, "
            f"{best.flower_count} fl ({best.pot_count} pt), "
            f"{best.tour_steps} steps -> {best_path}"
        )
