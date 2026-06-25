"""Domain objects for the marquetry-first rewrite."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class PhysicalSize:
    """Real-world size of the finished marquetry piece."""

    width: float
    height: float
    unit: str = 'in'

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PhysicalSize:
        return cls(
            width=float(data['width']),
            height=float(data['height']),
            unit=str(data.get('unit', 'in')),
        )

    def pixels_per_unit(self, image_size: tuple[int, int]) -> tuple[float, float]:
        width_px, height_px = image_size
        return width_px / max(self.width, 1e-9), height_px / max(self.height, 1e-9)


@dataclass(frozen=True, slots=True)
class SourceImage:
    """Normalized source image metadata."""

    path: str
    original_width: int
    original_height: int
    working_width: int
    working_height: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceImage:
        return cls(
            path=str(data['path']),
            original_width=int(data['original_width']),
            original_height=int(data['original_height']),
            working_width=int(data['working_width']),
            working_height=int(data['working_height']),
        )


@dataclass(frozen=True, slots=True)
class Veneer:
    """A material swatch available for the final design."""

    veneer_id: str
    name: str
    color_rgb: tuple[int, int, int]
    sheet_width: float = 0.0
    sheet_height: float = 0.0
    sheet_count: int = 0
    grain_direction: str = ''
    notes: str = ''

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload['color_rgb'] = list(self.color_rgb)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Veneer:
        return cls(
            veneer_id=str(data['veneer_id']),
            name=str(data.get('name') or data['veneer_id']),
            color_rgb=tuple(int(value) for value in data['color_rgb']),
            sheet_width=float(data.get('sheet_width', 0.0) or 0.0),
            sheet_height=float(data.get('sheet_height', 0.0) or 0.0),
            sheet_count=max(0, int(data.get('sheet_count', 0) or 0)),
            grain_direction=str(data.get('grain_direction', '')),
            notes=str(data.get('notes', '')),
        )


@dataclass(frozen=True, slots=True)
class Candidate:
    """A generated source partition that can seed a design."""

    candidate_id: str
    labels_path: str
    preview_path: str
    target_regions: int
    compactness: float
    region_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Candidate:
        return cls(
            candidate_id=str(data['candidate_id']),
            labels_path=str(data['labels_path']),
            preview_path=str(data['preview_path']),
            target_regions=int(data['target_regions']),
            compactness=float(data['compactness']),
            region_count=int(data['region_count']),
        )


@dataclass(frozen=True, slots=True)
class DetailZone:
    """A user-selected area where generated candidates should preserve more detail."""

    zone_id: int
    name: str
    bbox: tuple[int, int, int, int]
    detail_multiplier: float = 2.0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload['bbox'] = list(self.bbox)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DetailZone:
        return cls(
            zone_id=int(data['zone_id']),
            name=str(data.get('name') or f'Zone {data["zone_id"]}'),
            bbox=tuple(int(value) for value in data['bbox']),
            detail_multiplier=max(1.0, float(data.get('detail_multiplier', 2.0))),
        )


@dataclass(slots=True)
class Region:
    """A single physical cut piece in the current design partition."""

    region_id: int
    veneer_id: str
    suggested_veneer_id: str
    color_rgb: tuple[int, int, int]
    area_px: int
    area_physical: float
    bbox: tuple[int, int, int, int]
    contour: tuple[tuple[float, float], ...]
    neighbors: tuple[int, ...] = ()
    locked: bool = False
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload['color_rgb'] = list(self.color_rgb)
        payload['contour'] = [list(point) for point in self.contour]
        payload['neighbors'] = list(self.neighbors)
        payload['warnings'] = list(self.warnings)
        return payload


@dataclass(frozen=True, slots=True)
class EditOperation:
    """A deterministic user edit applied to a design."""

    op_id: int
    kind: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EditOperation:
        return cls(op_id=int(data['op_id']), kind=str(data['kind']), payload=dict(data['payload']))


@dataclass(slots=True)
class MarquetryDesign:
    """The durable product object: a measured, veneer-assigned partition."""

    source_candidate_id: str
    labels_path: str
    physical_size: PhysicalSize
    veneers: list[Veneer]
    veneer_assignments: dict[int, str] = field(default_factory=dict)
    locked_region_ids: set[int] = field(default_factory=set)
    detail_zones: list[DetailZone] = field(default_factory=list)
    edit_history: list[EditOperation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            'source_candidate_id': self.source_candidate_id,
            'labels_path': self.labels_path,
            'physical_size': self.physical_size.to_dict(),
            'veneers': [veneer.to_dict() for veneer in self.veneers],
            'veneer_assignments': {
                str(region_id): veneer_id
                for region_id, veneer_id in sorted(self.veneer_assignments.items())
            },
            'locked_region_ids': sorted(self.locked_region_ids),
            'detail_zones': [zone.to_dict() for zone in self.detail_zones],
            'edit_history': [edit.to_dict() for edit in self.edit_history],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MarquetryDesign:
        return cls(
            source_candidate_id=str(data['source_candidate_id']),
            labels_path=str(data['labels_path']),
            physical_size=PhysicalSize.from_dict(data['physical_size']),
            veneers=[Veneer.from_dict(item) for item in data.get('veneers', [])],
            veneer_assignments={
                int(region_id): str(veneer_id)
                for region_id, veneer_id in data.get('veneer_assignments', {}).items()
            },
            locked_region_ids={int(region_id) for region_id in data.get('locked_region_ids', [])},
            detail_zones=[
                DetailZone.from_dict(item) for item in data.get('detail_zones', [])
            ],
            edit_history=[EditOperation.from_dict(item) for item in data.get('edit_history', [])],
        )


def default_veneers() -> list[Veneer]:
    """Small default palette chosen to be useful for early pet-portrait tests."""

    return [
        Veneer('maple', 'Maple', (221, 204, 164)),
        Veneer('cherry', 'Cherry', (166, 94, 58)),
        Veneer('walnut', 'Walnut', (82, 55, 38)),
        Veneer('black-dyed', 'Black dyed', (30, 28, 25)),
        Veneer('blue-dyed', 'Blue dyed', (70, 97, 128)),
    ]
