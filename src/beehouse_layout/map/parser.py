from dataclasses import dataclass
from pathlib import Path

import yaml

_KEY_NAME = "name"
_KEY_LEGEND = "legend"
_KEY_MAP = "map"
_EMPTY_TILE = " "


@dataclass
class MapData:
    name: str
    grid: list[list[str | None]]


def parse_map(path: str) -> MapData:
    raw = yaml.safe_load(Path(path).read_text())
    legend = raw[_KEY_LEGEND]
    rows = raw[_KEY_MAP].rstrip("\n").split("\n")

    grid: list[list[str | None]] = []
    for row in rows:
        grid.append([legend.get(ch) if ch != _EMPTY_TILE else None for ch in row])

    return MapData(name=raw[_KEY_NAME], grid=grid)
