import type { GenerationSettings, ScenarioProject, SpeciesTemplate, Track } from "./types";

export const SPECIES_TEMPLATES: SpeciesTemplate[] = [
  {
    id: "pip-kuhl",
    commonName: "Pipistrelle de Kuhl",
    latinName: "Pipistrellus kuhlii",
    color: "#4ea1ff",
    fmeRangeKhz: [36, 38],
    fiOffsetKhz: [2, 8],
    ftOffsetKhz: [1, 4],
    durationMs: [4, 8],
    iciMs: [130, 240]
  },
  {
    id: "pip-common",
    commonName: "Pipistrelle commune",
    latinName: "Pipistrellus pipistrellus",
    color: "#ffd166",
    fmeRangeKhz: [45, 48],
    fiOffsetKhz: [2, 7],
    ftOffsetKhz: [1, 3],
    durationMs: [4, 8],
    iciMs: [90, 180]
  },
  {
    id: "pip-pygmy",
    commonName: "Pipistrelle pygmee",
    latinName: "Pipistrellus pygmaeus",
    color: "#9b8cff",
    fmeRangeKhz: [53, 58],
    fiOffsetKhz: [2, 7],
    ftOffsetKhz: [1, 3],
    durationMs: [3, 7],
    iciMs: [80, 160]
  },
  {
    id: "serotine",
    commonName: "Serotine commune",
    latinName: "Eptesicus serotinus",
    color: "#2dd4bf",
    fmeRangeKhz: [25, 28],
    fiOffsetKhz: [4, 12],
    ftOffsetKhz: [1, 5],
    durationMs: [8, 16],
    iciMs: [180, 360]
  },
  {
    id: "molosse",
    commonName: "Molosse de Cestoni",
    latinName: "Tadarida teniotis",
    color: "#ff8fab",
    fmeRangeKhz: [10, 14],
    fiOffsetKhz: [1, 4],
    ftOffsetKhz: [1, 3],
    durationMs: [8, 20],
    iciMs: [200, 500]
  },
  {
    id: "noctule",
    commonName: "Noctule",
    latinName: "Nyctalus sp.",
    color: "#a3e635",
    fmeRangeKhz: [20, 26],
    fiOffsetKhz: [4, 12],
    ftOffsetKhz: [1, 5],
    durationMs: [8, 18],
    iciMs: [180, 420]
  }
];

export const DEFAULT_GENERATION: GenerationSettings = {
  durationHours: 11,
  densityPerHour: 120,
  noiseLevel: 0.12,
  echoProbability: 0.18,
  activityProfile: "dusk_dawn",
  speciesMix: {
    "pip-kuhl": 0.75,
    "pip-common": 0,
    "pip-pygmy": 0.25,
    serotine: 0,
    molosse: 0,
    noctule: 0
  }
};

export const DEFAULT_TRACKS: Track[] = [
  { id: "track-low", name: "Basses frequences", minKhz: 5, maxKhz: 24, clipIds: [] },
  { id: "track-mid", name: "Frequences medianes", minKhz: 18, maxKhz: 42, clipIds: [] },
  { id: "track-high", name: "Hautes frequences", minKhz: 36, maxKhz: 65, clipIds: [] }
];

export function createEmptyProject(): ScenarioProject {
  return {
    schemaVersion: 1,
    id: crypto.randomUUID(),
    name: "scenario",
    durationMs: DEFAULT_GENERATION.durationHours * 60 * 60 * 1000,
    tracks: DEFAULT_TRACKS.map((track) => ({ ...track, clipIds: [] })),
    clips: [],
    generation: cloneDefaultGeneration(),
    updatedAt: new Date().toISOString()
  };
}

export function speciesById(id: string): SpeciesTemplate {
  return SPECIES_TEMPLATES.find((species) => species.id === id) ?? SPECIES_TEMPLATES[0];
}

function cloneDefaultGeneration() {
  return {
    ...DEFAULT_GENERATION,
    speciesMix: { ...DEFAULT_GENERATION.speciesMix }
  };
}
