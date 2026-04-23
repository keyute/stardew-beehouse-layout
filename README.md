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

Output: `outputs/<map_stem>_overlay.png`

### Optimize a layout

Runs the optimizer to find the best beehouse layout. Outputs are saved incrementally as better solutions are found.

```sh
# Run indefinitely (Ctrl+C to stop)
uv run beehouse optimize maps/ginger_island_west_left_bottom.yml

# Run for a fixed duration
uv run beehouse optimize --duration 60 maps/ginger_island_west_left_bottom.yml
```

Output: `outputs/<map_name>/<beehouse_count>bh_<flower_count>fl_<pot_count>pt_<steps>st.png`

Previous outputs for the map are cleared on each run.

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

Each character in the map grid corresponds to a tile type defined in the legend. The map must be bounded by obstacles.

### Tile types

| Type       | Description                                                            |
|------------|------------------------------------------------------------------------|
| `path`     | Walkable tile, can place beehouses                                     |
| `pot`      | Walkable tile, can place beehouses or flowers (garden pot, expensive)  |
| `soil`     | Walkable tile, can place beehouses or flowers (direct planting, cheap) |
| `obstacle` | Impassable, cannot place anything                                      |
| `entrance` | Always walkable, player starts here for collection tour                |

## Optimization rules

These are the constraints the optimizer must satisfy. Any layout that violates a rule is invalid.

### Placement

- Beehouses can be placed on `path`, `pot`, or `soil` tiles.
- Flowers can be placed on `pot` tiles (expensive, requires garden pot) or `soil` tiles (cheap, direct planting).
- Nothing can be placed on `obstacle` or `entrance` tiles.
- A tile with a beehouse or flower on it is not walkable.
- A tile without an object is walkable if its type is `path`, `pot`, `soil`, or `entrance`.

### Flower range

A beehouse produces fairy rose honey if at least one fairy rose flower is within **Manhattan distance 5** (
`|dx| + |dy| <= 5`). Every beehouse must have at least one flower in range.

### Accidental pluck prevention (controller)

On a controller, pressing the action button interacts with the tile directly in front of the player (cardinal direction,
1 tile). To prevent accidentally picking flowers while collecting honey, **no flower may be cardinally adjacent to any
walkable tile**. Diagonal adjacency is safe.

This means every flower must be shielded on all four cardinal sides by beehouses, obstacles, other flowers, or the map
edge.

### Beehouse accessibility

Every beehouse must be collectible by the player. A beehouse is accessible if it has at least one walkable tile within
8-directional adjacency (cardinal or diagonal).

#### Accessibility tiers

Collection difficulty depends on the relationship between the beehouse and the walkable tile the player stands on:

| Tier | Condition                                                                                                                                                             | Penalty |
|------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------|
| Easy | Walkable tile is cardinally adjacent to beehouse                                                                                                                      | None    |
| OK   | Walkable tile is diagonally adjacent, and the walkable tile has no cardinally adjacent obstacles                                                                      | None    |
| Hard | Walkable tile is diagonally adjacent, and the walkable tile has at least one cardinally adjacent obstacle (interferes with auto-targeting, requires manual selection) | Yes     |

A beehouse is penalized only if **all** its accessible walkable tiles result in Hard collection.

### Connectivity

All beehouses must be reachable from an `entrance` tile. Specifically, every beehouse must have at least one adjacent (
8-directional) walkable tile that is connected to an entrance via cardinal-direction walkable paths.

Isolated pockets of walkable tiles that have no beehouses nearby do not need to be connected.

All `entrance` tiles must be reachable.

### Collection tour

The player collects honey by walking from an entrance tile, visiting every beehouse, and returning. Each tile traversed
counts as one step, **including backtracking** through dead-end corridors.

## Scoring

Layouts are compared using a weighted score (higher is better):

```
score = 10000 * beehouses - 1 * steps - 100 * pots - 50 * hard_collect
```

| Metric         | Weight | Rationale                                                      |
|----------------|--------|----------------------------------------------------------------|
| Beehouse count | +10000 | Primary goal, each produces 680g fairy rose honey every 4 days |
| Tour steps     | -1     | Time cost of collecting, ~7 times per season                   |
| Pot count      | -100   | Garden pot material cost, one-time                             |
| Hard collect   | -50    | Beehouses requiring manual selection on controller             |

Weights ensure one extra beehouse always outweighs any step/pot/penalty improvement.

## Assets

Sprites in `assets/` are used to render layout images:

| File             | Size    | Purpose                                                  |
|------------------|---------|----------------------------------------------------------|
| `bee_house.png`  | 48x96px | Beehouse sprite (visually 2 tiles tall, occupies 1 tile) |
| `fairy_rose.png` | 48x48px | Flower sprite                                            |
| `wood_floor.png` | 48x48px | Floor under placed objects                               |
| `garden_pot.png` | 48x48px | Garden pot sprite                                        |
