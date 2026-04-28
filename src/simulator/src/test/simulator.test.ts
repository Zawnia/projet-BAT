import { describe, expect, it } from "vitest";
import {
  convertClipToNoise,
  createClipFromSpecies,
  deriveDetections,
  deriveDetectionsForClip,
  duplicateClipWithHalfIciOffset,
  durationMsToWindows,
  khzToBin
} from "../lib/detection";
import { exportGroundTruthCsv, exportSensorTxt } from "../lib/export";
import { isGeneratedClip } from "../lib/clipGuards";
import { importedStoreManager } from "../lib/importedStore";
import { importSensorTxtAsClips, inferSpeciesFromFme, parseSensorTxt, segmentRows } from "../lib/sensorFormat";
import { stripImportedStores } from "../lib/storage";
import { createEmptyProject, DEFAULT_GENERATION, SPECIES_TEMPLATES } from "../lib/species";
import type { ScenarioProject } from "../lib/types";

const SENSOR_SAMPLE = [
  "DETECTDATA",
  "FREQ_KHZ_ENREG 200",
  "LENFFT 512",
  "OVERLAP 2",
  "SNRMIN 19",
  "detectData_nbsig 4",
  "nbsig_detect 4",
  "temps_ms_fin_prec 0",
  "RAW-ASCII 1",
  "time_ms posFME posFI posFT posDUREE SNRdB",
  "raw: uint32 uint8 uint8 uint8 uint8 uint8",
  "",
  "DATAASCII",
  "1000 97 100 94 6 25",
  "1080 98 101 95 6 26",
  "1250 136 140 132 5 24",
  "1300 137 141 133 5 23"
].join("\r\n");

function projectWithClips(): ScenarioProject {
  const project = createEmptyProject();
  const species = SPECIES_TEMPLATES[1];
  const first = {
    ...createClipFromSpecies(species, project.tracks[2].id, 1000),
    id: "clip-a",
    seed: 101,
    durationMs: 500,
    iciMeanMs: 100,
    echo: { enabled: false, probability: 0, delayMinMs: 1, delayMaxMs: 10, snrLossDb: 7, fmeDeltaBins: 1 }
  };
  const second = {
    ...createClipFromSpecies(species, project.tracks[2].id, 250),
    id: "clip-b",
    seed: 202,
    durationMs: 500,
    iciMeanMs: 100,
    echo: { enabled: false, probability: 0, delayMinMs: 1, delayMaxMs: 10, snrLossDb: 7, fmeDeltaBins: 1 }
  };
  return {
    ...project,
    clips: [first, second],
    tracks: project.tracks.map((track) =>
      track.id === project.tracks[2].id ? { ...track, clipIds: [first.id, second.id] } : track
    )
  };
}

describe("sensor conversions", () => {
  it("converts kHz to FFT bins and clamps to uint8 range", () => {
    expect(khzToBin(0)).toBe(0);
    expect(khzToBin(45)).toBe(115);
    expect(khzToBin(200)).toBe(255);
  });

  it("converts duration to 1.28 ms FFT windows", () => {
    expect(durationMsToWindows(0.2)).toBe(1);
    expect(durationMsToWindows(1.28)).toBe(1);
    expect(durationMsToWindows(6.4)).toBe(5);
  });
});

describe("defaults", () => {
  it("starts with Kuhl at 75 percent, pygmy at 25 percent and other species at zero", () => {
    expect(DEFAULT_GENERATION.speciesMix["pip-kuhl"]).toBe(0.75);
    expect(DEFAULT_GENERATION.speciesMix["pip-pygmy"]).toBe(0.25);
    expect(DEFAULT_GENERATION.speciesMix["pip-common"]).toBe(0);
    expect(DEFAULT_GENERATION.speciesMix.serotine).toBe(0);
    expect(DEFAULT_GENERATION.speciesMix.molosse).toBe(0);
    expect(DEFAULT_GENERATION.speciesMix.noctule).toBe(0);
  });
});

