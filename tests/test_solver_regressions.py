import random
from pathlib import Path

from beehouse_layout.map.parser import parse_map
from beehouse_layout.solver.annealing import anneal
from beehouse_layout.solver.greedy import build_greedy, exhaustive_fill
from beehouse_layout.solver.scoring import score_solution
from beehouse_layout.solver.tile_info import precompute
from beehouse_layout.solver.tour import optimize_tour_metrics
from beehouse_layout.solver.validator import cleanup_assignments, validate_solution


ROOT = Path(__file__).resolve().parents[1]


def _initial_solution(map_name: str, seed: int, *, no_hard: bool = False):
    random.seed(seed)
    tile_info = precompute(parse_map(str(ROOT / "maps" / f"{map_name}.yml")))
    assignments = build_greedy(tile_info, no_hard=no_hard)
    cleanup_assignments(tile_info, assignments)
    exhaustive_fill(tile_info, assignments, no_hard=no_hard, attempts=200 if no_hard else 100)
    cleanup_assignments(tile_info, assignments)
    return tile_info, assignments


def _score(tile_info, assignments):
    route = optimize_tour_metrics(tile_info, assignments)
    return score_solution(
        tile_info,
        assignments,
        route.steps,
        route_turns=route.turns,
        route_revisits=route.revisits,
    )


def _assert_meets_baseline(solution, baseline):
    assert solution.beehouse_count >= baseline["beehouses"]
    assert solution.flower_count <= baseline["flowers"]
    assert solution.pot_count <= baseline["pots"]
    assert solution.tour_steps <= baseline["steps"]
    if "turns" in baseline:
        assert solution.route_turns <= baseline["turns"]
    if "revisits" in baseline:
        assert solution.route_revisits <= baseline["revisits"]
    if "hard_access" in baseline:
        assert solution.obstacle_diagonal_count <= baseline["hard_access"]


def test_anneal_does_not_return_invalid_single_flower_high_counts():
    baseline = {"beehouses": 48, "flowers": 1, "pots": 0, "steps": 64}
    for seed in (3, 4, 8):
        tile_info, assignments = _initial_solution("single_flower", seed)
        solution, _ = anneal(
            tile_info,
            assignments,
            duration_secs=float("inf"),
            max_iterations=10_000,
        )

        assert not validate_solution(tile_info, solution.assignments)
        _assert_meets_baseline(solution, baseline)


def test_small_maps_reach_known_optima_across_seed_samples():
    cases = [
        ("single_flower", {"beehouses": 48, "flowers": 1, "pots": 0, "steps": 64}),
        ("quality_sprinkler", {"beehouses": 76, "flowers": 8, "pots": 0, "steps": 92}),
    ]

    for map_name, baseline in cases:
        for seed in range(1, 6):
            tile_info, assignments = _initial_solution(map_name, seed)
            solution = _score(tile_info, assignments)

            assert not validate_solution(tile_info, solution.assignments)
            _assert_meets_baseline(solution, baseline)


def test_route_first_score_prefers_steps_before_turns():
    tile_info, assignments = _initial_solution("quality_sprinkler", 1)

    better_steps = score_solution(tile_info, assignments, tour_steps=90, route_turns=10)
    worse_steps_fewer_turns = score_solution(tile_info, assignments, tour_steps=91, route_turns=0)

    assert better_steps.score > worse_steps_fewer_turns.score
