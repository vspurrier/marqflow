interface Veneer {
  veneer_id: string;
  name: string;
  color_rgb: [number, number, number];
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
  };
  regions: Region[];
  merge_suggestions: MergeSuggestion[];
  validation: {valid: boolean; region_count?: number; unassigned_px?: number};
}