describe("derived detections", () => {
  it("recomputes detections from clips without storing them in the project", () => {
    const project = projectWithClips();
    expect("detections" in project).toBe(false);
    const before = deriveDetections(project).length;
    const modified = { ...project, clips: [{ ...project.clips[0], durationMs: 1000 }] };
    expect(deriveDetections(modified).length).toBeGreaterThan(before / 2);
  });

  it("flattens multiple clips sorted by time_ms", () => {
    const detections = deriveDetections(projectWithClips());
    expect(detections.length).toBeGreaterThan(3);
    expect(detections.map((detection) => detection.timeMs)).toEqual(
      [...detections.map((detection) => detection.timeMs)].sort((left, right) => left - right)
    );
  });

  it("generates echoes with delay, shifted FME and flags", () => {
    const clip = {
      ...projectWithClips().clips[0],
      durationMs: 120,
      iciMeanMs: 60,
      echo: { enabled: true, probability: 1, delayMinMs: 1, delayMaxMs: 10, snrLossDb: 7, fmeDeltaBins: 1 }
    };
    const detections = deriveDetectionsForClip(clip);
    const echo = detections.find((detection) => detection.isEcho);
    const source = detections.find((detection) => !detection.isEcho);
    expect(echo).toBeDefined();
    expect(source).toBeDefined();
    expect(echo!.timeMs - source!.timeMs).toBeGreaterThanOrEqual(1);
    expect(Math.abs(echo!.posFME - source!.posFME)).toBeLessThanOrEqual(1);
  });

  it("creates a half-ICI offset copy for interleaved individuals", () => {
    const clip = projectWithClips().clips[0];
    const copy = duplicateClipWithHalfIciOffset(clip);
    expect(isGeneratedClip(clip)).toBe(true);
    expect(isGeneratedClip(copy)).toBe(true);
    if (!isGeneratedClip(clip) || !isGeneratedClip(copy)) throw new Error("Expected generated clips");
    expect(copy.id).not.toBe(clip.id);
    expect(copy.startMs).toBe(Math.round(clip.startMs + clip.iciMeanMs / 2));
    expect(copy.individualId).not.toBe(clip.individualId);
  });

  it("converts a sequence to 1-3 isolated noise detections", () => {
    const noise = convertClipToNoise(projectWithClips().clips[0]);
    const detections = deriveDetectionsForClip(noise);
    expect(noise.kind).toBe("noise");
    expect(detections.length).toBeGreaterThanOrEqual(1);
    expect(detections.length).toBeLessThanOrEqual(3);
    expect(detections.every((detection) => detection.isNoise && !detection.isEcho)).toBe(true);
  });
});

describe("exports", () => {
  it("exports the native sensor header shape observed in DATA00.TXT", () => {
    const txt = exportSensorTxt(projectWithClips());
    expect(txt.startsWith("DETECTDATA\r\nFREQ_KHZ_ENREG 200\r\nLENFFT 512\r\nOVERLAP 2\r\nSNRMIN 19\r\n")).toBe(true);
    expect(txt).toContain("time_ms posFME posFI posFT posDUREE SNRdB\r\n");
    expect(txt).toContain("raw: uint32 uint8 uint8 uint8 uint8 uint8\r\n\r\nDATAASCII\r\n");
    expect(txt.split("\r\nDATAASCII\r\n")[1].trim().split("\r\n")[0]).toMatch(/^\d+ \d+ \d+ \d+ \d+ \d+$/);
  });

  it("keeps ground truth detection ids aligned with exported detections", () => {
    const project = projectWithClips();
    const txtRows = exportSensorTxt(project).split("\r\nDATAASCII\r\n")[1].trim().split("\r\n");
    const csvRows = exportGroundTruthCsv(project).trim().split("\n").slice(1);
    expect(csvRows).toHaveLength(txtRows.length);
    expect(csvRows[0].startsWith("det-000001,")).toBe(true);
  });
});

