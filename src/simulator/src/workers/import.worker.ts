/// <reference lib="webworker" />

import { importSensorTxtAsClips } from "../lib/sensorFormat";

self.onmessage = (event: MessageEvent<{ type: "import-sensor-txt"; text: string; filename: string }>) => {
  if (event.data.type !== "import-sensor-txt") return;
  try {
    const result = importSensorTxtAsClips(event.data.text, { filename: event.data.filename });
    self.postMessage({ type: "imported-sensor-txt", result });
  } catch (error) {
    self.postMessage({ type: "import-error", message: error instanceof Error ? error.message : "Import impossible" });
  }
};

export {};
