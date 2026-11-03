export interface VisualizationIntent {
  format: 'xyg.intent/v1';
  name: string;
  result: string;
  kind: 'result-graph' | 'chart' | 'geospatial' | 'temporal';
  filters: Array<{ column: string; operator: "equals" | "contains"; value: string }>;
  base?: string;
  intent?: 'graph' | 'table' | 'bar-chart' | 'parallel-coordinates' | 'embedding-coordinates';
  graph?: { layout: 'cose' | 'force' | 'circle' | 'grid'; iterations: number };
  chart?: { mark: ChartMark; x: string; y?: string; color?: string };
  geospatial?: { longitude: string; latitude: string; targetLongitude?: string; targetLatitude?: string; crs: 4326; projection: 3857; longitudeCenter: number; latitudeCenter: number; zoom: number };
  temporal?: { timestamp: string; value: string; series?: string; timezone: 'UTC'; mark: 'line' | 'bar' | 'scatter' };
}
export type ChartMark = 'bar' | 'scatter' | 'line' | 'histogram';

export function isVisualizationIntent(value: unknown): value is VisualizationIntent;
export function createGraphForgeIntent(input: {name: string;result: string;filters?: VisualizationIntent["filters"];base?: string;intent?: VisualizationIntent["intent"]}): VisualizationIntent;
