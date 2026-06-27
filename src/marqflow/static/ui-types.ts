export type CanvasPoint = {x: number; y: number};

export type VertexDrag = {
  vertexId: number;
  start: CanvasPoint;
  current: CanvasPoint;
};

export type PendingVertexMove = {
  vertexId: number;
  sourcePoint: CanvasPoint;
  point: CanvasPoint;
  sourceKind: string | null;
};

