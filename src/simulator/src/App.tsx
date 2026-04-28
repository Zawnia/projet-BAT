import { useEffect, useMemo, useRef, useState } from "react";
import { TimelineCanvas } from "./components/TimelineCanvas";
import {
  createClipFromSpecies,
  convertClipToNoise,
  deriveDetections,
  pickTrackForSpecies
} from "./lib/detection";
import { isGeneratedClip, isImportedClip } from "./lib/clipGuards";
import { downloadText, exportGroundTruthCsv, exportProjectJson, exportSensorTxt } from "./lib/export";
import { importedStoreManager } from "./lib/importedStore";
import { saveProject, loadProject, stripImportedStores } from "./lib/storage";
import { createEmptyProject, SPECIES_TEMPLATES, speciesById } from "./lib/species";
import type { Clip, GeneratedClip, GenerationSettings, ImportedClip, ImportedDetectionStore, ScenarioProject, ScenarioProjectSnapshot, TimelineView } from "./lib/types";

type WorkerMessage = { type: "generated-night"; project: ScenarioProject };
type ImportWorkerMessage =
  | { type: "imported-sensor-txt"; result: { store: ImportedDetectionStore; clips: ImportedClip[] } }
  | { type: "import-error"; message: string };

export function App() {
  const [project, setProject] = useState<ScenarioProject>(() => createEmptyProject());
  const [view, setView] = useState<TimelineView>({ scrollMs: 0, pxPerMs: 0.006, selectedClipIds: [] });
  const [status, setStatus] = useState("Projet local pret.");
  const [isGenerating, setIsGenerating] = useState(false);
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const txtInputRef = useRef<HTMLInputElement | null>(null);
  const workerRef = useRef<Worker | null>(null);
  const clipboardRef = useRef<Clip[]>([]);
  const selectedClip = useMemo(
    () => project.clips.find((clip) => clip.id === view.selectedClipIds[0]) ?? null,
    [project.clips, view.selectedClipIds]
  );
  const detectionCount = useMemo(() => deriveDetections(project).length, [project]);

  useEffect(() => {
    loadProject().then((stored) => {
      if (stored) {
        setProject(stored);
        setStatus("Projet restaure depuis IndexedDB.");
      }
    });
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      saveProject(project).catch((error) => setStatus(`Sauvegarde impossible: ${error.message}`));
    }, 450);
    return () => window.clearTimeout(timer);
  }, [project]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName)) return;
      if (event.key === "Delete" || event.key === "Backspace") {
        deleteSelectedClips();
        event.preventDefault();
        return;
      }
      if (!(event.ctrlKey || event.metaKey)) return;
      if (event.key.toLowerCase() === "c") {
        clipboardRef.current = project.clips.filter((clip) => view.selectedClipIds.includes(clip.id));
        setStatus(`${clipboardRef.current.length} clip(s) copies.`);
        event.preventDefault();
      }
      if (event.key.toLowerCase() === "v" && clipboardRef.current.length > 0) {
        const pasted = clipboardRef.current.map((clip, index) => duplicateClip(clip, `paste-${index + 1}`));
        updateProject((current) => ({
          ...current,
          tracks: current.tracks.map((track) => ({
            ...track,
            clipIds: [...track.clipIds, ...pasted.filter((clip) => clip.trackId === track.id).map((clip) => clip.id)]
          })),
          clips: [...current.clips, ...pasted]
        }));
        setView((current) => ({ ...current, selectedClipIds: pasted.map((clip) => clip.id) }));
        event.preventDefault();
      }
      if (event.key.toLowerCase() === "d") {
        duplicateSelectedClips();
        event.preventDefault();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [project.clips, view.selectedClipIds]);

  function updateProject(mutator: (project: ScenarioProject) => ScenarioProject) {
    setProject((current) => ({ ...mutator(current), updatedAt: new Date().toISOString() }));
  }

  function upsertClip(next: Clip) {
    updateProject((current) => ({
      ...current,
      tracks: current.tracks.map((track) => ({
        ...track,
        clipIds:
          track.id === next.trackId
            ? Array.from(new Set([...track.clipIds, next.id]))
            : track.clipIds.filter((id) => id !== next.id)
      })),
      clips: current.clips.map((clip) => (clip.id === next.id ? next : clip))
    }));
  }

  function addClip(speciesId: string, trackId: string, startMs: number) {
    const species = speciesById(speciesId);
    const clip = createClipFromSpecies(species, trackId, startMs);
    updateProject((current) => ({
      ...current,
      tracks: current.tracks.map((track) =>
        track.id === trackId ? { ...track, clipIds: [...track.clipIds, clip.id] } : track
      ),
      clips: [...current.clips, clip]
    }));
    setView((current) => ({ ...current, selectedClipIds: [clip.id] }));
  }

  function handleContextAction(clipId: string, action: "duplicate" | "delete" | "noise" | "half-ici") {
    const clip = project.clips.find((item) => item.id === clipId);
    if (!clip) return;
    if (action === "delete") {
      updateProject((current) => ({
        ...current,
        tracks: current.tracks.map((track) => ({ ...track, clipIds: track.clipIds.filter((id) => id !== clipId) })),
        clips: current.clips.filter((item) => item.id !== clipId)
      }));
      importedStoreManager.removeUnused(project.clips.filter(isImportedClip).filter((item) => item.id !== clipId).map((item) => item.storeId));
      setView((current) => ({ ...current, selectedClipIds: [] }));
      return;
    }
    const next =
      action === "noise" && isGeneratedClip(clip)
        ? convertClipToNoise(clip)
        : action === "half-ici"
          ? duplicateHalfIci(clip)
          : duplicateClip(clip, "copy");
    updateProject((current) => ({
      ...current,
      tracks: current.tracks.map((track) =>
        track.id === next.trackId ? { ...track, clipIds: [...track.clipIds, next.id] } : track
      ),
      clips: [...current.clips, next]
    }));
    setView((current) => ({ ...current, selectedClipIds: [next.id] }));
  }

  function duplicateSelectedClips() {
    const selected = project.clips.filter((clip) => view.selectedClipIds.includes(clip.id));
    if (selected.length === 0) return;
    const duplicates = selected.map((clip, index) => duplicateClip(clip, `copy-${index + 1}`));
    updateProject((current) => ({
      ...current,
      tracks: current.tracks.map((track) => ({
        ...track,
        clipIds: [...track.clipIds, ...duplicates.filter((clip) => clip.trackId === track.id).map((clip) => clip.id)]
      })),
      clips: [...current.clips, ...duplicates]
    }));
    setView((current) => ({ ...current, selectedClipIds: duplicates.map((clip) => clip.id) }));
    setStatus(`${duplicates.length} clip(s) dupliques.`);
  }

  function deleteSelectedClips() {
    const selectedIds = new Set(view.selectedClipIds);
    if (selectedIds.size === 0) return;
    updateProject((current) => ({
      ...current,
      tracks: current.tracks.map((track) => ({
        ...track,
        clipIds: track.clipIds.filter((id) => !selectedIds.has(id))
      })),
      clips: current.clips.filter((clip) => !selectedIds.has(clip.id))
    }));
    importedStoreManager.removeUnused(project.clips.filter(isImportedClip).filter((clip) => !selectedIds.has(clip.id)).map((clip) => clip.storeId));
    setView((current) => ({ ...current, selectedClipIds: [] }));
    setStatus(`${selectedIds.size} clip(s) supprimes.`);
  }

  function duplicateClip(clip: Clip, suffix: string): Clip {
    if (isImportedClip(clip)) {
      return { ...clip, id: crypto.randomUUID(), startMs: clip.startMs + 1000 };
    }
    return {
      ...clip,
      id: crypto.randomUUID(),
      sequenceId: `${clip.sequenceId}-${suffix}`,
      startMs: clip.startMs + 1000,
      seed: clip.seed + 1009
    };
  }

  function duplicateHalfIci(clip: Clip): Clip {
    if (isImportedClip(clip)) {
      return { ...clip, id: crypto.randomUUID(), startMs: Math.round(clip.startMs + clip.summary.iciMedianMs / 2) };
    }
    return {
      ...clip,
      id: crypto.randomUUID(),
      individualId: `${clip.individualId}-half`,
      sequenceId: `${clip.sequenceId}-half`,
      startMs: Math.round(clip.startMs + clip.iciMeanMs / 2),
      seed: clip.seed + 2027
    };
  }

  function generateNight() {
    setIsGenerating(true);
    setStatus("Generation en cours dans le worker...");
    const worker = new Worker(new URL("./workers/generator.worker.ts", import.meta.url), { type: "module" });
    workerRef.current = worker;
    worker.onmessage = (event: MessageEvent<WorkerMessage>) => {
      if (event.data.type !== "generated-night") return;
      setProject(event.data.project);
      setView((current) => ({ ...current, scrollMs: 0, selectedClipIds: [] }));
      setIsGenerating(false);
      setStatus("Nuit generee et editable sur la timeline.");
      worker.terminate();
    };
    worker.onerror = (event) => {
      setIsGenerating(false);
      setStatus(`Generation impossible: ${event.message}`);
      worker.terminate();
    };
    worker.postMessage({ type: "generate-night", settings: project.generation, seed: Date.now() });
  }

  function updateGeneration(settings: Partial<GenerationSettings>) {
    updateProject((current) => ({
      ...current,
      durationMs:
        settings.durationHours !== undefined ? settings.durationHours * 60 * 60 * 1000 : current.durationMs,
      generation: { ...current.generation, ...settings }
    }));
  }

  function exportTxt() {
    downloadText("scenario.TXT", exportSensorTxt(project), "text/plain;charset=utf-8");
    setExportMenuOpen(false);
    setStatus(`${detectionCount.toLocaleString("fr-FR")} detections exportees en TXT.`);
  }

  function exportCsv() {
    downloadText("scenario_groundtruth.csv", exportGroundTruthCsv(project), "text/csv;charset=utf-8");
    setExportMenuOpen(false);
    setStatus("Ground truth CSV exportee.");
  }

  function exportJson() {
    downloadText("scenario.json", exportProjectJson(project), "application/json;charset=utf-8");
    setExportMenuOpen(false);
    setStatus("Projet JSON exporte.");
  }

  function exportAll() {
    downloadText("scenario.TXT", exportSensorTxt(project), "text/plain;charset=utf-8");
    downloadText("scenario_groundtruth.csv", exportGroundTruthCsv(project), "text/csv;charset=utf-8");
    downloadText("scenario.json", exportProjectJson(project), "application/json;charset=utf-8");
    setExportMenuOpen(false);
    setStatus(`${detectionCount.toLocaleString("fr-FR")} detections exportees avec ground truth et projet.`);
  }

  function importProject(file: File) {
    file.text().then((text) => {
      const parsed = JSON.parse(text) as ScenarioProjectSnapshot;
      importedStoreManager.hydrate(parsed.importedStores);
      setProject(stripImportedStores(parsed));
      setView((current) => ({ ...current, selectedClipIds: [] }));
      setStatus(`${file.name} charge.`);
    });
  }

  function importSensorTxt(file: File) {
    setStatus(`Import de ${file.name} en cours...`);
    file.text().then((text) => {
      const worker = new Worker(new URL("./workers/import.worker.ts", import.meta.url), { type: "module" });
      worker.onmessage = (event: MessageEvent<ImportWorkerMessage>) => {
        if (event.data.type === "import-error") {
          setStatus(event.data.message);
          worker.terminate();
          return;
        }
        importedStoreManager.add(event.data.result.store);
        const importedClips = event.data.result.clips;
        updateProject((current) => ({
          ...current,
          durationMs: Math.max(current.durationMs, ...importedClips.map((clip) => clip.startMs + clip.durationMs)),
          tracks: current.tracks.map((track) => ({
            ...track,
            clipIds: [...track.clipIds, ...importedClips.filter((clip) => clip.trackId === track.id).map((clip) => clip.id)]
          })),
          clips: [...current.clips, ...importedClips]
        }));
        setView((current) => ({ ...current, selectedClipIds: importedClips[0] ? [importedClips[0].id] : [] }));
        setStatus(`${importedClips.length} sequences importees, ${event.data.result.store.rows.length.toLocaleString("fr-FR")} detections.`);
        worker.terminate();
      };
      worker.postMessage({ type: "import-sensor-txt", text, filename: file.name });
    });
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>Simulateur acoustique</h1>
          <p>{project.clips.length} clips, {detectionCount.toLocaleString("fr-FR")} detections derivees</p>
        </div>
        <div className="actions">
          <button onClick={() => {
            importedStoreManager.clear();
            setProject(createEmptyProject());
          }}>Nouveau</button>
          <button onClick={() => fileInputRef.current?.click()}>Charger</button>
          <button onClick={() => txtInputRef.current?.click()}>Importer TXT</button>
          <div className="export-group">
            <button className="export-main" onClick={exportTxt}>Export TXT</button>
            <button
              className="export-arrow"
              aria-label="Autres exports"
              aria-expanded={exportMenuOpen}
              onClick={() => setExportMenuOpen((open) => !open)}
            >
              ▾
            </button>
            {exportMenuOpen && (
              <div className="export-menu">
                <button onClick={exportCsv}>Ground truth CSV</button>
                <button onClick={exportJson}>Projet JSON</button>
                <button onClick={exportAll}>Tout exporter</button>
              </div>
            )}
          </div>
          <input
            ref={fileInputRef}
            hidden
            type="file"
            accept="application/json,.json"
            onChange={(event) => {
              const file = event.currentTarget.files?.[0];
              if (file) importProject(file);
            }}
          />
          <input
            ref={txtInputRef}
            hidden
            type="file"
            accept=".txt,.TXT,text/plain"
            onChange={(event) => {
              const file = event.currentTarget.files?.[0];
              if (file) importSensorTxt(file);
              event.currentTarget.value = "";
            }}
          />
        </div>
      </header>

      <section className="workspace">
        <aside className="panel library">
          <h2>Especes</h2>
          <div className="species-list">
            {SPECIES_TEMPLATES.map((species) => (
              <button
                key={species.id}
                draggable
                onDragStart={(event) => event.dataTransfer.setData("application/x-species-id", species.id)}
                onClick={() => addClip(species.id, pickTrackForSpecies(project, species.id), view.scrollMs + 2000)}
              >
                <span className="swatch" style={{ background: species.color }} />
                <span>
                  <strong>{species.commonName}</strong>
                  <small>{species.fmeRangeKhz[0]}-{species.fmeRangeKhz[1]} kHz</small>
                </span>
              </button>
            ))}
          </div>

          <h2>Generer nuit</h2>
          <label>
            Duree
            <input
              type="number"
              min={0.1}
              step={0.5}
              value={project.generation.durationHours}
              onChange={(event) => updateGeneration({ durationHours: Number(event.target.value) })}
            />
          </label>
          <label>
            Densite / h
            <input
              type="number"
              min={1}
              value={project.generation.densityPerHour}
              onChange={(event) => updateGeneration({ densityPerHour: Number(event.target.value) })}
            />
          </label>
          <label>
            Bruit
            <input
              type="range"
              min={0}
              max={0.5}
              step={0.01}
              value={project.generation.noiseLevel}
              onChange={(event) => updateGeneration({ noiseLevel: Number(event.target.value) })}
            />
          </label>
          <label>
            Echos
            <input
              type="range"
              min={0}
              max={0.8}
              step={0.01}
              value={project.generation.echoProbability}
              onChange={(event) => updateGeneration({ echoProbability: Number(event.target.value) })}
            />
          </label>
          <label>
            Profil
            <select
              value={project.generation.activityProfile}
              onChange={(event) => updateGeneration({ activityProfile: event.target.value as GenerationSettings["activityProfile"] })}
            >
              <option value="dusk_dawn">Crepuscule/aube</option>
              <option value="uniform">Uniforme</option>
            </select>
          </label>
          <div className="mix-list">
            {SPECIES_TEMPLATES.map((species) => (
              <label key={species.id}>
                {species.commonName} {Math.round((project.generation.speciesMix[species.id] ?? 0) * 100)}%
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.01}
                  value={project.generation.speciesMix[species.id] ?? 0}
                  onChange={(event) =>
                    updateGeneration({
                      speciesMix: {
                        ...project.generation.speciesMix,
                        [species.id]: Number(event.target.value)
                      }
                    })
                  }
                />
              </label>
            ))}
          </div>
          <button className="primary" disabled={isGenerating} onClick={generateNight}>
            Generer nuit
          </button>
        </aside>

        <section className="timeline-panel">
          <div className="timeline-toolbar">
            <span>{status}</span>
            <label>
              Zoom
              <input
                type="range"
                min={0.00002}
                max={0.08}
                step={0.0002}
                value={view.pxPerMs}
                onChange={(event) => setView({ ...view, pxPerMs: Number(event.target.value) })}
              />
            </label>
          </div>
          <TimelineCanvas
            project={project}
            view={view}
            onViewChange={setView}
            onClipChange={upsertClip}
            onDropSpecies={addClip}
            onOpenInspector={(clipId) => setView((current) => ({ ...current, selectedClipIds: [clipId] }))}
            onContextAction={handleContextAction}
          />
        </section>

        <aside className="panel inspector">
          <h2>Inspector</h2>
          {selectedClip ? (
            isImportedClip(selectedClip) ? (
              <ImportedClipInspector clip={selectedClip} />
            ) : (
              <ClipInspector clip={selectedClip} onChange={upsertClip} onHalfIci={() => handleContextAction(selectedClip.id, "half-ici")} />
            )
          ) : (
            <p className="muted">Selectionne un clip pour modifier ses parametres.</p>
          )}
        </aside>
      </section>
    </main>
  );
}

