"""Whole-solution validation and repair."""

from __future__ import annotations

from beehouse_layout.solver.constraints import (
    check_connectivity,
    check_flower_coverage,
    check_flower_safety,
    classify_beehouse_access,
)
from beehouse_layout.solver.tile_info import TileInfo
from beehouse_layout.solver.types import TileState


def validate_solution(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
    *,
    no_hard: bool = False,
) -> list[str]:
    """Validate all constraints. Returns list of violation descriptions."""
    violations: list[str] = []

    for pos, state in assignments.items():
        if state == TileState.BEEHOUSE:
            if pos not in tile_info.beehouse_tiles:
                violations.append(f"Beehouse at {pos} on invalid tile")
            if not check_flower_coverage(pos, tile_info, assignments):
                violations.append(f"Beehouse at {pos} has no flower in range")
            access = classify_beehouse_access(pos, tile_info, assignments)
            if access is None:
                violations.append(f"Beehouse at {pos} is inaccessible")
            elif no_hard and access == "hard":
                violations.append(f"Beehouse at {pos} has hard access (--no-hard)")

        elif state == TileState.FLOWER:
            if pos not in tile_info.flower_tiles:
                violations.append(f"Flower at {pos} on invalid tile")
            if not check_flower_safety(pos, tile_info, assignments):
                violations.append(f"Flower at {pos} has adjacent walkable tile")

    if not check_connectivity(tile_info, assignments):
        violations.append("Walkable tiles are not fully connected")

    return violations


def cleanup_assignments(
    tile_info: TileInfo,
    assignments: dict[tuple[int, int], TileState],
) -> None:
    """Remove invalid beehouses and flowers until all constraints are satisfied."""
    changed = True
    while changed:
        changed = False
        # Remove inaccessible beehouses
        for pos in [
            p for p, s in assignments.items()
            if s == TileState.BEEHOUSE and classify_beehouse_access(p, tile_info, assignments) is None
        ]:
            del assignments[pos]
            changed = True
        # Remove unsafe flowers
        for pos in [
            p for p, s in assignments.items()
            if s == TileState.FLOWER and not check_flower_safety(p, tile_info, assignments)
        ]:
            del assignments[pos]
            changed = True
        # Remove uncovered beehouses
        for pos in [
            p for p, s in assignments.items()
            if s == TileState.BEEHOUSE and not check_flower_coverage(p, tile_info, assignments)
        ]:
            del assignments[pos]
            changed = True
