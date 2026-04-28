export type Phase = "transit" | "chasse" | "approche" | "feeding_buzz";
export type ClipKind = "sequence" | "noise" | "imported";
export type ActivityProfile = "uniform" | "dusk_dawn";

export interface SpeciesTemplate {
  id: string;
  commonName: string;
  latinName: string;
  color: string;
  fmeRangeKhz: [number, number];
  fiOffsetKhz: [number, number];
  ftOffsetKhz: [number, number];
  durationMs: [number, number];
  iciMs: [number, number];
}

export interface EchoSettings {
  enabled: boolean;
  probability: number;
  delayMinMs: number;
  delayMaxMs: number;
  snrLossDb: number;
  fmeDeltaBins: number;
}

export interface GeneratedClip {
  id: string;
  kind: "sequence" | "noise";
  trackId: string;
  speciesId: string;
  speciesName: string;
  individualId: string;
  sequenceId: string;
  startMs: number;
  durationMs: number;
  phase: Phase;
  fmeKhz: number;
  fiKhz: number;
  ftKhz: number;
  chirpDurationMs: number;
  iciMeanMs: number;
  iciJitter: number;
  fmeStdKhz: number;
  snrMeanDb: number;
  snrStdDb: number;
  echo: EchoSettings;
  seed: number;
}

export interface ImportedClip {
  id: string;
  kind: "imported";
  trackId: string;
  speciesId: string;
  speciesName: string;
  startMs: number;
  durationMs: number;
  storeId: string;
  rowStart: number;
  rowEnd: number;
  originalStartMs: number;
  summary: ImportedClipSummary;
}

export type Clip = GeneratedClip | ImportedClip;

export interface ImportedClipSummary {
  filename: string;
  firstTimeMs: number;
  lastTimeMs: number;
  fmeMedianKhz: number;
  fmeStdKhz: number;
  iciMedianMs: number;
  snrMedianDb: number;
  nDetections: number;
  inferredSpecies: string | null;
}

export interface Track {
  id: string;
  name: string;
  minKhz: number;
  maxKhz: number;
  clipIds: string[];
}

export interface GenerationSettings {
  durationHours: number;
  densityPerHour: number;
  noiseLevel: number;
  echoProbability: number;
  activityProfile: ActivityProfile;
  speciesMix: Record<string, number>;
}

export interface ScenarioProject {
  schemaVersion: 1;
  id: string;
  name: string;
  durationMs: number;
  tracks: Track[];
  clips: Clip[];
  generation: GenerationSettings;
  updatedAt: string;
}

export interface SensorMetadata {
  freqKhzEnreg: number;
  lenfft: number;
  overlap: number;
  snrMin: number;
  binKhz: number;
}

export interface SensorDetectionRow {
  timeMs: number;
  posFME: number;
  posFI: number;
  posFT: number;
  posDUREE: number;
  snrDb: number;
}

export interface ImportedDetectionStore {
  id: string;
  filename: string;
  metadata: SensorMetadata;
  rows: SensorDetectionRow[];
  importedAt: number;
}

export interface ScenarioProjectSnapshot extends ScenarioProject {
  importedStores?: ImportedDetectionStore[];
}

export interface Detection {
  detectionId: string;
  timeMs: number;
  posFME: number;
  posFI: number;
  posFT: number;
  posDUREE: number;
  snrDb: number;
  fmeKhz: number;
  fiKhz: number;
  ftKhz: number;
  individualId: string;
  speciesName: string;
  sequenceId: string;
  isEcho: boolean;
  isNoise: boolean;
  sourceClipId: string;
}

export interface TimelineView {
  scrollMs: number;
  pxPerMs: number;
  selectedClipIds: string[];
}
