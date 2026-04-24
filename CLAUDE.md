# Running

Use `uv run beehouse` to run the CLI (e.g. `uv run beehouse optimize maps/...`).

# Constants Placement

Constants must live at the narrowest scope that covers all their usages:

- **Single file**: define in that file
- **Multiple files in the same package**: define in a `constants.py` within that package
- **Multiple packages**: define in a `constants.py` at the nearest common ancestor package
