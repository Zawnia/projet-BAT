/// <reference lib="webworker" />

import { generateNight } from "../lib/generator";
import type { GenerationSettings } from "../lib/types";

export interface GenerateNightRequest {
  type: "generate-night";
  settings: GenerationSettings;
  seed: number;
}

self.onmessage = (event: MessageEvent<GenerateNightRequest>) => {
  if (event.data.type !== "generate-night") return;
  const project = generateNight(event.data.settings, event.data.seed);
  self.postMessage({ type: "generated-night", project });
};

export {};