describe("sensor TXT import", () => {
  it("parses sensor metadata and rows", () => {
    const parsed = parseSensorTxt(SENSOR_SAMPLE);
    expect(parsed.metadata.freqKhzEnreg).toBe(200);
    expect(parsed.metadata.lenfft).toBe(512);
    expect(parsed.metadata.overlap).toBe(2);
    expect(parsed.metadata.snrMin).toBe(19);
    expect(parsed.rows).toHaveLength(4);
    expect(parsed.rows[0]).toEqual({ timeMs: 1000, posFME: 97, posFI: 100, posFT: 94, posDUREE: 6, snrDb: 25 });
  });

  it("segments rows with configurable gap and infers species from FME", () => {
    const parsed = parseSensorTxt(SENSOR_SAMPLE);
    expect(segmentRows(parsed.rows, 100)).toEqual([[0, 2], [2, 4]]);
    expect(inferSpeciesFromFme(38)).toBe("Pipistrelle de Kuhl");
    expect(inferSpeciesFromFme(53.5)).toBe("Pipistrelle pygmee");
  });

  it("stores imported rows out of project clips and exports identical rows when not moved", () => {
    importedStoreManager.clear();
    const project = createEmptyProject();
    const { clips } = importSensorTxtAsClips(SENSOR_SAMPLE, { filename: "DATA00.TXT", tracks: project.tracks });
    const importedProject = { ...project, clips, tracks: project.tracks.map((track) => ({ ...track, clipIds: clips.filter((clip) => clip.trackId === track.id).map((clip) => clip.id) })) };
    const exportedRows = exportSensorTxt(importedProject).split("\r\nDATAASCII\r\n")[1].trim().split("\r\n");
    expect(exportedRows).toEqual([
      "1000 97 100 94 6 25",
      "1080 98 101 95 6 26",
      "1250 136 140 132 5 24",
      "1300 137 141 133 5 23"
    ]);
  });

  it("applies horizontal offset to imported rows and globally sorts mixed exports", () => {
    importedStoreManager.clear();
    const project = createEmptyProject();
    const { clips } = importSensorTxtAsClips(SENSOR_SAMPLE, { filename: "DATA00.TXT", tracks: project.tracks });
    const moved = { ...clips[0], startMs: clips[0].startMs + 500 };
    const mixedProject = { ...project, clips: [moved, clips[1], { ...projectWithClips().clips[0], startMs: 900 }] };
    const rows = exportSensorTxt(mixedProject).split("\r\nDATAASCII\r\n")[1].trim().split("\r\n");
    const times = rows.map((row) => Number(row.split(" ")[0]));
    expect(times).toEqual([...times].sort((left, right) => left - right));
    expect(rows).toContain("1500 97 100 94 6 25");
    expect(rows).toContain("1580 98 101 95 6 26");
  });

  it("snapshots and hydrates imported stores for portable scenario JSON", () => {
    importedStoreManager.clear();
    const project = createEmptyProject();
    const { clips } = importSensorTxtAsClips(SENSOR_SAMPLE, { filename: "DATA00.TXT", tracks: project.tracks });
    const importedProject = { ...project, clips };
    const snapshot = JSON.parse((awaitImportJson(importedProject))) as ReturnType<typeof JSON.parse>;
    importedStoreManager.clear();
    importedStoreManager.hydrate(snapshot.importedStores);
    const restored = stripImportedStores(snapshot);
    expect(restored.clips).toHaveLength(clips.length);
    expect(importedStoreManager.list()[0].nRows).toBe(4);
  });

  it("removes imported stores that are no longer referenced", () => {
    importedStoreManager.clear();
    const project = createEmptyProject();
    importSensorTxtAsClips(SENSOR_SAMPLE, { filename: "DATA00.TXT", tracks: project.tracks });
    expect(importedStoreManager.list()).toHaveLength(1);
    importedStoreManager.removeUnused([]);
    expect(importedStoreManager.list()).toHaveLength(0);
  });
});

function awaitImportJson(project: ScenarioProject): string {
  return JSON.stringify({
    ...project,
    importedStores: importedStoreManager.toJSON()
  });
}
