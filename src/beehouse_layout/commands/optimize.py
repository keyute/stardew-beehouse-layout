import csv
import json
import logging
import multiprocessing
import os
import queue
import random
import shutil
import signal
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from types import FrameType

import click

from beehouse_layout.commands.constants import OUTPUT_DIR
from beehouse_layout.map.parser import parse_map
from beehouse_layout.render.dashboard import Dashboard
from beehouse_layout.render.layout import render_layout
from beehouse_layout.render.utils import save_image
from beehouse_layout.render.route import render_route
from beehouse_layout.render.text import render_text, save_text
from beehouse_layout.solver.annealing import anneal
from beehouse_layout.solver.scoring import score_solution
from beehouse_layout.solver.tile_info import TileInfo, precompute
from beehouse_layout.solver.tour import compute_tour_path, optimize_tour
from beehouse_layout.solver.types import AnnealStats, Solution, WorkerStatus
from beehouse_layout.solver.constraints import check_entrance_connectivity
from beehouse_layout.solver.validator import cleanup_assignments, validate_solution
from beehouse_layout.solver.greedy import build_greedy, exhaustive_fill

MAX_SEED = 2**63


def _make_sigint_handler(
    stop_event: multiprocessing.Event,
    user_cancelled: list[bool],
) -> Callable[[int, FrameType | None], None]:
    """First Ctrl+C sets stop_event; second Ctrl+C force-exits."""
    hit_count = 0

    def handler(signum: int, frame: FrameType | None) -> None:
        nonlocal hit_count
        hit_count += 1
        if hit_count == 1:
            user_cancelled[0] = True
            stop_event.set()
        else:
            os._exit(1)

    return handler


