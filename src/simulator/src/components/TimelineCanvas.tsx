import { useEffect, useMemo, useRef, useState } from "react";
import { deriveDetectionsForClip } from "../lib/detection";
import { isImportedClip } from "../lib/clipGuards";
import { importedStoreManager } from "../lib/importedStore";
import { SPECIES_TEMPLATES } from "../lib/species";
import type { Clip, ImportedClip, ScenarioProject, SensorDetectionRow, TimelineView } from "../lib/types";

const TRACK_HEIGHT = 168;
const HEADER_WIDTH = 148;
const HANDLE_PX = 8;

interface Props {
  project: ScenarioProject;
  view: TimelineView;
  onViewChange: (view: TimelineView) => void;
  onClipChange: (clip: Clip) => void;
  onDropSpecies: (speciesId: string, trackId: string, startMs: number) => void;
  onOpenInspector: (clipId: string) => void;
  onContextAction: (clipId: string, action: "duplicate" | "delete" | "noise" | "half-ici") => void;
}

type DragState =
  | { mode: "move"; clip: Clip; startX: number; startY: number }
  | { mode: "resize"; clip: Clip; startX: number }
  | null;

export function TimelineCanvas({
  project,
  view,
  onViewChange,
  onClipChange,
  onDropSpecies,
  onOpenInspector,
  onContextAction
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const [drag, setDrag] = useState<DragState>(null);
  const [menu, setMenu] = useState<{ x: number; y: number; clipId: string } | null>(null);
  const clipColors = useMemo(
    () => new Map(SPECIES_TEMPLATES.map((species) => [species.id, species.color])),
    []
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap) return;
    const rect = wrap.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.floor(rect.width * dpr);
    canvas.height = Math.floor(Math.max(360, project.tracks.length * TRACK_HEIGHT) * dpr);
    canvas.style.width = `${rect.width}px`;
    canvas.style.height = `${Math.max(360, project.tracks.length * TRACK_HEIGHT)}px`;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw(ctx, rect.width, Math.max(360, project.tracks.length * TRACK_HEIGHT), project, view, clipColors);
  }, [clipColors, project, view]);

  useEffect(() => {
    const onResize = () => onViewChange({ ...view });
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [onViewChange, view]);

  function hitTest(clientX: number, clientY: number): { clip: Clip; zone: "body" | "resize" } | null {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    for (const clip of project.clips) {
      const trackIndex = project.tracks.findIndex((track) => track.id === clip.trackId);
      if (trackIndex < 0) continue;
      const x0 = HEADER_WIDTH + (clip.startMs - view.scrollMs) * view.pxPerMs;
      const x1 = HEADER_WIDTH + (clip.startMs + clip.durationMs - view.scrollMs) * view.pxPerMs;
      const y0 = trackIndex * TRACK_HEIGHT + 24;
      const y1 = (trackIndex + 1) * TRACK_HEIGHT - 14;
      if (x >= x0 && x <= x1 && y >= y0 && y <= y1) {
        return { clip, zone: x1 - x <= HANDLE_PX ? "resize" : "body" };
      }
    }
    return null;
  }

  function pointerToTime(clientX: number): number {
    const rect = canvasRef.current!.getBoundingClientRect();
    return Math.max(0, view.scrollMs + (clientX - rect.left - HEADER_WIDTH) / view.pxPerMs);
  }

  function pointerToTrack(clientY: number): string {
    const rect = canvasRef.current!.getBoundingClientRect();
    const index = Math.min(project.tracks.length - 1, Math.max(0, Math.floor((clientY - rect.top) / TRACK_HEIGHT)));
    return project.tracks[index].id;
  }

  function pointerToFrequency(clientY: number, trackId: string): number {
    const rect = canvasRef.current!.getBoundingClientRect();
    const trackIndex = project.tracks.findIndex((track) => track.id === trackId);
    const track = project.tracks[trackIndex];
    const y = clientY - rect.top - trackIndex * TRACK_HEIGHT;
    const ratio = 1 - Math.min(1, Math.max(0, (y - 24) / (TRACK_HEIGHT - 40)));
    return track.minKhz + ratio * (track.maxKhz - track.minKhz);
  }

  const menuClip = menu ? project.clips.find((clip) => clip.id === menu.clipId) ?? null : null;

  return (
    <div
      ref={wrapRef}
      className="timeline-wrap"
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        const speciesId = event.dataTransfer.getData("application/x-species-id");
        if (!speciesId) return;
        onDropSpecies(speciesId, pointerToTrack(event.clientY), Math.round(pointerToTime(event.clientX)));
      }}
    >
      <canvas
        ref={canvasRef}
        className="timeline-canvas"
        onWheel={(event) => {
          event.preventDefault();
          const factor = event.deltaY < 0 ? 1.18 : 0.84;
          const nextPxPerMs = Math.min(0.9, Math.max(0.00002, view.pxPerMs * factor));
          onViewChange({ ...view, pxPerMs: nextPxPerMs });
        }}
        onDoubleClick={(event) => {
          const hit = hitTest(event.clientX, event.clientY);
          if (hit) onOpenInspector(hit.clip.id);
        }}
        onContextMenu={(event) => {
          event.preventDefault();
          const hit = hitTest(event.clientX, event.clientY);
          if (hit) setMenu({ x: event.clientX, y: event.clientY, clipId: hit.clip.id });
        }}
        onPointerDown={(event) => {
          setMenu(null);
          const hit = hitTest(event.clientX, event.clientY);
          if (!hit) {
            onViewChange({ ...view, selectedClipIds: [] });
            return;
          }
          const selected = event.shiftKey
            ? Array.from(new Set([...view.selectedClipIds, hit.clip.id]))
            : [hit.clip.id];
          onViewChange({ ...view, selectedClipIds: selected });
          if (hit.zone === "resize" && isImportedClip(hit.clip)) return;
          setDrag(hit.zone === "resize" ? { mode: "resize", clip: hit.clip, startX: event.clientX } : { mode: "move", clip: hit.clip, startX: event.clientX, startY: event.clientY });
        }}
        onPointerMove={(event) => {
          if (!drag) return;
          if (drag.mode === "resize") {
            const deltaMs = (event.clientX - drag.startX) / view.pxPerMs;
            onClipChange({ ...drag.clip, durationMs: Math.max(40, drag.clip.durationMs + deltaMs) });
            return;
          }
          const deltaMs = (event.clientX - drag.startX) / view.pxPerMs;
          if (isImportedClip(drag.clip)) {
            onClipChange({
              ...drag.clip,
              startMs: Math.max(0, Math.round(drag.clip.startMs + deltaMs))
            });
            return;
          }
          const trackId = pointerToTrack(event.clientY);
          const fmeKhz = pointerToFrequency(event.clientY, trackId);
          const deltaKhz = fmeKhz - drag.clip.fmeKhz;
          onClipChange({
            ...drag.clip,
            trackId,
            startMs: Math.max(0, Math.round(drag.clip.startMs + deltaMs)),
            fmeKhz,
            fiKhz: drag.clip.fiKhz + deltaKhz,
            ftKhz: drag.clip.ftKhz + deltaKhz
          });
        }}
        onPointerUp={() => setDrag(null)}
        onPointerLeave={() => setDrag(null)}
      />
      <div className="timeline-scroll">
        <input
          aria-label="Scroll temporel"
          type="range"
          min={0}
          max={Math.max(0, project.durationMs)}
          step={100}
          value={view.scrollMs}
          onChange={(event) => onViewChange({ ...view, scrollMs: Number(event.target.value) })}
        />
      </div>
      {menu && menuClip && (
        <div className="context-menu" style={{ left: menu.x, top: menu.y }}>
          <button onClick={() => onContextAction(menu.clipId, "duplicate")}>Dupliquer</button>
          {!isImportedClip(menuClip) && (
            <>
              <button onClick={() => onContextAction(menu.clipId, "half-ici")}>Decaler de demi-ICI</button>
              <button onClick={() => onContextAction(menu.clipId, "noise")}>Convertir en bruit</button>
            </>
          )}
          <button onClick={() => onContextAction(menu.clipId, "delete")}>Supprimer</button>
        </div>
      )}
    </div>
  );
}

