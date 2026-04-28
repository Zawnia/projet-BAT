import { Rng, hashSeed } from "./random";
import { speciesById } from "./species";
import { isGeneratedClip, isImportedClip } from "./clipGuards";
import { importedStoreManager } from "./importedStore";
import type { Clip, Detection, GeneratedClip, ScenarioProject, SensorDetectionRow, SpeciesTemplate } from "./types";

export const SENSOR_SAMPLE_KHZ = 200;
export const FFT_LENGTH = 512;
export const FFT_OVERLAP = 2;
export const SNR_MIN_DB = 19;
export const BIN_KHZ = SENSOR_SAMPLE_KHZ / FFT_LENGTH;
export const WINDOW_MS = (FFT_LENGTH / FFT_OVERLAP / (SENSOR_SAMPLE_KHZ * 1000)) * 1000;

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function khzToBin(khz: number): number {
  return Math.round(clamp(khz / BIN_KHZ, 0, 255));
}

export function durationMsToWindows(durationMs: number): number {
  return Math.max(1, Math.round(durationMs / WINDOW_MS));
}

export function createClipFromSpecies(species: SpeciesTemplate, trackId: string, startMs: number): GeneratedClip {
  const seed = hashSeed(`${species.id}:${trackId}:${startMs}:${Date.now()}`);
  const rng = new Rng(seed);
  const fmeKhz = rng.range(species.fmeRangeKhz[0], species.fmeRangeKhz[1]);
  const chirpDurationMs = rng.range(species.durationMs[0], species.durationMs[1]);
  const iciMeanMs = rng.range(species.iciMs[0], species.iciMs[1]);
  return {
    id: crypto.randomUUID(),
    kind: "sequence",
    trackId,
    speciesId: species.id,
    speciesName: species.commonName,
    individualId: `ind-${species.id}-${rng.integer(1000, 9999)}`,
    sequenceId: `seq-${rng.integer(100000, 999999)}`,
    startMs,
    durationMs: Math.max(iciMeanMs * 12, 2500),
    phase: "transit",
    fmeKhz,
    fiKhz: fmeKhz + rng.range(species.fiOffsetKhz[0], species.fiOffsetKhz[1]),
    ftKhz: Math.max(5, fmeKhz - rng.range(species.ftOffsetKhz[0], species.ftOffsetKhz[1])),
    chirpDurationMs,
    iciMeanMs,
    iciJitter: 0.18,
    fmeStdKhz: 0.35,
    snrMeanDb: 28,
    snrStdDb: 4,
    echo: {
      enabled: true,
      probability: 0.18,
      delayMinMs: 1,
      delayMaxMs: 10,
      snrLossDb: 7,
      fmeDeltaBins: 1
    },
    seed
  };
}

export function deriveDetectionsForClip(clip: Clip): Detection[] {
  if (isImportedClip(clip)) return deriveImportedDetections(clip);
  return clip.kind === "noise" ? deriveNoiseDetections(clip) : deriveSequenceDetections(clip);
}

export function deriveDetections(project: ScenarioProject): Detection[] {
  const detections = project.clips.flatMap(deriveDetectionsForClip);
  detections.sort((left, right) => left.timeMs - right.timeMs || left.sourceClipId.localeCompare(right.sourceClipId));
  return detections.map((detection, index) => ({ ...detection, detectionId: `det-${String(index + 1).padStart(6, "0")}` }));
}

export function duplicateClipWithHalfIciOffset(clip: Clip): Clip {
  if (isImportedClip(clip)) {
    return {
      ...clip,
      id: crypto.randomUUID(),
      startMs: Math.round(clip.startMs + clip.summary.iciMedianMs / 2)
    };
  }
  return {
    ...clip,
    id: crypto.randomUUID(),
    individualId: `${clip.individualId}-half`,
    sequenceId: `${clip.sequenceId}-half`,
    startMs: Math.round(clip.startMs + clip.iciMeanMs / 2),
    seed: hashSeed(`${clip.seed}:half:${clip.id}`)
  };
}

export function convertClipToNoise(clip: Clip): Clip {
  if (!isGeneratedClip(clip)) return clip;
  return {
    ...clip,
    id: crypto.randomUUID(),
    kind: "noise",
    sequenceId: `${clip.sequenceId}-noise`,
    durationMs: Math.min(clip.durationMs, Math.max(clip.iciMeanMs * 2, 500)),
    snrMeanDb: 20,
    snrStdDb: 1.5,
    echo: { ...clip.echo, enabled: false, probability: 0 },
    seed: hashSeed(`${clip.seed}:noise:${clip.id}`)
  };
}

