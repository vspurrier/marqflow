"""Workspace persistence for the marquetry-first rewrite."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps
from skimage.segmentation import slic

from .geometry import (
    build_regions,
    design_to_svg,
    normalize_labels,
    partition_validation,
    preview_image,
)
from .models import (
    Candidate,
    EditOperation,
    MarquetryDesign,
    PhysicalSize,
    SourceImage,
    Veneer,
    default_veneers,
)

MANIFEST = 'workspace.json'
SOURCE_IMAGE = 'source.png'
DESIGN_LABELS = 'design-labels.npy'


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=False, dir=path.parent) as tmp:
        json.dump(payload, tmp, indent=2, sort_keys=True)
        tmp.write('\n')
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


def _load_image(path: Path, max_edge: int) -> tuple[Image.Image, SourceImage]:
    original = ImageOps.exif_transpose(Image.open(path)).convert('RGB')
    working = original.copy()
    working.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    metadata = SourceImage(
        path=SOURCE_IMAGE,
        original_width=original.width,
        original_height=original.height,
        working_width=working.width,
        working_height=working.height,
    )
    return working, metadata


@dataclass(slots=True)
class MarquetryWorkspace:
    """Owns source image, generated candidates, and one final marquetry design."""

    workspace_dir: Path
    source: SourceImage
    candidates: list[Candidate] = field(default_factory=list)
    design: MarquetryDesign | None = None

    @property
    def source_path(self) -> Path:
        return self.workspace_dir / self.source.path

    @classmethod
    def create(
        cls,
        image_path: str | Path,
        workspace_dir: str | Path,
        max_edge: int = 768,
    ) -> MarquetryWorkspace:
        workspace_path = Path(workspace_dir)
        workspace_path.mkdir(parents=True, exist_ok=True)
        working, source = _load_image(Path(image_path), max_edge=max_edge)
        working.save(workspace_path / SOURCE_IMAGE)
        workspace = cls(workspace_dir=workspace_path, source=source)
        workspace.save()
        return workspace

    @classmethod
    def load(cls, workspace_dir: str | Path) -> MarquetryWorkspace:
        workspace_path = Path(workspace_dir)
        manifest = json.loads((workspace_path / MANIFEST).read_text(encoding='utf-8'))
        design_data = manifest.get('design')
        return cls(
            workspace_dir=workspace_path,
            source=SourceImage.from_dict(manifest['source']),
            candidates=[Candidate.from_dict(item) for item in manifest.get('candidates', [])],
            design=MarquetryDesign.from_dict(design_data) if design_data else None,
        )

    def save(self) -> None:
        _atomic_json(
            self.workspace_dir / MANIFEST,
            {
                'source': self.source.to_dict(),
                'candidates': [candidate.to_dict() for candidate in self.candidates],
                'design': self.design.to_dict() if self.design else None,
            },
        )

    def source_array(self) -> np.ndarray:
        return np.asarray(Image.open(self.source_path).convert('RGB'))

    def _candidate_by_id(self, candidate_id: str) -> Candidate:
        for candidate in self.candidates:
            if candidate.candidate_id == candidate_id:
                return candidate
        raise ValueError(f'candidate not found: {candidate_id}')

    def candidate_labels(self, candidate_id: str) -> np.ndarray:
        candidate = self._candidate_by_id(candidate_id)
        return np.load(self.workspace_dir / candidate.labels_path)

    def design_labels(self) -> np.ndarray:
        if self.design is None:
            raise ValueError('create a design from a candidate first')
        return np.load(self.workspace_dir / self.design.labels_path)

    def generate_candidate(
        self,
        target_regions: int = 80,
        compactness: float = 18.0,
    ) -> Candidate:
        """Generate one SLIC candidate partition."""

        image = self.source_array()
        labels = slic(
            image,
            n_segments=max(2, int(target_regions)),
            compactness=float(compactness),
            sigma=1.0,
            start_label=1,
            channel_axis=-1,
        )
        labels = normalize_labels(labels)
        candidate_id = f'candidate-{len(self.candidates) + 1}'
        candidate_dir = self.workspace_dir / 'candidates' / candidate_id
        candidate_dir.mkdir(parents=True, exist_ok=True)
        labels_path = Path('candidates') / candidate_id / 'labels.npy'
        preview_path = Path('candidates') / candidate_id / 'preview.png'
        np.save(self.workspace_dir / labels_path, labels)
        preview_image(image, labels).save(self.workspace_dir / preview_path)
        candidate = Candidate(
            candidate_id=candidate_id,
            labels_path=str(labels_path),
            preview_path=str(preview_path),
            target_regions=int(target_regions),
            compactness=float(compactness),
            region_count=int(len(np.unique(labels))),
        )
        self.candidates.append(candidate)
        self.save()
        return candidate

    def create_design(
        self,
        candidate_id: str,
        physical_size: PhysicalSize,
        veneers: list[Veneer] | None = None,
    ) -> MarquetryDesign:
        """Seed the durable design from a candidate partition."""

        labels = self.candidate_labels(candidate_id)
        np.save(self.workspace_dir / DESIGN_LABELS, labels)
        self.design = MarquetryDesign(
            source_candidate_id=candidate_id,
            labels_path=DESIGN_LABELS,
            physical_size=physical_size,
            veneers=veneers or default_veneers(),
        )
        self._auto_assign_veneers()
        self.save()
        return self.design

    def _auto_assign_veneers(self) -> None:
        if self.design is None:
            return
        image = self.source_array()
        labels = self.design_labels()
        regions = build_regions(image, labels, self.design)
        self.design.veneer_assignments = {
            region.region_id: region.suggested_veneer_id for region in regions
        }

    def assign_veneer(self, region_id: int, veneer_id: str) -> None:
        if self.design is None:
            raise ValueError('create a design first')
        if veneer_id not in {veneer.veneer_id for veneer in self.design.veneers}:
            raise ValueError(f'unknown veneer: {veneer_id}')
        self.design.veneer_assignments[int(region_id)] = veneer_id
        self.design.edit_history.append(
            EditOperation(
                op_id=len(self.design.edit_history) + 1,
                kind='assign_veneer',
                payload={'region_id': int(region_id), 'veneer_id': veneer_id},
            )
        )
        self.save()

    def regions(self) -> list[dict[str, Any]]:
        if self.design is None:
            return []
        return [
            region.to_dict()
            for region in build_regions(self.source_array(), self.design_labels(), self.design)
        ]

    def validation(self) -> dict[str, Any]:
        if self.design is None:
            return {'valid': False, 'reason': 'missing design'}
        return partition_validation(self.design_labels())

    def export_svg(self, output_path: str | Path) -> Path:
        if self.design is None:
            raise ValueError('create a design first')
        validation = self.validation()
        if not validation['valid']:
            raise ValueError(f'invalid partition: {validation}')
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        svg = design_to_svg(
            build_regions(self.source_array(), self.design_labels(), self.design),
            self.design.physical_size,
            (self.source.working_width, self.source.working_height),
        )
        path.write_text(svg, encoding='utf-8')
        return path

    def pack(self, output_dir: str | Path) -> dict[str, Any]:
        """Write a traceable, simple packing manifest grouped by veneer."""

        if self.design is None:
            raise ValueError('create a design first')
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        regions = build_regions(self.source_array(), self.design_labels(), self.design)
        by_veneer: dict[str, list[dict[str, Any]]] = {}
        for region in regions:
            by_veneer.setdefault(region.veneer_id, []).append(region.to_dict())
        sheets = []
        for veneer in self.design.veneers:
            pieces = by_veneer.get(veneer.veneer_id, [])
            if not pieces:
                continue
            sheet_count_used = 1
            sheets.append(
                {
                    'veneer_id': veneer.veneer_id,
                    'piece_count': len(pieces),
                    'sheet_width': veneer.sheet_width or self.design.physical_size.width,
                    'sheet_height': veneer.sheet_height or self.design.physical_size.height,
                    'available_sheet_count': veneer.sheet_count,
                    'sheet_count_used': sheet_count_used,
                    'over_stock_capacity': bool(
                        veneer.sheet_count and sheet_count_used > veneer.sheet_count
                    ),
                    'pieces': pieces,
                }
            )
        manifest = {'packing_backend': 'simple-grouped-manifest', 'sheets': sheets}
        (output_path / 'pack.json').write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + '\n',
            encoding='utf-8',
        )
        self.export_svg(output_path / 'design.svg')
        return manifest

    def summary(self) -> dict[str, Any]:
        return {
            'workspace_dir': str(self.workspace_dir),
            'source': self.source.to_dict(),
            'candidates': [candidate.to_dict() for candidate in self.candidates],
            'design': self.design.to_dict() if self.design else None,
            'regions': self.regions(),
            'validation': self.validation(),
        }

    def copy_to(self, output_dir: str | Path) -> None:
        """Copy the whole workspace for debugging or fixtures."""

        output_path = Path(output_dir)
        if output_path.exists():
            shutil.rmtree(output_path)
        shutil.copytree(self.workspace_dir, output_path)