function draw(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  project: ScenarioProject,
  view: TimelineView,
  clipColors: Map<string, string>
) {
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#091015";
  ctx.fillRect(0, 0, width, height);
  const visibleStart = view.scrollMs;
  const visibleEnd = view.scrollMs + (width - HEADER_WIDTH) / view.pxPerMs;

  project.tracks.forEach((track, trackIndex) => {
    const y = trackIndex * TRACK_HEIGHT;
    ctx.fillStyle = trackIndex % 2 ? "rgba(255,255,255,0.025)" : "rgba(255,255,255,0.045)";
    ctx.fillRect(0, y, width, TRACK_HEIGHT);
    ctx.fillStyle = "rgba(255,255,255,0.78)";
    ctx.font = "12px Inter, system-ui, sans-serif";
    ctx.fillText(track.name, 16, y + 28);
    ctx.fillStyle = "rgba(255,255,255,0.48)";
    ctx.fillText(`${track.minKhz}-${track.maxKhz} kHz`, 16, y + 48);
    ctx.strokeStyle = "rgba(255,255,255,0.08)";
    ctx.beginPath();
    ctx.moveTo(0, y + TRACK_HEIGHT - 1);
    ctx.lineTo(width, y + TRACK_HEIGHT - 1);
    ctx.stroke();
  });

  drawGrid(ctx, width, height, view);

  for (const clip of project.clips) {
    if (clip.startMs + clip.durationMs < visibleStart || clip.startMs > visibleEnd) continue;
    const trackIndex = project.tracks.findIndex((track) => track.id === clip.trackId);
    if (trackIndex < 0) continue;
    drawClip(ctx, clip, project, trackIndex, view, clipColors);
  }
}

