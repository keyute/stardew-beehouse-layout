"""Font loading for render modules."""

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

FONT_PATH = "assets/Inter.ttf"


@lru_cache(maxsize=None)
def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load the bundled Inter font at *size*, falling back to PIL's default."""
    try:
        path = Path(FONT_PATH)
        if not path.exists():
            path = Path(__file__).resolve().parents[3] / FONT_PATH
        return ImageFont.truetype(str(path), size)
    except (OSError, AttributeError):
        return ImageFont.load_default()
