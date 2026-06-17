"""Configuration objects for image preparation and segmentation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SuperpixelConfig:
    """Controls the coarse region base that the UI starts from."""

    target_segments: int = 32
    compactness: float = 20.0
    sigma: float = 1.0


@dataclass(frozen=True, slots=True)
class SegmentationConfig:
    """Full pipeline configuration for preparing a marquetry working image."""

    downscale_factor: int = 1
    max_working_edge: int = 384
    superpixels: SuperpixelConfig = field(default_factory=SuperpixelConfig)

    def validate(self) -> None:
        if self.downscale_factor < 1:
            raise ValueError('downscale_factor must be >= 1')
        if self.max_working_edge < 1:
            raise ValueError('max_working_edge must be >= 1')
        if self.superpixels.target_segments < 1:
            raise ValueError('target_segments must be >= 1')
        if self.superpixels.compactness <= 0:
            raise ValueError('compactness must be > 0')
        if self.superpixels.sigma < 0:
            raise ValueError('sigma must be >= 0')