function drawGrid(ctx: CanvasRenderingContext2D, width: number, height: number, view: TimelineView) {
  const stepMs = chooseGridStep(view.pxPerMs);
  const first = Math.floor(view.scrollMs / stepMs) * stepMs;
  ctx.strokeStyle = "rgba(255,255,255,0.07)";
  ctx.fillStyle = "rgba(255,255,255,0.45)";
  ctx.font = "11px Inter, system-ui, sans-serif";
  for (let t = first; t < view.scrollMs + width / view.pxPerMs; t += stepMs) {
    const x = HEADER_WIDTH + (t - view.scrollMs) * view.pxPerMs;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, height);
    ctx.stroke();
    ctx.fillText(formatTime(t), x + 4, 14);
  }
}

function drawClip(
  ctx: CanvasRenderingContext2D,
  clip: Clip,
  project: ScenarioProject,
  trackIndex: number,
  view: TimelineView,
  clipColors: Map<string, string>
) {
  const track = project.tracks[trackIndex];
  const selected = view.selectedClipIds.includes(clip.id);
  const x0 = HEADER_WIDTH + (clip.startMs - view.scrollMs) * view.pxPerMs;
  const w = Math.max(5, clip.durationMs * view.pxPerMs);
  const y0 = trackIndex * TRACK_HEIGHT + 24;
  const h = TRACK_HEIGHT - 40;
  const color = isImportedClip(clip) ? "#f8fafc" : clip.kind === "noise" ? "#d1d5db" : clipColors.get(clip.speciesId) ?? "#ffffff";
  ctx.fillStyle = selected ? "rgba(255,255,255,0.11)" : "rgba(255,255,255,0.06)";
  ctx.strokeStyle = selected ? "#ffffff" : isImportedClip(clip) ? "rgba(248,250,252,0.72)" : color;
  ctx.lineWidth = selected ? 2 : 1;
  roundRect(ctx, x0, y0, w, h, 7);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = color;
  ctx.font = "12px Inter, system-ui, sans-serif";
  ctx.fillText(isImportedClip(clip) ? `Import: ${clip.speciesName}` : clip.kind === "noise" ? "Bruit" : clip.speciesName, x0 + 8, y0 + 18, Math.max(20, w - 16));

  ctx.strokeStyle = color;
  ctx.lineWidth = 1.4;
  if (isImportedClip(clip)) {
    drawImportedRows(ctx, clip, x0, y0, h, track.minKhz, track.maxKhz, view, color);
    ctx.fillStyle = "rgba(248,250,252,0.78)";
    ctx.fillText("lock", x0 + Math.max(10, w - 34), y0 + 18);
    return;
  }
  const detections = deriveDetectionsForClip(clip);
  for (const detection of detections) {
    const localX = HEADER_WIDTH + (detection.timeMs - view.scrollMs) * view.pxPerMs;
    if (localX < HEADER_WIDTH || localX > ctx.canvas.width) continue;
    drawChirp(ctx, localX, y0, h, track.minKhz, track.maxKhz, detection.fiKhz, detection.ftKhz, detection.posDUREE * 1.28, color);
  }
  ctx.fillStyle = color;
  ctx.fillRect(x0 + w - HANDLE_PX, y0, HANDLE_PX, h);
}

