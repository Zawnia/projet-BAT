import { isImportedClip } from "./clipGuards";
import { importedStoreManager } from "./importedStore";
import type { ScenarioProject, ScenarioProjectSnapshot } from "./types";

const DB_NAME = "bat-simulator";
const DB_VERSION = 1;
const STORE = "projects";
const ACTIVE_KEY = "active";

export async function saveProject(project: ScenarioProject): Promise<void> {
  const db = await openDb();
  await requestToPromise(db.transaction(STORE, "readwrite").objectStore(STORE).put(stripComputed(project), ACTIVE_KEY));
  db.close();
}

export async function loadProject(): Promise<ScenarioProject | null> {
  const db = await openDb();
  const value = await requestToPromise<ScenarioProjectSnapshot | undefined>(
    db.transaction(STORE, "readonly").objectStore(STORE).get(ACTIVE_KEY)
  );
  db.close();
  if (!value) return null;
  importedStoreManager.hydrate(value.importedStores);
  return stripImportedStores(value);
}

function stripComputed(project: ScenarioProject): ScenarioProjectSnapshot {
  return {
    schemaVersion: project.schemaVersion,
    id: project.id,
    name: project.name,
    durationMs: project.durationMs,
    clips: project.clips.map((clip) => (isImportedClip(clip) ? { ...clip, summary: { ...clip.summary } } : { ...clip, echo: { ...clip.echo } })),
    tracks: project.tracks.map((track) => ({ ...track, clipIds: [...track.clipIds] })),
    generation: { ...project.generation, speciesMix: { ...project.generation.speciesMix } },
    updatedAt: new Date().toISOString(),
    importedStores: importedStoreManager.toJSON()
  };
}

export function stripImportedStores(snapshot: ScenarioProjectSnapshot): ScenarioProject {
  return {
    schemaVersion: snapshot.schemaVersion,
    id: snapshot.id,
    name: snapshot.name,
    durationMs: snapshot.durationMs,
    tracks: snapshot.tracks.map((track) => ({ ...track, clipIds: [...track.clipIds] })),
    clips: snapshot.clips.map((clip) => (isImportedClip(clip) ? { ...clip, summary: { ...clip.summary } } : { ...clip, echo: { ...clip.echo } })),
    generation: { ...snapshot.generation, speciesMix: { ...snapshot.generation.speciesMix } },
    updatedAt: snapshot.updatedAt
  };
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      request.result.createObjectStore(STORE);
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function requestToPromise<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}
