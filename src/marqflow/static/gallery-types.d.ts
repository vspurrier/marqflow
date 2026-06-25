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

interface WorkspaceSummary {
  source: {
    original_width: number;
    original_height: number;
    working_width: number;
    working_height: number;
  };
  candidates: Array<{candidate_id: string; region_count: number}>;
  design: null | {veneers: Veneer[]};
  regions: Region[];
  validation: {valid: boolean; region_count?: number; unassigned_px?: number};
}
