import type { Clip, GeneratedClip, ImportedClip } from "./types";

export function isImportedClip(clip: Clip): clip is ImportedClip {
  return clip.kind === "imported";
}

export function isGeneratedClip(clip: Clip): clip is GeneratedClip {
  return clip.kind === "sequence" || clip.kind === "noise";
}
