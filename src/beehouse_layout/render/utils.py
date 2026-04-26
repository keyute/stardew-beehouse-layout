"""Shared render utilities."""

from pathlib import Path

from PIL import Image


def save_image(image: Image.Image, path: str) -> None:
    """Save an image to file, creating parent directories as needed."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
