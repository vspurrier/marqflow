type RGB = [number, number, number];

interface PhysicalSize {
  width: number;
  height: number;
  unit: string;
}

interface VeneerSwatch {
  veneer_id: string;
  name: string;
  color_rgb: RGB;
  sheet_width?: number;
  sheet_height?: number;
  sheet_count?: number;
  grain_direction?: string;
  notes?: string;
}

interface GridCandidate {
  candidate_id: string;
  label?: string;
  preset?: Record<string, number>;
  region_count: number;
  grid_row?: number;
  grid_col?: number;
  generation?: number;
  kept: boolean;
  selected_region_ids: number[];
  selection_revision: number;
  selected_at_ns?: number;
  preview_url: string;
  thumb_url?: string;
  svg_url?: string;
  hitmap_url?: string;
}

interface CandidateRegion {
  region_id: number;
  area: number;
  fill: RGB;
  bbox: [number, number, number, number];
  neighbors: number[];
}

interface CandidateDetail extends GridCandidate {
  size: {width: number; height: number};
  regions: CandidateRegion[];
}

interface RegionHitmap {
  width: number;
  height: number;
  labels: number[][];
}

interface DesignRegion {
  region_id: number;
  area_px: number;
  area_physical: number;
  bbox: [number, number, number, number];
  point_count: number;
  neighbors: number[];
  veneer_id: string;
  suggested_veneer_id: string;
  veneer_override_id?: string | null;
  locked: boolean;
  contour: Array<[number, number]>;
}

interface WorkspaceSummary {
  workspace_dir: string;
  source_image_path?: string;
  candidate_count: number;
  kept_count: number;
  grid_rows: number;
  grid_cols: number;
  active_candidate_id?: string | null;
  active_candidate?: GridCandidate | null;
  candidates: GridCandidate[];
  physical_size: PhysicalSize;
  veneer_palette: VeneerSwatch[];
  final_regions: DesignRegion[];
  design_summary?: Record<string, any>;
  cleanup_settings?: Record<string, any>;
  subject_settings?: Record<string, any>;
}

interface PackedSheet {
  veneer_id: string;
  sheet_width: number;
  sheet_height: number;
  available_sheet_count?: number;
  over_stock_capacity?: boolean;
  placement_valid?: boolean;
}
