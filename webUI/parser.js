(function (root) {
  "use strict";

  function parseNumberMetadata(lines, key) {
    const line = lines.find((item) => item.trim().startsWith(key));
    if (!line) throw new Error(`Metadonnee manquante: ${key}`);
    const value = Number(line.trim().split(/\s+/)[1]);
    if (!Number.isFinite(value) || value <= 0) {
      throw new Error(`Valeur invalide pour ${key}`);
    }
    return value;
  }

  function parseBatTxt(text) {
    const lines = text.replace(/\r/g, "").split("\n");
    const freqKhzEnreg = parseNumberMetadata(lines, "FREQ_KHZ_ENREG");
    const lenfft = parseNumberMetadata(lines, "LENFFT");
    const startIndex = lines.findIndex((line) => line.trim() === "DATAASCII");
    if (startIndex === -1) throw new Error("Bloc DATAASCII introuvable");

    const records = [];
    for (const line of lines.slice(startIndex + 3)) {
      const parts = line.trim().split(/\s+/);
      if (parts.length !== 6) continue;
      const values = parts.map(Number);
      if (values.every(Number.isInteger)) records.push(values);
    }
    if (records.length === 0) throw new Error("Aucune ligne de donnees exploitable");

    const columns = {
      time_ms: [],
      posFME: [],
      posFI: [],
      posFT: [],
      duree_bins: [],
      SNR_dB: [],
    };
    for (const [time, fme, fi, ft, duree, snr] of records) {
      columns.time_ms.push(time);
      columns.posFME.push(fme);
      columns.posFI.push(fi);
      columns.posFT.push(ft);
      columns.duree_bins.push(duree);
      columns.SNR_dB.push(snr);
    }

    const metadata = {
      freq_khz_enreg: freqKhzEnreg,
      lenfft,
      bin_khz: freqKhzEnreg / lenfft,
    };
    return { records: columns, metadata };
  }

  root.BatParser = { parseBatTxt };
  if (typeof module !== "undefined") module.exports = root.BatParser;
})(typeof window !== "undefined" ? window : globalThis);