function drawImportedRows(
  ctx: CanvasRenderingContext2D,
  clip: ImportedClip,
  _x0: number,
  y0: number,
  height: number,
  minKhz: number,
  maxKhz: number,
  view: TimelineView,
  color: string
) {
  const store = importedStoreManager.get(clip.storeId);
  if (!store) return;
  const offset = clip.startMs - clip.originalStartMs;
  const visibleStart = view.scrollMs;
  const canvasWidth = ctx.canvas.clientWidth || ctx.canvas.width;
  const visibleEnd = view.scrollMs + canvasWidth / view.pxPerMs;
  for (let index = clip.rowStart; index < clip.rowEnd; index += 1) {
    const row = store.rows[index];
    const timeMs = row.timeMs + offset;
    if (timeMs < visibleStart || timeMs > visibleEnd) continue;
    const localX = HEADER_WIDTH + (timeMs - view.scrollMs) * view.pxPerMs;
    drawImportedChirp(ctx, row, store.metadata.binKhz, localX, y0, height, minKhz, maxKhz, color);
  }
}

function drawImportedChirp(
  ctx: CanvasRenderingContext2D,
  row: SensorDetectionRow,
  binKhz: number,
  x: number,
  y: number,
  height: number,
  minKhz: number,
  maxKhz: number,
  color: string
) {
  drawChirp(ctx, x, y, height, minKhz, maxKhz, row.posFI * binKhz, row.posFT * binKhz, row.posDUREE * 1.28, color);
}

function drawChirp(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  height: number,
  minKhz: number,
  maxKhz: number,
  fiKhz: number,
  ftKhz: number,
  durationMs: number,
  color: string
) {
  const k = 3.5;
  const pxDuration = Math.max(4, durationMs * 0.6);
  ctx.beginPath();
  for (let step = 0; step <= 8; step += 1) {
    const ratio = step / 8;
    const freq = ftKhz + (fiKhz - ftKhz) * Math.exp(-k * ratio);
    const yy = y + (1 - (freq - minKhz) / (maxKhz - minKhz)) * height;
    const xx = x + ratio * pxDuration;
    if (step === 0) ctx.moveTo(xx, yy);
    else ctx.lineTo(xx, yy);
  }
  ctx.strokeStyle = color;
  ctx.stroke();
}

function chooseGridStep(pxPerMs: number): number {
  if (pxPerMs > 0.2) return 100;
  if (pxPerMs > 0.04) return 1000;
  if (pxPerMs > 0.006) return 10000;
  if (pxPerMs > 0.001) return 60000;
  return 600000;
}

function formatTime(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return h > 0 ? `${h}h${String(m).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`;
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}
