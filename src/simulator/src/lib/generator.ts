import { createClipFromSpecies, convertClipToNoise, pickTrackForSpecies } from "./detection";
import { Rng, hashSeed } from "./random";
import { createEmptyProject, SPECIES_TEMPLATES, speciesById } from "./species";
import type { Clip, GenerationSettings, Phase, ScenarioProject } from "./types";

const PHASES: Phase[] = ["transit", "chasse", "approche", "feeding_buzz"];

export function generateNight(settings: GenerationSettings, seed = Date.now()): ScenarioProject {
  const rng = new Rng(seed);
  const project = createEmptyProject();
  project.durationMs = settings.durationHours * 60 * 60 * 1000;
  project.generation = { ...settings, speciesMix: { ...settings.speciesMix } };
  const totalPassages = Math.max(1, Math.round(settings.durationHours * settings.densityPerHour));
  const clips: Clip[] = [];

  for (let index = 0; index < totalPassages; index += 1) {
    const species = speciesById(pickSpecies(settings, rng));
    const trackId = pickTrackForSpecies(project, species.id);
    const startMs = Math.round(sampleStartMs(project.durationMs, settings.activityProfile, rng));
    const clip = createClipFromSpecies(species, trackId, startMs);
    const phase = rng.pick(PHASES);
    const durationScale = phase === "feeding_buzz" ? 0.18 : phase === "approche" ? 0.55 : phase === "chasse" ? 0.85 : 1.25;
    const iciScale = phase === "feeding_buzz" ? 0.18 : phase === "approche" ? 0.5 : phase === "chasse" ? 0.85 : 1;
    const individualOffset = rng.normal(0, 1.2);
    const intraOffset = rng.normal(0, 0.35);
    const fmeKhz = clip.fmeKhz + individualOffset + intraOffset;
    clips.push({
      ...clip,
      phase,
      id: crypto.randomUUID(),
      individualId: `ind-${species.id}-${Math.max(1, Math.round(index / 3))}`,
      sequenceId: `seq-${index + 1}`,
      durationMs: Math.max(250, rng.logNormal(clip.durationMs * durationScale, 0.45)),
      iciMeanMs: Math.max(6, clip.iciMeanMs * iciScale),
      iciJitter: phase === "transit" ? 0.12 : phase === "feeding_buzz" ? 0.28 : 0.35,
      fmeKhz,
      fiKhz: fmeKhz + rng.range(species.fiOffsetKhz[0], species.fiOffsetKhz[1]),
      ftKhz: Math.max(5, fmeKhz - rng.range(species.ftOffsetKhz[0], species.ftOffsetKhz[1])),
      snrMeanDb: rng.range(21, 38),
      snrStdDb: rng.range(2, 6),
      echo: { ...clip.echo, probability: settings.echoProbability },
      seed: hashSeed(`${seed}:${index}:${species.id}`)
    });
  }

  const noiseCount = Math.round(totalPassages * settings.noiseLevel);
  for (let index = 0; index < noiseCount; index += 1) {
    const species = rng.pick(SPECIES_TEMPLATES);
    const clip = createClipFromSpecies(species, project.tracks[0].id, rng.range(0, project.durationMs));
    clips.push(
      convertClipToNoise({
        ...clip,
        speciesName: "Bruit basse frequence",
        speciesId: "noise-low",
        fmeKhz: rng.range(8, 19),
        fiKhz: rng.range(8, 20),
        ftKhz: rng.range(8, 20),
        durationMs: rng.range(250, 2500),
        seed: hashSeed(`${seed}:noise:${index}`)
      })
    );
  }

  project.clips = clips;
  project.tracks = project.tracks.map((track) => ({
    ...track,
    clipIds: clips.filter((clip) => clip.trackId === track.id).map((clip) => clip.id)
  }));
  project.updatedAt = new Date().toISOString();
  return project;
}

function pickSpecies(settings: GenerationSettings, rng: Rng): string {
  const entries = SPECIES_TEMPLATES.map((species) => [species.id, settings.speciesMix[species.id] ?? 0] as const);
  const total = entries.reduce((sum, [, weight]) => sum + Math.max(0, weight), 0) || 1;
  let cursor = rng.range(0, total);
  for (const [id, weight] of entries) {
    cursor -= Math.max(0, weight);
    if (cursor <= 0) return id;
  }
  return entries[0][0];
}

function sampleStartMs(durationMs: number, profile: GenerationSettings["activityProfile"], rng: Rng): number {
  if (profile === "uniform") return rng.range(0, durationMs);
  const peak = rng.next() < 0.5 ? 0.08 : 0.92;
  const normalized = Math.min(1, Math.max(0, rng.normal(peak, 0.09)));
  return normalized * durationMs;
}
