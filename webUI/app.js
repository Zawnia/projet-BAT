(function () {
  "use strict";

  const DEFAULTS = {
    fmeMinKhz: 18,
    sequenceGapMs: 100,
    echoGapMs: 10,
    echoFmeBins: 1,
    bandwidthMethod: "scott",
    bandwidthScale: 1,
    peakProminenceRatio: 0.05,
    gridSize: 1000,
    maxComponents: 8,
    maxIter: 120,
    histogramBins: 80,
  };

  const state = {
    parsed: null,
    fileName: "",
    last: null,
  };

  const els = {};

  function $(id) {
    return document.getElementById(id);
  }

  function readOptions() {
    return {
      fmeMinKhz: Number(els.fmeMinKhz.value),
      sequenceGapMs: Number(els.sequenceGapMs.value),
      echoGapMs: Number(els.echoGapMs.value),
      echoFmeBins: Number(els.echoFmeBins.value),
      bandwidthMethod: els.bandwidthMethod.value,
      bandwidthScale: Number(els.bandwidthScale.value),
      peakProminenceRatio: Number(els.peakProminenceRatio.value),
      gridSize: DEFAULTS.gridSize,
      maxComponents: DEFAULTS.maxComponents,
      maxIter: DEFAULTS.maxIter,
      histogramBins: Number(els.histogramBins.value),
    };
  }

  function formatNumber(value, digits = 2) {
    if (!Number.isFinite(value)) return "-";
    return value.toLocaleString("fr-FR", { maximumFractionDigits: digits, minimumFractionDigits: digits });
  }

  function setStatus(message, tone) {
    els.status.textContent = message;
    els.status.dataset.tone = tone || "neutral";
  }

  function updateParamLabels() {
    els.fmeMinKhzValue.textContent = `${formatNumber(Number(els.fmeMinKhz.value), 1)} kHz`;
    els.sequenceGapMsValue.textContent = `${formatNumber(Number(els.sequenceGapMs.value), 0)} ms`;
    els.echoGapMsValue.textContent = `${formatNumber(Number(els.echoGapMs.value), 0)} ms`;
    els.echoFmeBinsValue.textContent = `${formatNumber(Number(els.echoFmeBins.value), 1)} bins`;
    els.bandwidthScaleValue.textContent = `x${formatNumber(Number(els.bandwidthScale.value), 2)}`;
    els.peakProminenceRatioValue.textContent = `${formatNumber(Number(els.peakProminenceRatio.value) * 100, 1)} %`;
    els.histogramBinsValue.textContent = `${Number(els.histogramBins.value)} bins`;
  }

  function renderStats(stats, result) {
    const items = [
      ["Detections brutes", stats.n_raw],
      ["Artefacts retires", stats.n_artefacts],
      ["Detections clean", stats.n_clean],
      ["Echos retires", stats.n_echoes],
      ["Sans echo", stats.n_no_echo],
      ["Cris sociaux retires", stats.n_social],
      ["Clusterisees", stats.n_filtered],
      ["Sequences clean", stats.n_sequences],
      ["Sequences sans echo", stats.n_sequences_no_echo],
      ["Resolution FFT", `${formatNumber(stats.bin_khz, 6)} kHz/bin`],
      ["K detecte", result.K],
      ["Bande passante KDE", `${formatNumber(result.kde.bandwidth, 3)} kHz`],
    ];
    els.statsGrid.innerHTML = items.map(([label, value]) => `
      <div class="metric">
        <span>${label}</span>
        <strong>${value}</strong>
      </div>
    `).join("");
  }

  function renderClusters(fme, result) {
    els.clusterBody.innerHTML = result.model.means.map((mean, index) => {
      const count = result.counts[index];
      const pct = count / fme.length;
      return `
        <tr>
          <td><span class="swatch" style="background:${["#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c", "#0891b2", "#be123c", "#4d7c0f"][index % 8]}"></span>${index}</td>
          <td>${count.toLocaleString("fr-FR")}</td>
          <td>${formatNumber(pct * 100, 2)} %</td>
          <td>${result.model.species[index]}</td>
          <td>${formatNumber(result.model.medians[index], 3)}</td>
          <td>${formatNumber(mean, 3)}</td>
          <td>${formatNumber(result.model.sigmas[index], 3)}</td>
          <td>${formatNumber(result.model.weights[index], 3)}</td>
        </tr>
      `;
    }).join("");
    els.peaksText.textContent = result.peaks.length
      ? result.peaks.map((peak) => formatNumber(peak.x, 2)).join(" ; ") + " kHz"
      : "aucun pic net";
    els.thresholdsText.textContent = result.thresholds.length
      ? result.thresholds.map((value) => formatNumber(value, 2)).join(" ; ") + " kHz"
      : "aucun seuil";
  }

  function recompute() {
    updateParamLabels();
    if (!state.parsed) return;
    try {
      setStatus("Calcul en cours...", "neutral");
      const options = readOptions();
      const preprocessing = window.BatPreprocessing.preprocessBatData(state.parsed, options);
      const result = window.BatClustering.clusterFme(preprocessing.fmeKhz, options);
      state.last = { preprocessing, result, options };
      renderStats(preprocessing.stats, result);
      renderClusters(preprocessing.fmeKhz, result);
      els.emptyState.hidden = true;
      els.results.hidden = false;
      window.BatCharts.drawGmmChart(els.chart, preprocessing.fmeKhz, result, options);
      setStatus(`${state.fileName} - ${preprocessing.fmeKhz.length.toLocaleString("fr-FR")} detections clusterisees`, "ok");
    } catch (error) {
      els.results.hidden = true;
      els.emptyState.hidden = false;
      setStatus(error.message, "error");
    }
  }

  function debounce(fn, delay) {
    let timer = null;
    return function debounced() {
      window.clearTimeout(timer);
      timer = window.setTimeout(fn, delay);
    };
  }

  function bindInput(id, key) {
    els[key] = $(id);
    els[`${key}Value`] = $(`${id}Value`);
    els[key].value = DEFAULTS[key];
  }

  async function handleFile(file) {
    if (!file) return;
    try {
      setStatus("Lecture du fichier...", "neutral");
      const text = await file.text();
      state.parsed = window.BatParser.parseBatTxt(text);
      state.fileName = file.name;
      recompute();
    } catch (error) {
      state.parsed = null;
      els.results.hidden = true;
      els.emptyState.hidden = false;
      setStatus(error.message, "error");
    }
  }

  function init() {
    els.status = $("status");
    els.fileInput = $("fileInput");
    els.results = $("results");
    els.emptyState = $("emptyState");
    els.statsGrid = $("statsGrid");
    els.clusterBody = $("clusterBody");
    els.peaksText = $("peaksText");
    els.thresholdsText = $("thresholdsText");
    els.chart = $("chart");
    els.bandwidthMethod = $("bandwidthMethod");
    bindInput("fmeMinKhz", "fmeMinKhz");
    bindInput("sequenceGapMs", "sequenceGapMs");
    bindInput("echoGapMs", "echoGapMs");
    bindInput("echoFmeBins", "echoFmeBins");
    bindInput("bandwidthScale", "bandwidthScale");
    bindInput("peakProminenceRatio", "peakProminenceRatio");
    bindInput("histogramBins", "histogramBins");

    els.bandwidthMethod.value = DEFAULTS.bandwidthMethod;
    const delayed = debounce(recompute, 160);
    document.querySelectorAll("input[type='range'], select").forEach((input) => {
      input.addEventListener("input", () => {
        updateParamLabels();
        delayed();
      });
      input.addEventListener("change", delayed);
    });
    els.fileInput.addEventListener("change", () => handleFile(els.fileInput.files[0]));
    window.addEventListener("resize", debounce(() => {
      if (state.last) {
        window.BatCharts.drawGmmChart(els.chart, state.last.preprocessing.fmeKhz, state.last.result, state.last.options);
      }
    }, 120));
    updateParamLabels();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
