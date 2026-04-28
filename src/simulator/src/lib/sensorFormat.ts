import { BIN_KHZ, FFT_LENGTH, FFT_OVERLAP, SENSOR_SAMPLE_KHZ, SNR_MIN_DB } from "./detection";
import { importedStoreManager } from "./importedStore";
import { DEFAULT_TRACKS } from "./species";
import type {
  ImportedClip,
  ImportedClipSummary,
  ImportedDetectionStore,
  SensorDetectionRow,
  SensorMetadata,
  Track
} from "./types";

export interface ParsedSensorFile {
  metadata: SensorMetadata;
  rows: SensorDetectionRow[];
}

export interface ImportedSensorResult {
  store: ImportedDetectionStore;
  clips: ImportedClip[];
}

export interface ImportOptions {
  filename: string;
  sequenceGapMs?: number;
  tracks?: Track[];
}

export function parseSensorTxt(text: string): ParsedSensorFile {
  const lines = text.replace(/\r/g, "").split("\n");
  if (lines[0]?.trim() !== "DETECTDATA") throw new Error("En-tete DETECTDATA introuvable");
  const freqKhzEnreg = parseNumberMetadata(lines, "FREQ_KHZ_ENREG");
  const lenfft = parseNumberMetadata(lines, "LENFFT");
  const overlap = parseNumberMetadata(lines, "OVERLAP");
  const snrMin = parseNumberMetadata(lines, "SNRMIN");
  const startIndex = lines.findIndex((line) => line.trim() === "DATAASCII");
  if (startIndex === -1) throw new Error("Bloc DATAASCII introuvable");

  const rows: SensorDetectionRow[] = [];
  for (const line of lines.slice(startIndex + 1)) {
    const parts = line.trim().split(/\s+/);
    if (parts.length !== 6) continue;
    const values = parts.map(Number);
    if (!values.every((value) => Number.isInteger(value) && value >= 0)) continue;
    rows.push({
      timeMs: values[0],
      posFME: values[1],
      posFI: values[2],
      posFT: values[3],
      posDUREE: values[4],
      snrDb: values[5]
    });
  }
  if (rows.length === 0) throw new Error("Aucune ligne de donnees exploitable");
  rows.sort((left, right) => left.timeMs - right.timeMs);
  return {
    metadata: {
      freqKhzEnreg,
      lenfft,
      overlap,
      snrMin,
      binKhz: freqKhzEnreg / lenfft
    },
    rows
  };
}

export function importSensorTxtAsClips(text: string, options: ImportOptions): ImportedSensorResult {
  const parsed = parseSensorTxt(text);
  const store: ImportedDetectionStore = {
    id: crypto.randomUUID(),
    filename: options.filename,
    metadata: parsed.metadata,
    rows: parsed.rows,
    importedAt: Date.now()
  };
  const segments = segmentRows(parsed.rows, options.sequenceGapMs ?? 100);
  const tracks = options.tracks?.length ? options.tracks : DEFAULT_TRACKS;
  const clips = segments.map(([rowStart, rowEnd], index) => {
    const summary = summarizeRows(store, rowStart, rowEnd);
    return {
      id: crypto.randomUUID(),
      kind: "imported" as const,
      trackId: pickTrackForSummary(tracks, summary),
      speciesId: "imported",
      speciesName: summary.inferredSpecies ?? "Import capteur",
      startMs: summary.firstTimeMs,
      durationMs: Math.max(1, summary.lastTimeMs - summary.firstTimeMs),
      storeId: store.id,
      rowStart,
      rowEnd,
      originalStartMs: summary.firstTimeMs,
      summary: {
        ...summary,
        inferredSpecies: summary.inferredSpecies ?? `Sequence importee ${index + 1}`
      }
    };
  });
  importedStoreManager.add(store);
  return { store, clips };
}