function deriveSequenceDetections(clip: GeneratedClip): Detection[] {
  const rng = new Rng(clip.seed);
  const detections: Detection[] = [];
  let offsetMs = 0;
  let index = 0;
  while (offsetMs <= clip.durationMs) {
    const fmeKhz = clamp(rng.normal(clip.fmeKhz, clip.fmeStdKhz), 5, 99);
    const fiKhz = Math.max(fmeKhz, rng.normal(clip.fiKhz, clip.fmeStdKhz));
    const ftKhz = Math.min(fmeKhz, rng.normal(clip.ftKhz, clip.fmeStdKhz));
    const snrDb = Math.round(clamp(rng.normal(clip.snrMeanDb, clip.snrStdDb), SNR_MIN_DB, 40));
    const timeMs = Math.round(clip.startMs + offsetMs);
    const base = makeDetection(clip, `raw-${index}`, timeMs, fmeKhz, fiKhz, ftKhz, snrDb, false, false);
    detections.push(base);
    if (clip.echo.enabled && rng.next() < clip.echo.probability) {
      const deltaBins = rng.integer(-clip.echo.fmeDeltaBins, clip.echo.fmeDeltaBins);
      const echoFme = fmeKhz + deltaBins * BIN_KHZ;
      const delay = rng.range(clip.echo.delayMinMs, clip.echo.delayMaxMs);
      detections.push(
        makeDetection(
          clip,
          `echo-${index}`,
          Math.round(timeMs + delay),
          echoFme,
          fiKhz + deltaBins * BIN_KHZ,
          ftKhz + deltaBins * BIN_KHZ,
          Math.round(clamp(snrDb - clip.echo.snrLossDb + rng.normal(0, 1), SNR_MIN_DB, 40)),
          true,
          false
        )
      );
    }
    const ici = Math.max(4, rng.normal(clip.iciMeanMs, clip.iciMeanMs * clip.iciJitter));
    offsetMs += ici;
    index += 1;
  }
  return detections;
}

function deriveNoiseDetections(clip: GeneratedClip): Detection[] {
  const rng = new Rng(clip.seed);
  const count = rng.integer(1, 3);
  const low = Math.min(clip.fiKhz, clip.ftKhz, clip.fmeKhz);
  const high = Math.max(clip.fiKhz, clip.ftKhz, clip.fmeKhz);
  return Array.from({ length: count }, (_, index) => {
    const fmeKhz = clamp(rng.range(low, high), 5, 99);
    const duration = rng.range(1.2, 4);
    return makeDetection(
      clip,
      `noise-${index}`,
      Math.round(clip.startMs + rng.range(0, clip.durationMs)),
      fmeKhz,
      clamp(fmeKhz + rng.range(-1, 1), 5, 99),
      clamp(fmeKhz + rng.range(-1, 1), 5, 99),
      Math.round(clamp(rng.normal(clip.snrMeanDb, clip.snrStdDb), SNR_MIN_DB, 24)),
      false,
      true,
      duration
    );
  });
}

function makeDetection(
  clip: GeneratedClip,
  localId: string,
  timeMs: number,
  fmeKhz: number,
  fiKhz: number,
  ftKhz: number,
  snrDb: number,
  isEcho: boolean,
  isNoise: boolean,
  durationMs = clip.chirpDurationMs
): Detection {
  return {
    detectionId: `${clip.id}-${localId}`,
    timeMs,
    posFME: khzToBin(fmeKhz),
    posFI: khzToBin(fiKhz),
    posFT: khzToBin(ftKhz),
    posDUREE: durationMsToWindows(durationMs),
    snrDb,
    fmeKhz,
    fiKhz,
    ftKhz,
    individualId: clip.individualId,
    speciesName: clip.speciesName,
    sequenceId: clip.sequenceId,
    isEcho,
    isNoise,
    sourceClipId: clip.id
  };
}

function deriveImportedDetections(clip: Extract<Clip, { kind: "imported" }>): Detection[] {
  const store = importedStoreManager.get(clip.storeId);
  if (!store) return [];
  const offset = clip.startMs - clip.originalStartMs;
  return store.rows.slice(clip.rowStart, clip.rowEnd).map((row, index) =>
    detectionFromSensorRow(row, store.metadata.binKhz, Math.round(row.timeMs + offset), clip, index)
  );
}

export function detectionFromSensorRow(
  row: SensorDetectionRow,
  binKhz: number,
  timeMs: number,
  clip: Extract<Clip, { kind: "imported" }>,
  index: number
): Detection {
  return {
    detectionId: `${clip.id}-import-${index}`,
    timeMs,
    posFME: row.posFME,
    posFI: row.posFI,
    posFT: row.posFT,
    posDUREE: row.posDUREE,
    snrDb: row.snrDb,
    fmeKhz: row.posFME * binKhz,
    fiKhz: row.posFI * binKhz,
    ftKhz: row.posFT * binKhz,
    individualId: "imported",
    speciesName: clip.speciesName,
    sequenceId: clip.id,
    isEcho: false,
    isNoise: false,
    sourceClipId: clip.id
  };
}

export function pickTrackForSpecies(project: ScenarioProject, speciesId: string): string {
  const species = speciesById(speciesId);
  const center = (species.fmeRangeKhz[0] + species.fmeRangeKhz[1]) / 2;
  return project.tracks.find((track) => center >= track.minKhz && center <= track.maxKhz)?.id ?? project.tracks[0].id;
}
