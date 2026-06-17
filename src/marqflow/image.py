"""Raster image loading and downscaling helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def load_rgb_image(path: str | Path) -> np.ndarray:
    """Load an image as an RGB numpy array."""

    image = Image.open(path).convert('RGB')
    return np.asarray(image)


def save_rgb_image(path: str | Path, image_rgb: np.ndarray) -> None:
    """Save an RGB numpy array to disk."""

    Image.fromarray(image_rgb.astype(np.uint8), mode='RGB').save(path)


def downscale_image(image_rgb: np.ndarray, factor: int) -> np.ndarray:
    """Reduce the image dimensions by an integer factor."""

    if factor < 1:
        raise ValueError('factor must be >= 1')
    if factor == 1:
        return image_rgb

    height, width = image_rgb.shape[:2]
    new_width = max(1, width // factor)
    new_height = max(1, height // factor)
    pil_image = Image.fromarray(image_rgb.astype(np.uint8), mode='RGB')
    resized = pil_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    return np.asarray(resized)
