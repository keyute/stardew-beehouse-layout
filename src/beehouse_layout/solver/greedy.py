"""Phase 1: Greedy construction of an initial beehouse layout."""

from __future__ import annotations

from collections import deque

from beehouse_layout.constants import BEEHOUSE_TILES
from beehouse_layout.solver.constraints import (
    check_connectivity,
    check_flower_coverage,
    check_flower_safety,
    classify_beehouse_access,
)
from beehouse_layout.solver.tile_info import TileInfo
from beehouse_layout.solver.types import TileState


def _can_shield_flower(
    pos: tuple[int, int],
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
) -> list[tuple[int, int]] | None:
    """Check if a flower at pos can be shielded on all 8 sides. Returns positions needing beehouses, or None."""
    need_beehouses: list[tuple[int, int]] = []
    for nb in tile_info.all_neighbors[pos]:
        if nb in tile_info.obstacle_tiles:
            continue  # naturally shields (obstacle or interactable)
        tt = tile_info.tile_type.get(nb)
        if tt is None:
            continue  # map edge, naturally shields
        if tt not in BEEHOUSE_TILES:
            return None  # can't shield (e.g. entrance, walkway)
        state = assignments.get(nb, TileState.EMPTY)
        if state == TileState.BEEHOUSE or state == TileState.FLOWER:
            continue  # already shields
        need_beehouses.append(nb)
    return need_beehouses


