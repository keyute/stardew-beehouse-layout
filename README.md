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
- `--no-hard` — reject solutions with hard-to-access beehouses (near interactable obstacles)

## Map format

Maps are YAML files with three sections:

```yaml
name: Map Name
legend:
  ".": path
  P: pot
  X: obstacle
  I: interactable
  S: soil
  E: entrance
  W: walkway
map: |
  .....PPXXXXXXXXPPP
  .....PPXXXXXXXXPPP
  ...
```

Each character in the map grid corresponds to a tile type defined in the legend.

| Type           | Description                                                            |
|----------------|------------------------------------------------------------------------|
| `path`         | Walkable tile, can place beehouses                                     |
| `pot`          | Walkable tile, can place beehouses or flowers (garden pot, expensive)  |
| `soil`         | Walkable tile, can place beehouses or flowers (direct planting, cheap) |
| `obstacle`     | Impassable, cannot place anything (rocks, water, buildings, fences)    |
| `interactable` | Impassable, cannot place anything (chests, machines — penalized)       |
| `entrance`     | Always walkable, player starts here for collection tour                |
| `walkway`      | Always walkable, permanent path — no placement allowed                 |

## Layout rules

Any valid layout must satisfy all of these constraints:

- **Flower range**: Every beehouse must have at least one fairy rose within Manhattan distance 5 (`|dx| + |dy| <= 5`)
- **Pluck prevention**: No flower may be adjacent to a walkable tile in any of the 8 directions (prevents accidental
  pickup). Flowers must be shielded on all 8 sides by beehouses, obstacles, other flowers, or the map edge
- **Beehouse accessibility**: Every beehouse must have at least one walkable tile within 8-directional adjacency.
  Beehouses only reachable via diagonal with an interactable obstacle nearby are penalized (risk of accidental
  interaction on controller). Non-interactable obstacles do not incur a penalty. Use `--no-hard` to reject any solution
  with penalized beehouses
- **Entrance connectivity**: Every entrance tile must have at least one cardinal neighbor that is a path, entrance, or
  walkway tile
- **Connectivity**: All beehouses must be reachable from an entrance tile via cardinal-direction walkable paths
- **Collection tour**: The optimizer minimizes the walking steps needed to visit every beehouse from an entrance and
  return, including backtracking through dead ends

## Contributions

If you have any questions or suggestions, feel free to open issues. If you have a feature or improvement you really
want implemented, please implement it yourself and open a pull request and I will review it. Please do not open an
issue or pull request if the content is not meaningful and can be better served with tutorials that is readily available
online.