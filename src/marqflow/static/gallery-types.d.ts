interface Veneer {
  veneer_id: string;
  name: string;
  color_rgb: [number, number, number];
  sheet_width: number;
  sheet_height: number;
  sheet_count: number;
  grain_direction: string;
  notes: string;
}

interface DetailZone {
  zone_id: number;
  name: string;
  bbox: [number, number, number, number];
  detail_multiplier: number;
}

interface Region {
  region_id: number;
  veneer_id: string;
  suggested_veneer_id: string;
  color_rgb: [number, number, number];
  area_physical: number;
  warnings: string[];
}

interface MergeSuggestion {
  region_id: number;
  target_region_id: number;
  reason: string;
  same_veneer: boolean;
  area_physical: number;
}

interface Candidate {
  candidate_id: string;
  preview_path: string;
  target_regions: number;
  compactness: number;
  region_count: number;
}

interface WorkspaceSummary {
  workspace_dir: string;
  source: {
    original_width: number;
    original_height: number;
    working_width: number;
    working_height: number;
  };
  candidates: Candidate[];
  design: null | {
    veneers: Veneer[];
    physical_size: {width: number; height: number; unit: string};
    detail_zones: DetailZone[];
  };
  regions: Region[];
  merge_suggestions: MergeSuggestion[];
  validation: {valid: boolean; region_count?: number; unassigned_px?: number};
  boundaries: {
    boundary_count: number;
    boundaries: Array<{
      region_a: number;
      region_b: number;
      edge_px: number;
      edge_length_physical: number;
    }>;
  };
  applied_merge_count?: number;
  applied_detail_split_count?: number;
  repaired_region_count?: number;
  smoothed_pixel_count?: number;
}

interface DesignHitmap {
  width: number;
  height: number;
  labels: number[][];
}