def _try_place_cluster(
    pos: tuple[int, int],
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
    *,
    no_hard: bool = False,
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
        access = classify_beehouse_access(sp, tile_info, assignments)
        if access is None or (no_hard and access == "hard"):
            _rollback(assignments, saved_states)
            return False

    # Validate connectivity
    if not check_connectivity(tile_info, assignments):
        _rollback(assignments, saved_states)
        return False

    return True


def _try_place_flower_group(
    positions: set[tuple[int, int]],
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
    *,
    no_hard: bool = False,
) -> bool:
    """Try to place multiple flowers atomically with shared shielding. Returns True if successful."""
    # Validate all positions are flower-eligible and empty
    for pos in positions:
        if pos not in tile_info.flower_tiles:
            return False
        if assignments.get(pos, TileState.EMPTY) != TileState.EMPTY:
            return False

    # Compute shield positions needed (neighbors not in group, not already shielded)
    shield_needed: set[tuple[int, int]] = set()
    for pos in positions:
        for nb in tile_info.all_neighbors[pos]:
            if nb in positions:
                continue  # shielded by another flower in group
            if nb in tile_info.obstacle_tiles:
                continue  # naturally shielded
            tt = tile_info.tile_type.get(nb)
            if tt is None:
                continue  # map edge
            if tt not in BEEHOUSE_TILES:
                return False  # can't shield (entrance, walkway)
            state = assignments.get(nb, TileState.EMPTY)
            if state == TileState.BEEHOUSE or state == TileState.FLOWER:
                continue  # already shielded
            if state != TileState.EMPTY:
                return False
            shield_needed.add(nb)

    # Save state for rollback (targeted, not full copy)
    saved_states: dict[tuple[int, int], TileState | None] = {}
    for pos in positions:
        saved_states[pos] = assignments.get(pos)
    for sp in shield_needed:
        saved_states[sp] = assignments.get(sp)

    # Place all flowers and shield beehouses
    for pos in positions:
        assignments[pos] = TileState.FLOWER
    for sp in shield_needed:
        assignments[sp] = TileState.BEEHOUSE

    # Validate flower safety
    for pos in positions:
        if not check_flower_safety(pos, tile_info, assignments):
            _rollback(assignments, saved_states)
            return False

    # Validate new beehouse accessibility
    for sp in shield_needed:
        access = classify_beehouse_access(sp, tile_info, assignments)
        if access is None or (no_hard and access == "hard"):
            _rollback(assignments, saved_states)
            return False

    # Check adjacent existing beehouses still accessible
    all_placed = positions | shield_needed
    for placed in all_placed:
        for nb in tile_info.all_neighbors[placed]:
            if nb not in all_placed and assignments.get(nb) == TileState.BEEHOUSE:
                access = classify_beehouse_access(nb, tile_info, assignments)
                if access is None or (no_hard and access == "hard"):
                    _rollback(assignments, saved_states)
                    return False

    # Validate connectivity
    if not check_connectivity(tile_info, assignments):
        _rollback(assignments, saved_states)
        return False

    return True


def _find_flower_components(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
) -> list[set[tuple[int, int]]]:
    """Find 8-connected components of empty flower-eligible tiles."""
    unvisited = {
        pos for pos in tile_info.flower_tiles
        if assignments.get(pos, TileState.EMPTY) == TileState.EMPTY
    }
    components: list[set[tuple[int, int]]] = []
    while unvisited:
        seed = next(iter(unvisited))
        component: set[tuple[int, int]] = set()
        queue = deque([seed])
        while queue:
            pos = queue.popleft()
            if pos in component:
                continue
            component.add(pos)
            unvisited.discard(pos)
            for nb in tile_info.all_neighbors[pos]:
                if nb in unvisited:
                    queue.append(nb)
        components.append(component)
    return components


def _filter_shieldable(
    component: set[tuple[int, int]],
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
) -> set[tuple[int, int]]:
    """Filter a flower component to tiles that can be part of a shielded group."""
    candidates = set(component)
    changed = True
    while changed:
        changed = False
        to_remove: set[tuple[int, int]] = set()
        for pos in candidates:
            for nb in tile_info.all_neighbors[pos]:
                if nb in candidates:
                    continue  # shielded by group member
                if nb in tile_info.obstacle_tiles:
                    continue  # naturally shielded
                tt = tile_info.tile_type.get(nb)
                if tt is None:
                    continue  # map edge
                if tt not in BEEHOUSE_TILES:
                    to_remove.add(pos)
                    break
                state = assignments.get(nb, TileState.EMPTY)
                if state in (TileState.BEEHOUSE, TileState.FLOWER):
                    continue  # already shielded
        if to_remove:
            candidates -= to_remove
            changed = True
    return candidates


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


def build_greedy(tile_info: TileInfo, *, no_hard: bool = False) -> dict[tuple[int, int], TileState]:
    """Build an initial layout using greedy flower cluster placement + beehouse filling."""
    assignments: dict[tuple[int, int], TileState] = {}

    # Step 1: Place multi-flower groups (adjacent flowers shield each other)
    components = _find_flower_components(tile_info, assignments)
    for component in sorted(components, key=len, reverse=True):
        filtered = _filter_shieldable(component, tile_info, assignments)
        if len(filtered) < 2:
            continue
        # Try placing the full filtered group
        if _try_place_flower_group(filtered, tile_info, assignments, no_hard=no_hard):
            continue
        # Shrink by removing periphery tiles (fewest in-group neighbors) and retry
        shrinkable = set(filtered)
        for _ in range(min(10, len(shrinkable))):
            if len(shrinkable) < 2:
                break
            # Remove tile with fewest in-group neighbors
            worst = min(
                shrinkable,
                key=lambda p: sum(1 for nb in tile_info.all_neighbors[p] if nb in shrinkable),
            )
            shrinkable.discard(worst)
            if _try_place_flower_group(shrinkable, tile_info, assignments, no_hard=no_hard):
                break

    # Step 2: Place remaining single flower clusters greedily by coverage
    candidates = sorted(
        tile_info.flower_tiles,
        key=lambda p: _coverage_score(p, tile_info, assignments),
        reverse=True,
    )

    for pos in candidates:
        if assignments.get(pos, TileState.EMPTY) != TileState.EMPTY:
            continue
        _try_place_cluster(pos, tile_info, assignments, no_hard=no_hard)

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
            access = classify_beehouse_access(nb, tile_info, assignments)
            if access is None or (no_hard and access == "hard"):
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
