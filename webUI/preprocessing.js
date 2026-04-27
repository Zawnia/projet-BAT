(function (root) {
  "use strict";

  function take(data, indices) {
    const next = {};
    for (const key of Object.keys(data)) {
      next[key] = indices.map((index) => data[key][index]);
    }
    return next;
  }

  function filter(data, predicate) {
    const indices = [];
    const size = data.time_ms.length;
    for (let index = 0; index < size; index += 1) {
      if (predicate(index)) indices.push(index);
    }
    return take(data, indices);
  }

  function addFrequencyColumns(records, binKhz) {
    return {
      ...records,
      FME_kHz: records.posFME.map((value) => value * binKhz),
      FI_kHz: records.posFI.map((value) => value * binKhz),
      FT_kHz: records.posFT.map((value) => value * binKhz),
    };
  }

  function removeZeroArtefacts(data) {
    return filter(data, (i) => !(data.posFME[i] === 0 && data.SNR_dB[i] === 0 && data.duree_bins[i] === 0));
  }

  function addSequenceColumns(data, sequenceGapMs, suffix) {
    const order = data.time_ms.map((_, index) => index).sort((a, b) => data.time_ms[a] - data.time_ms[b]);
    const sorted = take(data, order);
    const gapKey = `gap_ms${suffix}`;
    const seqKey = `seq_id${suffix}`;
    sorted[gapKey] = [];
    sorted[seqKey] = [];
    let sequence = 0;
    for (let i = 0; i < sorted.time_ms.length; i += 1) {
      const gap = i === 0 ? NaN : sorted.time_ms[i] - sorted.time_ms[i - 1];
      if (i === 0 || gap >= sequenceGapMs) sequence += 1;
      sorted[gapKey].push(gap);
      sorted[seqKey].push(sequence);
    }
    return sorted;
  }

  function removeEchoes(data, echoGapMs, echoFmeBins) {
    const delta = [];
    const keep = [];
    let echoCount = 0;
    for (let i = 0; i < data.posFME.length; i += 1) {
      const value = i === 0 ? NaN : Math.abs(data.posFME[i] - data.posFME[i - 1]);
      const isEcho = data.gap_ms[i] <= echoGapMs && value <= echoFmeBins;
      delta.push(value);
      keep.push(!isEcho);
      if (isEcho) echoCount += 1;
    }
    const withDelta = { ...data, delta_FME_bins: delta };
    return {
      data: filter(withDelta, (i) => keep[i]),
      echoCount,
    };
  }

  function uniqueCount(values) {
    return new Set(values).size;
  }

  function preprocessBatData(parsed, options) {
    const data = addFrequencyColumns(parsed.records, parsed.metadata.bin_khz);
    const clean = removeZeroArtefacts(data);
    if (clean.time_ms.length === 0) throw new Error("Aucune detection apres suppression des artefacts");

    const sequenced = addSequenceColumns(clean, options.sequenceGapMs, "");
    const withoutEchoes = removeEchoes(sequenced, options.echoGapMs, options.echoFmeBins);
    const noEcho = addSequenceColumns(withoutEchoes.data, options.sequenceGapMs, "2");
    const clustered = filter(noEcho, (i) => noEcho.FME_kHz[i] > options.fmeMinKhz);
    if (clustered.time_ms.length < 3) throw new Error("Trop peu de detections apres filtrage FME");

    const stats = {
      n_raw: parsed.records.time_ms.length,
      n_artefacts: parsed.records.time_ms.length - clean.time_ms.length,
      n_clean: clean.time_ms.length,
      n_echoes: withoutEchoes.echoCount,
      n_no_echo: noEcho.time_ms.length,
      n_filtered: clustered.time_ms.length,
      n_social: noEcho.time_ms.length - clustered.time_ms.length,
      n_sequences: uniqueCount(sequenced.seq_id),
      n_sequences_no_echo: uniqueCount(noEcho.seq_id2),
      fme_min_khz: options.fmeMinKhz,
      sequence_gap_ms: options.sequenceGapMs,
      echo_gap_ms: options.echoGapMs,
      echo_fme_bins: options.echoFmeBins,
      freq_khz_enreg: parsed.metadata.freq_khz_enreg,
      lenfft: parsed.metadata.lenfft,
      bin_khz: parsed.metadata.bin_khz,
    };
    return { fmeKhz: clustered.FME_kHz, detections: clustered, stats };
  }

  root.BatPreprocessing = { preprocessBatData };
  if (typeof module !== "undefined") module.exports = root.BatPreprocessing;
})(typeof window !== "undefined" ? window : globalThis);
