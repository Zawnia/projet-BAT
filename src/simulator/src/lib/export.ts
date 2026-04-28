import { deriveDetections } from "./detection";
import { isImportedClip } from "./clipGuards";
import { importedStoreManager } from "./importedStore";
import { sensorHeader, sensorRowToText } from "./sensorFormat";
import type { Detection, ScenarioProject, ScenarioProjectSnapshot, SensorDetectionRow } from "./types";

const CRLF = "\r\n";

export function exportSensorTxt(project: ScenarioProject): string {
  const sensorRows = exportSensorRows(project);
  const rows = sensorRows.map(sensorRowToText);
  return `${sensorHeader(sensorRows.length)}${CRLF}${rows.join(CRLF)}${CRLF}`;
}

export function exportGroundTruthCsv(project: ScenarioProject): string {
  const detections = deriveDetections(project);
  const header = "detection_id,time_ms,individu_id,espèce,est_echo,est_bruit,sequence_id";
  const rows = detections.map((detection) =>
    [
      detection.detectionId,
      detection.timeMs,
      csvEscape(detection.individualId),
      csvEscape(detection.speciesName),
      detection.isEcho ? "true" : "false",
      detection.isNoise ? "true" : "false",
      csvEscape(detection.sequenceId)
    ].join(",")
  );
  return `${header}\n${rows.join("\n")}\n`;
}

export function exportProjectJson(project: ScenarioProject): string {
  const serializable: ScenarioProjectSnapshot = {
    schemaVersion: project.schemaVersion,
    id: project.id,
    name: project.name,
    durationMs: project.durationMs,
    tracks: project.tracks.map((track) => ({ ...track, clipIds: [...track.clipIds] })),
    clips: project.clips.map((clip) => (isImportedClip(clip) ? { ...clip, summary: { ...clip.summary } } : { ...clip, echo: { ...clip.echo } })),
    generation: { ...project.generation, speciesMix: { ...project.generation.speciesMix } },
    updatedAt: new Date().toISOString(),
    importedStores: importedStoreManager.toJSON()
  };
  return JSON.stringify(serializable, null, 2);
}

export function downloadText(filename: string, text: string, type: string): void {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function exportSensorRows(project: ScenarioProject): SensorDetectionRow[] {
  const rows = project.clips.flatMap((clip) => {
    if (!isImportedClip(clip)) {
      return deriveDetections({ ...project, clips: [clip] }).map(detectionToSensorRow);
    }
    const store = importedStoreManager.get(clip.storeId);
    if (!store) return [];
    const offset = clip.startMs - clip.originalStartMs;
    return store.rows.slice(clip.rowStart, clip.rowEnd).map((row) => ({
      ...row,
      timeMs: Math.max(0, Math.round(row.timeMs + offset))
    }));
  });
  return rows.sort((left, right) => left.timeMs - right.timeMs);
}

function detectionToSensorRow(detection: Detection): SensorDetectionRow {
  return {
    timeMs: detection.timeMs,
    posFME: detection.posFME,
    posFI: detection.posFI,
    posFT: detection.posFT,
    posDUREE: detection.posDUREE,
    snrDb: detection.snrDb
  };
}

function csvEscape(value: string): string {
  if (!/[",\n]/.test(value)) return value;
  return `"${value.replace(/"/g, '""')}"`;
}
