interface Veneer {
  veneer_id: string;
  name: string;
  color_rgb: [number, number, number];
  sheet_width: number;
  sheet_height: number;
  sheet_count: number;
  grain_direction: string;
  texture_url: string;
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

interface ExportArtifact {
  kind: string;
  path: string;
  tolerance: number;
  coverage_valid: boolean;
  topology_vertex_count: number;
  topology_edge_count: number;
  created_at: string;
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
    subject_mask_path: string | null;
    vector_exports: ExportArtifact[];
  };
  subject_mask: {subject_px: number; background_px: number; unknown_px: number};
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
      path_count: number;
      paths: number[][][];
      physical_paths: number[][][];
      vertex_count: number;
      simplified_vertex_count: number;
      simplified_vertex_reduction: number;
      simplified_paths: number[][][];
      simplified_physical_paths: number[][][];
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
  subject_mask: number[][];
}

interface PackSheet {
  veneer_id: string;
  piece_count: number;
  placed_piece_count: number;
  sheet_width: number;
  sheet_height: number;
  available_sheet_count: number;
  sheet_count_used: number;
  recommended_sheet_count: number;
  stock_shortfall_count: number;
  sheet_area: number;
  material_area_available: number;
  material_area_used: number;
  total_piece_area: number;
  total_bounding_box_area: number;
  material_utilization: number;
  over_stock_capacity: boolean;
}

interface PackManifest {
  packing_backend: string;
  sheets: PackSheet[];
}

interface CleanupReport {
  readiness_score: number;
  readiness: string;
  region_count: number;
  locked_region_count: number;
  warning_counts: Record<string, number>;
  small_or_thin_region_ids: number[];
  merge_suggestion_count: number;
  top_merge_suggestions: MergeSuggestion[];
  boundary_count: number;
  jagged_boundary_count: number;
  top_jagged_boundaries: Array<{
    region_a: number;
    region_b: number;
    edge_length_physical: number;
    vertex_count: number;
    simplified_vertex_count: number;
    simplified_vertex_reduction: number;
  }>;
  veneer_region_counts: Record<string, number>;
  subject_mask: {subject_px: number; background_px: number; unknown_px: number};
  vector_exports: ExportArtifact[];
  topology: {vertex_count: number; edge_count: number};
  coverage: {
    valid: boolean;
    polygon_count: number;
    skipped_region_ids: number[];
    invalid_edge_count: number;
    invalid_edge_length: number;
  };
  valid_partition: {valid: boolean; region_count?: number; unassigned_px?: number};
}
