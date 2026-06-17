"""Raster image loading and downscaling helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageOps


def load_rgb_image(path: str | Path) -> np.ndarray:
    """Load an image as an RGB numpy array."""

    image = ImageOps.exif_transpose(Image.open(path)).convert('RGB')
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


def resize_to_max_edge(image_rgb: np.ndarray, max_edge: int) -> np.ndarray:
    """Resize an image so its longest edge is at most ``max_edge`` pixels."""

    if max_edge < 1:
        raise ValueError('max_edge must be >= 1')

    height, width = image_rgb.shape[:2]
    longest_edge = max(height, width)
    if longest_edge <= max_edge:
        return image_rgb

    scale = max_edge / float(longest_edge)
    new_width = max(1, int(round(width * scale)))
    new_height = max(1, int(round(height * scale)))
    pil_image = Image.fromarray(image_rgb.astype(np.uint8), mode='RGB')
    resized = pil_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    return np.asarray(resized)
