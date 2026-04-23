# Stardew Valley Beehouse Layout Optimizer

Finds optimized beehouse layouts for Stardew Valley maps, maximizing fairy rose honey production while respecting game
mechanics and controller-safe flower placement.

## Setup

Requires Python 3.14+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
```

## Usage

### Validate a map

Generates a color-coded overlay image to verify the map data is correct.

```sh
uv run beehouse validate maps/ginger_island_west_left_bottom.yml
```

### Optimize a layout

Runs the optimizer to find the best beehouse layout. Uses all CPU cores by default and auto-stops after 60 seconds
without improvement. Outputs are saved incrementally as better solutions are found.

```sh
uv run beehouse optimize maps/ginger_island_west_left_bottom.yml
```

Options:

- `--duration N` — stop after N seconds (default: unlimited)
- `--workers N` — number of parallel workers (default: CPU count)
- `--stagnation N` — auto-stop after N seconds without improvement (default: 60, 0 to disable)

## Map format

Maps are YAML files with three sections:

```yaml
name: Map Name
legend:
  ".": path
  P: pot
  X: obstacle
  S: soil
  E: entrance
map: |
  .....PPXXXXXXXXPPP
  .....PPXXXXXXXXPPP
  ...
```

Each character in the map grid corresponds to a tile type defined in the legend.

| Type       | Description                                                            |
|------------|------------------------------------------------------------------------|
| `path`     | Walkable tile, can place beehouses                                     |
| `pot`      | Walkable tile, can place beehouses or flowers (garden pot, expensive)  |
| `soil`     | Walkable tile, can place beehouses or flowers (direct planting, cheap) |
| `obstacle` | Impassable, cannot place anything                                      |
| `entrance` | Always walkable, player starts here for collection tour                |

## Layout rules

Any valid layout must satisfy all of these constraints:

- **Flower range**: Every beehouse must have at least one fairy rose within Manhattan distance 5 (`|dx| + |dy| <= 5`)
- **Pluck prevention**: No flower may be cardinally adjacent to a walkable tile (prevents accidental pickup on controller). Flowers must be shielded on all four cardinal sides by beehouses, obstacles, other flowers, or the map edge
- **Beehouse accessibility**: Every beehouse must have at least one walkable tile within 8-directional adjacency. Beehouses only reachable via diagonal with an obstacle nearby are penalized (hard to select on controller)
- **Connectivity**: All beehouses must be reachable from an entrance tile via cardinal-direction walkable paths
- **Collection tour**: The optimizer minimizes the walking steps needed to visit every beehouse from an entrance and return, including backtracking through dead ends