function ClipInspector({ clip, onChange, onHalfIci }: { clip: GeneratedClip; onChange: (clip: Clip) => void; onHalfIci: () => void }) {
  function patch(values: Partial<GeneratedClip>) {
    onChange({ ...clip, ...values });
  }
  return (
    <div className="inspector-form">
      <strong>{clip.kind === "noise" ? "Bruit ponctuel" : clip.speciesName}</strong>
      <label>Debut ms<input type="number" value={Math.round(clip.startMs)} onChange={(event) => patch({ startMs: Number(event.target.value) })} /></label>
      <label>Duree ms<input type="number" min={40} value={Math.round(clip.durationMs)} onChange={(event) => patch({ durationMs: Number(event.target.value) })} /></label>
      <label>FME kHz<input type="number" step={0.1} value={clip.fmeKhz} onChange={(event) => patch({ fmeKhz: Number(event.target.value) })} /></label>
      <label>FI kHz<input type="number" step={0.1} value={clip.fiKhz} onChange={(event) => patch({ fiKhz: Number(event.target.value) })} /></label>
      <label>FT kHz<input type="number" step={0.1} value={clip.ftKhz} onChange={(event) => patch({ ftKhz: Number(event.target.value) })} /></label>
      <label>ICI moyen<input type="number" min={4} value={clip.iciMeanMs} onChange={(event) => patch({ iciMeanMs: Number(event.target.value) })} /></label>
      <label>SNR moyen<input type="number" min={19} max={40} value={clip.snrMeanDb} onChange={(event) => patch({ snrMeanDb: Number(event.target.value) })} /></label>
      <label>Phase
        <select value={clip.phase} onChange={(event) => patch({ phase: event.target.value as GeneratedClip["phase"] })}>
          <option value="transit">Transit</option>
          <option value="chasse">Chasse</option>
          <option value="approche">Approche</option>
          <option value="feeding_buzz">Feeding buzz</option>
        </select>
      </label>
      <label className="inline">
        <input type="checkbox" checked={clip.echo.enabled} onChange={(event) => patch({ echo: { ...clip.echo, enabled: event.target.checked } })} />
        Echos
      </label>
      <button onClick={onHalfIci}>Decaler de demi-ICI</button>
    </div>
  );
}

