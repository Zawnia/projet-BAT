(function (root) {
  "use strict";

  const SQRT_2PI = Math.sqrt(2 * Math.PI);

  function mean(values) {
    return values.reduce((sum, value) => sum + value, 0) / values.length;
  }

  function variance(values, center) {
    return values.reduce((sum, value) => sum + (value - center) ** 2, 0) / Math.max(1, values.length - 1);
  }

  function quantile(sorted, q) {
    const position = (sorted.length - 1) * q;
    const base = Math.floor(position);
    const rest = position - base;
    return sorted[base + 1] === undefined ? sorted[base] : sorted[base] + rest * (sorted[base + 1] - sorted[base]);
  }

  function linspace(min, max, size) {
    if (size <= 1) return [min];
    const step = (max - min) / (size - 1);
    return Array.from({ length: size }, (_, i) => min + i * step);
  }

  function extent(values) {
    let min = Infinity;
    let max = -Infinity;
    for (const value of values) {
      if (value < min) min = value;
      if (value > max) max = value;
    }
    return { min, max };
  }

  function maxValue(values) {
    let max = -Infinity;
    for (const value of values) if (value > max) max = value;
    return max;
  }

  function normalPdf(x, mu, sigma) {
    const safeSigma = Math.max(sigma, 1e-6);
    const z = (x - mu) / safeSigma;
    return Math.exp(-0.5 * z * z) / (safeSigma * SQRT_2PI);
  }

  function bandwidth(values, method, scale) {
    const sorted = [...values].sort((a, b) => a - b);
    const sd = Math.sqrt(Math.max(variance(values, mean(values)), 1e-9));
    const n = values.length;
    if (method === "silverman") {
      const iqr = quantile(sorted, 0.75) - quantile(sorted, 0.25);
      const robust = Math.min(sd, iqr > 0 ? iqr / 1.34 : sd);
      return Math.max(0.05, 0.9 * robust * n ** -0.2 * scale);
    }
    return Math.max(0.05, sd * n ** -0.2 * scale);
  }

  function computeKde(values, options) {
    const { min, max } = extent(values);
    const pad = Math.max(0.5, (max - min) * 0.02);
    const grid = linspace(min - pad, max + pad, options.gridSize);
    const h = bandwidth(values, options.bandwidthMethod, options.bandwidthScale);
    const density = grid.map((x) => {
      let sum = 0;
      for (const value of values) sum += Math.exp(-0.5 * ((x - value) / h) ** 2);
      return sum / (values.length * h * SQRT_2PI);
    });
    return { grid, density, bandwidth: h };
  }

  function findPeaks(grid, density, prominenceRatio) {
    const maxDensity = maxValue(density);
    const minProminence = maxDensity * prominenceRatio;
    const candidates = [];
    for (let i = 1; i < density.length - 1; i += 1) {
      if (density[i] > density[i - 1] && density[i] >= density[i + 1]) {
        candidates.push(i);
      }
    }
    const peaks = candidates.filter((index, position) => {
      const leftBound = position === 0 ? 0 : candidates[position - 1];
      const rightBound = position === candidates.length - 1 ? density.length - 1 : candidates[position + 1];
      let leftMin = Infinity;
      let rightMin = Infinity;
      for (let i = leftBound; i <= index; i += 1) leftMin = Math.min(leftMin, density[i]);
      for (let i = index; i <= rightBound; i += 1) rightMin = Math.min(rightMin, density[i]);
      return density[index] - Math.max(leftMin, rightMin) >= minProminence;
    });
    return peaks.map((index) => ({ index, x: grid[index], y: density[index] }));
  }

  function initializeFromPeaks(values, peaks, k) {
    const sortedPeaks = peaks.map((peak) => peak.x).sort((a, b) => a - b);
    const sortedValues = [...values].sort((a, b) => a - b);
    const globalMean = mean(values);
    const globalSigma = Math.sqrt(Math.max(variance(values, globalMean), 0.05));
    const means = [];
    for (let i = 0; i < k; i += 1) {
      means.push(sortedPeaks[i] ?? quantile(sortedValues, (i + 1) / (k + 1)));
    }
    return {
      means,
      sigmas: Array.from({ length: k }, () => Math.max(globalSigma / Math.sqrt(k), 0.15)),
      weights: Array.from({ length: k }, () => 1 / k),
    };
  }

  function fitGmm(values, peaks, k, maxIter) {
    const n = values.length;
    let { means, sigmas, weights } = initializeFromPeaks(values, peaks, k);
    let lastLogLikelihood = -Infinity;
    const responsibilities = Array.from({ length: n }, () => Array(k).fill(0));

    for (let iter = 0; iter < maxIter; iter += 1) {
      let logLikelihood = 0;
      for (let i = 0; i < n; i += 1) {
        let total = 0;
        for (let j = 0; j < k; j += 1) {
          const value = weights[j] * normalPdf(values[i], means[j], sigmas[j]);
          responsibilities[i][j] = value;
          total += value;
        }
        if (total <= 0 || !Number.isFinite(total)) total = 1e-12;
        for (let j = 0; j < k; j += 1) responsibilities[i][j] /= total;
        logLikelihood += Math.log(total);
      }

      const effective = Array(k).fill(0);
      const nextMeans = Array(k).fill(0);
      const nextSigmas = Array(k).fill(0);
      for (let i = 0; i < n; i += 1) {
        for (let j = 0; j < k; j += 1) {
          effective[j] += responsibilities[i][j];
          nextMeans[j] += responsibilities[i][j] * values[i];
        }
      }
      for (let j = 0; j < k; j += 1) {
        if (effective[j] < 1e-6) {
          nextMeans[j] = means[j];
          effective[j] = 1e-6;
        } else {
          nextMeans[j] /= effective[j];
        }
      }
      for (let i = 0; i < n; i += 1) {
        for (let j = 0; j < k; j += 1) {
          nextSigmas[j] += responsibilities[i][j] * (values[i] - nextMeans[j]) ** 2;
        }
      }
      for (let j = 0; j < k; j += 1) {
        nextSigmas[j] = Math.sqrt(Math.max(nextSigmas[j] / effective[j], 0.05 ** 2));
      }

      means = nextMeans;
      sigmas = nextSigmas;
      weights = effective.map((value) => value / n);
      if (Math.abs(logLikelihood - lastLogLikelihood) < 1e-5 * Math.max(1, Math.abs(logLikelihood))) break;
      lastLogLikelihood = logLikelihood;
    }

    const order = means.map((value, index) => ({ value, index })).sort((a, b) => a.value - b.value).map((item) => item.index);
    return {
      means: order.map((index) => means[index]),
      sigmas: order.map((index) => sigmas[index]),
      weights: order.map((index) => weights[index]),
    };
  }

  function mixtureDensity(x, model) {
    let total = 0;
    for (let i = 0; i < model.means.length; i += 1) {
      total += model.weights[i] * normalPdf(x, model.means[i], model.sigmas[i]);
    }
    return total;
  }

  function thresholds(model) {
    const result = [];
    for (let i = 0; i < model.means.length - 1; i += 1) {
      const left = model.means[i];
      const right = model.means[i + 1];
      let bestX = left;
      let bestY = Infinity;
      for (const x of linspace(left, right, 160)) {
        const y = mixtureDensity(x, model);
        if (y < bestY) {
          bestY = y;
          bestX = x;
        }
      }
      result.push(bestX);
    }
    return result;
  }

  function predict(values, model) {
    return values.map((value) => {
      let best = 0;
      let bestScore = -Infinity;
      for (let i = 0; i < model.means.length; i += 1) {
        const score = model.weights[i] * normalPdf(value, model.means[i], model.sigmas[i]);
        if (score > bestScore) {
          bestScore = score;
          best = i;
        }
      }
      return best;
    });
  }

  function clusterFme(values, options) {
    if (values.length < 3) throw new Error("Trop peu de points pour le clustering");
    const kde = computeKde(values, options);
    const peaks = findPeaks(kde.grid, kde.density, options.peakProminenceRatio);
    const k = Math.max(1, Math.min(options.maxComponents, peaks.length || 1));
    const model = fitGmm(values, peaks, k, options.maxIter);
    const labels = predict(values, model);
    const counts = Array(k).fill(0);
    for (const label of labels) counts[label] += 1;
    const componentGrid = kde.grid.map((x) => ({
      x,
      mixture: mixtureDensity(x, model),
      components: model.means.map((_, i) => model.weights[i] * normalPdf(x, model.means[i], model.sigmas[i])),
    }));

    return {
      K: k,
      kde,
      peaks,
      model,
      thresholds: thresholds(model),
      labels,
      counts,
      componentGrid,
    };
  }

  root.BatClustering = { clusterFme, normalPdf, mixtureDensity };
  if (typeof module !== "undefined") module.exports = root.BatClustering;
})(typeof window !== "undefined" ? window : globalThis);