def _output_path(map_slug: str, solution: Solution) -> str:
    filename = (
        f"{solution.beehouse_count}bh_"
        f"{solution.flower_count}fl_"
        f"{solution.pot_count}pt_"
        f"{solution.tour_steps}st"
    )
    base = OUTPUT_DIR / map_slug / filename
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
    save_image(image, path)
    if route:
        tour_path = compute_tour_path(tile_info, solution.assignments)
        if tour_path.tiles:
            route_image = render_route(image, tour_path, top_padding)
            save_image(route_image, path.replace(".png", "_route.png"))
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
    stats: bool = False,
    initial_temp: float | None = None,
    cooling_rate: float | None = None,
    min_temp: float | None = None,
    max_iterations: int = 0,
) -> None:
    """SA worker process. Sends improvements and status to the queue."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
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

    def on_stats(snapshot: dict) -> None:
        snapshot["worker_id"] = worker_id
        result_queue.put(("stats_snapshot", snapshot))

    _, anneal_stats = anneal(
        tile_info,
        initial_assignments,
        duration_secs=duration_secs,
        on_improvement=on_improvement,
        on_progress=on_progress,
        on_stats=on_stats if stats else None,
        stop_event=stop_event,
        no_hard=no_hard,
        initial_temp=initial_temp,
        cooling_rate=cooling_rate,
        min_temp=min_temp,
        max_iterations=max_iterations,
    )
    result_queue.put(("anneal_stats", worker_id, anneal_stats))


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
    stats: bool = False,
    initial_temp: float | None = None,
    cooling_rate: float | None = None,
    min_temp: float | None = None,
    max_iterations: int = 0,
) -> tuple[Solution, bool, list[dict], dict[int, AnnealStats]]:
    """Run SA across multiple processes with a live dashboard.

    Returns (best_solution, user_stopped, trajectory_snapshots, worker_anneal_stats).
    """
    result_queue: multiprocessing.Queue = multiprocessing.Queue()
    stop_event = multiprocessing.Event()
    user_cancelled: list[bool] = [False]
    processes: list[multiprocessing.Process] = []
    trajectory: list[dict] = []
    worker_anneal_stats: dict[int, AnnealStats] = {}

    for i in range(workers):
        seed = random.randint(0, MAX_SEED)
        p = multiprocessing.Process(
            target=_sa_worker,
            args=(tile_info, assignments, sa_duration, seed, i, result_queue, stop_event),
            kwargs={
                "no_hard": no_hard, "stats": stats,
                "initial_temp": initial_temp, "cooling_rate": cooling_rate, "min_temp": min_temp,
                "max_iterations": max_iterations,
            },
        )
        p.start()
        processes.append(p)

    old_sigint = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, _make_sigint_handler(stop_event, user_cancelled))

    last_improvement_time = time.monotonic()

    def _handle_msg(msg: object) -> None:
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
        elif isinstance(msg, tuple):
            if msg[0] == "stats_snapshot":
                trajectory.append(msg[1])
            elif msg[0] == "anneal_stats":
                worker_anneal_stats[msg[1]] = msg[2]

    stopped_by_stagnation = False
    try:
        while any(p.is_alive() for p in processes):
            if stop_event.is_set():
                break
            try:
                _handle_msg(result_queue.get(timeout=0.5))
                while not stop_event.is_set():
                    try:
                        _handle_msg(result_queue.get_nowait())
                    except queue.Empty:
                        break
            except (queue.Empty, InterruptedError):
                pass

            if stagnation > 0:
                if time.monotonic() - last_improvement_time >= stagnation:
                    stopped_by_stagnation = True
                    stop_event.set()
                    break
    finally:
        stop_event.set()
        signal.signal(signal.SIGINT, old_sigint)
        if user_cancelled[0]:
            # User cancelled — kill workers immediately
            for p in processes:
                p.terminate()
            for p in processes:
                p.join(timeout=2)
        else:
            # Normal/stagnation exit — let workers send final stats
            for p in processes:
                p.join(timeout=5)
            # Force-kill any that didn't exit in time
            for p in processes:
                if p.is_alive():
                    p.terminate()
                    p.join(timeout=2)
        # Drain remaining messages to capture final improvements and stats
        if not user_cancelled[0]:
            while True:
                try:
                    _handle_msg(result_queue.get_nowait())
                except queue.Empty:
                    break

    if user_cancelled[0]:
        dashboard.log("Stopped by user")
    elif stopped_by_stagnation:
        dashboard.log(f"Stopped: no improvement for {stagnation}s")

    return best_so_far, user_cancelled[0], trajectory, worker_anneal_stats


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
@click.option(
    "--text",
    is_flag=True,
    default=False,
    help="Save a machine-readable text layout alongside the PNG.",
)
@click.option(
    "--seed",
    default=None,
    type=int,
    help="Random seed for reproducible runs.",
)
@click.option(
    "--stats",
    is_flag=True,
    default=False,
    help="Write SA trajectory CSV and move statistics JSON.",
)
@click.option(
    "--temp",
    default=None,
    type=float,
    help="Override SA initial temperature (default: 100.0).",
)
@click.option(
    "--cooling-rate",
    default=None,
    type=float,
    help="Override SA cooling rate (default: 0.9999).",
)
@click.option(
    "--min-temp",
    default=None,
    type=float,
    help="Override SA minimum temperature before reheat (default: 0.01).",
)
@click.option(
    "--max-iterations",
    default=0,
    type=int,
    help="Stop each worker after N iterations (0 = unlimited). Enables deterministic runs with --seed.",
)
@click.option(
    "-v", "--verbose",
    is_flag=True,
    default=False,
    help="Enable debug logging for greedy construction.",
)
def optimize(
    map_file: str, duration: int, workers: int, stagnation: int,
    no_hard: bool, route: bool, text: bool, seed: int | None, stats: bool,
    temp: float | None, cooling_rate: float | None, min_temp: float | None,
    max_iterations: int, verbose: bool,
) -> None:
    """Calculate optimal beehouse layout."""
    if verbose:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
        pkg_logger = logging.getLogger("beehouse_layout")
        pkg_logger.setLevel(logging.DEBUG)
        pkg_logger.addHandler(handler)

    if seed is not None:
        random.seed(seed)

    map_data = parse_map(map_file)
    map_slug = Path(map_file).stem

    with Dashboard(workers) as dashboard:
        dashboard.log(f"Map: {map_data.name}")

        # Clear previous outputs for this map
        output_dir = OUTPUT_DIR / map_slug
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
        exhaustive_fill(tile_info, assignments, no_hard=no_hard)
        cleanup_assignments(tile_info, assignments)
        tour_steps = optimize_tour(tile_info, assignments)
        greedy_solution = score_solution(tile_info, assignments, tour_steps)

        path = _validate_and_save(tile_info, greedy_solution, map_slug, no_hard=no_hard, route=route)
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

        best, user_stopped, trajectory, worker_anneal_stats = _run_parallel(
            tile_info, assignments, sa_duration, greedy_solution, map_slug,
            workers, stagnation, dashboard, no_hard=no_hard, route=route, stats=stats,
            initial_temp=temp, cooling_rate=cooling_rate, min_temp=min_temp,
            max_iterations=max_iterations,
        )

        # Post-SA exhaustive fill to catch remaining beehouses
        post_assignments = dict(best.assignments)
        exhaustive_fill(tile_info, post_assignments, no_hard=no_hard)
        cleanup_assignments(tile_info, post_assignments)
        post_tour = optimize_tour(tile_info, post_assignments)
        post_solution = score_solution(tile_info, post_assignments, post_tour)
        if post_solution.score > best.score:
            best = post_solution
            dashboard.log(
                f"  Fill: {best.beehouse_count} bh, "
                f"{best.flower_count} fl ({best.pot_count} pt), "
                f"{best.tour_steps} steps"
            )

        best_path = str(OUTPUT_DIR / map_slug / "best_layout.png")
        best_image, best_top_padding = render_layout(tile_info, best)
        save_image(best_image, best_path)
        if text:
            text_path = best_path.replace(".png", ".txt")
            save_text(render_text(tile_info, best), text_path)
        if route and not user_stopped:
            tour_path = compute_tour_path(tile_info, best.assignments)
            if tour_path.tiles:
                route_image = render_route(best_image, tour_path, best_top_padding)
                save_image(route_image, best_path.replace(".png", "_route.png"))

        if stats and trajectory:
            stats_dir = OUTPUT_DIR / map_slug
            # Write trajectory CSV
            csv_path = str(stats_dir / "trajectory.csv")
            fieldnames = ["worker_id", "iteration", "elapsed_secs", "temperature",
                          "current_score", "best_score", "acceptance_rate",
                          "beehouse_count", "improvements"]
            with open(csv_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for row in sorted(trajectory, key=lambda r: (r["worker_id"], r["iteration"])):
                    writer.writerow(row)
            dashboard.log(f"Trajectory: {csv_path}")

            # Write move stats JSON
            json_path = str(stats_dir / "move_stats.json")
            all_move_stats = {}
            for wid, astats in sorted(worker_anneal_stats.items()):
                all_move_stats[f"worker_{wid}"] = {
                    name: asdict(ms) for name, ms in astats.move_stats.items()
                }
            with open(json_path, "w") as f:
                json.dump(all_move_stats, f, indent=2)
            dashboard.log(f"Move stats: {json_path}")

        label = "Stopped" if user_stopped else "Done"
        dashboard.log(
            f"{label}: {best.beehouse_count} bh, "
            f"{best.flower_count} fl ({best.pot_count} pt), "
            f"{best.tour_steps} steps -> {best_path}"
        )
