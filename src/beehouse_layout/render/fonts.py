"""Font loading for render modules."""

from functools import lru_cache

from PIL import ImageFont

FONT_PATH = "assets/Inter.ttf"


@lru_cache(maxsize=None)
def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load the bundled Inter font at *size*, falling back to PIL's default."""
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except (OSError, AttributeError):
        return ImageFont.load_default()
