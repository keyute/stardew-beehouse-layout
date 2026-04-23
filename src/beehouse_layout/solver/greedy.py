"""Phase 1: Greedy construction of an initial beehouse layout."""

from __future__ import annotations

from beehouse_layout.constants import BEEHOUSE_TILES, TILE_OBSTACLE
from beehouse_layout.solver.constraints import (
    TileInfo,
    check_connectivity,
    check_flower_coverage,
    check_flower_safety,
    classify_beehouse_access,
)
from beehouse_layout.solver.types import TileState


def _can_shield_flower(
    pos: tuple[int, int],
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
) -> list[tuple[int, int]] | None:
    """Check if a flower at pos can be shielded. Returns positions needing beehouses, or None."""
    need_beehouses: list[tuple[int, int]] = []
    for nb in tile_info.cardinal_neighbors[pos]:
        tt = tile_info.tile_type.get(nb)
        if tt == TILE_OBSTACLE:
            continue  # naturally shields
        if tt not in BEEHOUSE_TILES:
            return None  # can't shield (e.g. entrance)
        state = assignments.get(nb, TileState.EMPTY)
        if state == TileState.BEEHOUSE or state == TileState.FLOWER:
            continue  # already shields
        need_beehouses.append(nb)
    return need_beehouses


def _try_place_cluster(
    pos: tuple[int, int],
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
) -> bool:
    """Try to place a flower at pos + shielding beehouses. Returns True if successful."""
    if pos not in tile_info.flower_tiles:
        return False
    if assignments.get(pos, TileState.EMPTY) != TileState.EMPTY:
        return False

    shield_positions = _can_shield_flower(pos, tile_info, assignments)
    if shield_positions is None:
        return False

    # Save state
    saved_states: dict[tuple[int, int], TileState | None] = {pos: None}
    for sp in shield_positions:
        saved_states[sp] = assignments.get(sp)

    # Place
    assignments[pos] = TileState.FLOWER
    for sp in shield_positions:
        assignments[sp] = TileState.BEEHOUSE

    # Validate flower safety
    if not check_flower_safety(pos, tile_info, assignments):
        _rollback(assignments, saved_states)
        return False

    # Validate beehouse accessibility
    for sp in shield_positions:
        if classify_beehouse_access(sp, tile_info, assignments) is None:
            _rollback(assignments, saved_states)
            return False

    # Validate connectivity
    if not check_connectivity(tile_info, assignments):
        _rollback(assignments, saved_states)
        return False

    return True


def _rollback(
    assignments: dict[tuple[int, int], TileState],
    saved: dict[tuple[int, int], TileState | None],
) -> None:
    for pos, state in saved.items():
        if state is None:
            assignments.pop(pos, None)
        else:
            assignments[pos] = state


def _coverage_score(
    pos: tuple[int, int],
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
) -> int:
    """Count how many empty beehouse-eligible tiles are in flower range of pos."""
    count = 0
    for nb in tile_info.flower_diamond[pos]:
        if nb in tile_info.beehouse_tiles:
            if assignments.get(nb, TileState.EMPTY) == TileState.EMPTY:
                count += 1
    return count


def build_greedy(tile_info: TileInfo) -> dict[tuple[int, int], TileState]:
    """Build an initial layout using greedy flower cluster placement + beehouse filling."""
    assignments: dict[tuple[int, int], TileState] = {}

    # Step 1: Place flower clusters greedily by coverage
    # Sort candidates by coverage potential (descending)
    candidates = sorted(
        tile_info.flower_tiles,
        key=lambda p: _coverage_score(p, tile_info, assignments),
        reverse=True,
    )

    for pos in candidates:
        if assignments.get(pos, TileState.EMPTY) != TileState.EMPTY:
            continue
        _try_place_cluster(pos, tile_info, assignments)

    # Step 2: Fill additional beehouses near existing flowers
    # Only place beehouses adjacent to walkable tiles (ensures accessibility)
    flower_positions = [
        pos for pos, state in assignments.items() if state == TileState.FLOWER
    ]
    for flower_pos in flower_positions:
        for nb in tile_info.flower_diamond[flower_pos]:
            if nb not in tile_info.beehouse_tiles:
                continue
            if assignments.get(nb, TileState.EMPTY) != TileState.EMPTY:
                continue

            assignments[nb] = TileState.BEEHOUSE

            # Must be accessible
            if classify_beehouse_access(nb, tile_info, assignments) is None:
                del assignments[nb]
                continue

            # Must not make adjacent beehouses inaccessible
            neighbor_lost_access = False
            for adj in tile_info.all_neighbors[nb]:
                if assignments.get(adj) == TileState.BEEHOUSE:
                    if classify_beehouse_access(adj, tile_info, assignments) is None:
                        neighbor_lost_access = True
                        break
            if neighbor_lost_access:
                del assignments[nb]
                continue

            # Must not expose any adjacent flower
            safe = True
            for fnb in tile_info.cardinal_neighbors[nb]:
                if assignments.get(fnb) == TileState.FLOWER:
                    if not check_flower_safety(fnb, tile_info, assignments):
                        safe = False
                        break
            if not safe:
                del assignments[nb]
                continue

            # Must maintain connectivity
            if not check_connectivity(tile_info, assignments):
                del assignments[nb]

    return assignments


def _fix_connectivity(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
) -> None:
    """Remove beehouses until connectivity is restored."""
    from collections import deque

    beehouses = [
        pos for pos, state in assignments.items() if state == TileState.BEEHOUSE
    ]
    # Remove beehouses with fewest neighbors first (least connected)
    beehouses.sort(
        key=lambda p: sum(
            1 for nb in tile_info.all_neighbors[p]
            if assignments.get(nb) == TileState.BEEHOUSE
        )
    )
    for pos in beehouses:
        if check_connectivity(tile_info, assignments):
            break
        if assignments.get(pos) == TileState.BEEHOUSE:
            del assignments[pos]


def _remove_unsafe_flowers(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
) -> None:
    to_remove = [
        pos for pos, state in assignments.items()
        if state == TileState.FLOWER
        and not check_flower_safety(pos, tile_info, assignments)
    ]
    for pos in to_remove:
        del assignments[pos]


def _remove_uncovered_beehouses(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
) -> None:
    to_remove = [
        pos for pos, state in assignments.items()
        if state == TileState.BEEHOUSE
        and not check_flower_coverage(pos, tile_info, assignments)
    ]
    for pos in to_remove:
        del assignments[pos]
