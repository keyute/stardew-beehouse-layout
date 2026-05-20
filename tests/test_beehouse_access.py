from beehouse_layout.map.parser import MapData
from beehouse_layout.solver.constraints import classify_beehouse_access
from beehouse_layout.solver.tile_info import precompute
from beehouse_layout.solver.types import TileState


def _tile_info(rows):
    return precompute(MapData(name="Access", grid=rows))


def test_diagonal_collector_adjacent_to_non_squeeze_interactable_is_hard():
    tile_info = _tile_info([
        ["interactable", "obstacle", "path"],
        ["obstacle", "path", "obstacle"],
        ["path", "path", "path"],
    ])
    assignments = {(2, 0): TileState.BEEHOUSE}

    assert classify_beehouse_access((2, 0), tile_info, assignments) == "hard"


def test_original_example_diagonal_collect_is_hard():
    tile_info = _tile_info([
        ["obstacle", "obstacle", "path"],
        ["obstacle", "path", "obstacle"],
        ["path", "path", "interactable"],
    ])
    assignments = {(2, 0): TileState.BEEHOUSE}

    assert classify_beehouse_access((2, 0), tile_info, assignments) == "hard"


def test_diagonal_collector_ignores_interactable_two_tiles_away():
    tile_info = _tile_info([
        ["obstacle", "obstacle", "path"],
        ["obstacle", "path", "obstacle"],
        ["path", "path", "path"],
        ["path", "path", "interactable"],
    ])
    assignments = {(2, 0): TileState.BEEHOUSE}

    assert classify_beehouse_access((2, 0), tile_info, assignments) == "ok"


def test_diagonal_collector_ignores_non_interactable_obstacle():
    tile_info = _tile_info([
        ["obstacle", "obstacle", "path"],
        ["obstacle", "path", "obstacle"],
        ["path", "path", "obstacle"],
    ])
    assignments = {(2, 0): TileState.BEEHOUSE}

    assert classify_beehouse_access((2, 0), tile_info, assignments) == "ok"


def test_cardinal_collector_is_easy_with_nearby_interactable():
    tile_info = _tile_info([
        ["path", "path"],
        ["interactable", "obstacle"],
    ])
    assignments = {(1, 0): TileState.BEEHOUSE}

    assert classify_beehouse_access((1, 0), tile_info, assignments) == "easy"


def test_cardinal_collector_overrides_hard_diagonal_collector():
    tile_info = _tile_info([
        ["obstacle", "path", "path"],
        ["obstacle", "path", "interactable"],
        ["obstacle", "obstacle", "obstacle"],
    ])
    assignments = {(2, 0): TileState.BEEHOUSE}

    assert classify_beehouse_access((2, 0), tile_info, assignments) == "easy"


def test_any_non_hard_diagonal_collector_keeps_access_ok():
    tile_info = _tile_info([
        ["path", "obstacle", "obstacle"],
        ["interactable", "path", "obstacle"],
        ["obstacle", "obstacle", "path"],
    ])
    assignments = {(1, 1): TileState.BEEHOUSE}

    assert classify_beehouse_access((1, 1), tile_info, assignments) == "ok"


def test_mixed_hard_and_non_hard_diagonal_collectors_are_ok():
    tile_info = _tile_info([
        ["path", "obstacle", "obstacle"],
        ["interactable", "path", "obstacle"],
        ["obstacle", "obstacle", "path"],
    ])
    assignments = {(1, 1): TileState.BEEHOUSE}

    assert classify_beehouse_access((1, 1), tile_info, assignments) == "ok"


def test_all_diagonal_collectors_hard_makes_access_hard():
    tile_info = _tile_info([
        ["interactable", "obstacle", "interactable"],
        ["obstacle", "path", "obstacle"],
        ["path", "obstacle", "path"],
        ["interactable", "path", "interactable"],
    ])
    assignments = {(1, 1): TileState.BEEHOUSE}

    assert classify_beehouse_access((1, 1), tile_info, assignments) == "hard"


def test_no_adjacent_walkable_collector_is_inaccessible():
    tile_info = _tile_info([
        ["obstacle", "obstacle", "obstacle"],
        ["obstacle", "path", "obstacle"],
        ["obstacle", "obstacle", "obstacle"],
    ])
    assignments = {(1, 1): TileState.BEEHOUSE}

    assert classify_beehouse_access((1, 1), tile_info, assignments) is None


def test_interactable_adjacent_to_beehouse_only_does_not_make_diagonal_hard():
    tile_info = _tile_info([
        ["obstacle", "path", "interactable"],
        ["path", "obstacle", "obstacle"],
        ["obstacle", "obstacle", "obstacle"],
    ])
    assignments = {(1, 0): TileState.BEEHOUSE}

    assert classify_beehouse_access((1, 0), tile_info, assignments) == "ok"