export function segmentRows(rows: SensorDetectionRow[], sequenceGapMs: number): [number, number][] {
  if (rows.length === 0) return [];
  const segments: [number, number][] = [];
  let start = 0;
  for (let index = 1; index < rows.length; index += 1) {
    if (rows[index].timeMs - rows[index - 1].timeMs >= sequenceGapMs) {
      segments.push([start, index]);
      start = index;
    }
  }
  segments.push([start, rows.length]);
  return segments;
}

export function inferSpeciesFromFme(fmeKhz: number): string | null {
  if (fmeKhz >= 36 && fmeKhz <= 39) return "Pipistrelle de Kuhl";
  if (fmeKhz >= 42 && fmeKhz <= 50) return "Pipistrelle commune";
  if (fmeKhz >= 52 && fmeKhz <= 58) return "Pipistrelle pygmee";
  if (fmeKhz >= 24 && fmeKhz <= 30) return "Serotine commune";
  if (fmeKhz >= 18 && fmeKhz <= 26) return "Noctule";
  if (fmeKhz >= 10 && fmeKhz <= 16) return "Molosse de Cestoni";
  return null;
}

export function sensorRowToText(row: SensorDetectionRow): string {
  return [row.timeMs, row.posFME, row.posFI, row.posFT, row.posDUREE, row.snrDb].join(" ");
}

export function sensorHeader(count: number): string {
  return [
    "DETECTDATA",
    `FREQ_KHZ_ENREG ${SENSOR_SAMPLE_KHZ}`,
    `LENFFT ${FFT_LENGTH}`,
    `OVERLAP ${FFT_OVERLAP}`,
    `SNRMIN ${SNR_MIN_DB}`,
    `detectData_nbsig ${count}`,
    `nbsig_detect ${count}`,
    "temps_ms_fin_prec 0",
    "RAW-ASCII 1",
    "time_ms posFME posFI posFT posDUREE SNRdB",
    "raw: uint32 uint8 uint8 uint8 uint8 uint8",
    "",
    "DATAASCII"
  ].join("\r\n");
}

export function summarizeRows(store: ImportedDetectionStore, rowStart: number, rowEnd: number): ImportedClipSummary {
  const rows = store.rows.slice(rowStart, rowEnd);
  const fme = rows.map((row) => row.posFME * store.metadata.binKhz);
  const snr = rows.map((row) => row.snrDb);
  const ici = rows.slice(1).map((row, index) => row.timeMs - rows[index].timeMs);
  const fmeMedianKhz = median(fme);
  return {
    filename: store.filename,
    firstTimeMs: rows[0].timeMs,
    lastTimeMs: rows[rows.length - 1].timeMs,
    fmeMedianKhz,
    fmeStdKhz: std(fme),
    iciMedianMs: ici.length ? median(ici) : 0,
    snrMedianDb: median(snr),
    nDetections: rows.length,
    inferredSpecies: inferSpeciesFromFme(fmeMedianKhz)
  };
}

function parseNumberMetadata(lines: string[], key: string): number {
  const line = lines.find((item) => item.trim().startsWith(key));
  if (!line) throw new Error(`Metadonnee manquante: ${key}`);
  const value = Number(line.trim().split(/\s+/)[1]);
  if (!Number.isFinite(value) || value <= 0) throw new Error(`Valeur invalide pour ${key}`);
  return value;
}

function pickTrackForSummary(tracks: Track[], summary: ImportedClipSummary): string {
  const fme = summary.fmeMedianKhz;
  return tracks.find((track) => fme >= track.minKhz && fme <= track.maxKhz)?.id ?? tracks[0].id;
}

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function std(values: number[]): number {
  if (values.length < 2) return 0;
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (values.length - 1);
  return Math.sqrt(variance);
}

export function defaultSensorMetadata(): SensorMetadata {
  return {
    freqKhzEnreg: SENSOR_SAMPLE_KHZ,
    lenfft: FFT_LENGTH,
    overlap: FFT_OVERLAP,
    snrMin: SNR_MIN_DB,
    binKhz: BIN_KHZ
  };
}