function ImportedClipInspector({ clip }: { clip: ImportedClip }) {
  const store = importedStoreManager.get(clip.storeId);
  return (
    <div className="inspector-form">
      <strong>Clip importe</strong>
      <p className="muted">{clip.summary.inferredSpecies ?? "Espece indeterminee"} - inferee depuis FME</p>
      <Metric label="Fichier" value={clip.summary.filename} />
      <Metric label="Detections" value={clip.summary.nDetections.toLocaleString("fr-FR")} />
      <Metric label="Plage" value={`${Math.round(clip.summary.firstTimeMs)} - ${Math.round(clip.summary.lastTimeMs)} ms`} />
      <Metric label="Duree" value={`${Math.round(clip.durationMs)} ms`} />
      <Metric label="FME mediane" value={`${clip.summary.fmeMedianKhz.toFixed(2)} kHz`} />
      <Metric label="FME std" value={`${clip.summary.fmeStdKhz.toFixed(2)} kHz`} />
      <Metric label="ICI median" value={`${clip.summary.iciMedianMs.toFixed(0)} ms`} />
      <Metric label="SNR median" value={`${clip.summary.snrMedianDb.toFixed(0)} dB`} />
      <Metric label="Store" value={store ? `${store.rows.length.toLocaleString("fr-FR")} rows` : "manquant"} />
      <button disabled>Convertir en sequence parametrique</button>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <p className="metric-line">
      <span>{label}</span>
      <strong>{value}</strong>
    </p>
  );
}
