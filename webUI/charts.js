(function (root) {
  "use strict";

  const COLORS = ["#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c", "#0891b2", "#be123c", "#4d7c0f"];

  function histogram(values, bins, min, max) {
    const counts = Array(bins).fill(0);
    const width = (max - min) / bins || 1;
    for (const value of values) {
      const index = Math.min(bins - 1, Math.max(0, Math.floor((value - min) / width)));
      counts[index] += 1;
    }
    return counts.map((count, i) => ({
      x0: min + i * width,
      x1: min + (i + 1) * width,
      density: count / (values.length * width),
    }));
  }

  function fitCanvas(canvas) {
    const rect = canvas.getBoundingClientRect();
    const ratio = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.floor(rect.width * ratio));
    canvas.height = Math.max(1, Math.floor(rect.height * ratio));
    const ctx = canvas.getContext("2d");
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    return { ctx, width: rect.width, height: rect.height };
  }

  function drawPath(ctx, points, mapX, mapY) {
    if (points.length === 0) return;
    ctx.beginPath();
    ctx.moveTo(mapX(points[0].x), mapY(points[0].y));
    for (let i = 1; i < points.length; i += 1) ctx.lineTo(mapX(points[i].x), mapY(points[i].y));
    ctx.stroke();
  }

  function maxOf(items, selector) {
    let max = 0;
    for (const item of items) {
      const value = selector(item);
      if (value > max) max = value;
    }
    return max;
  }

  function drawGmmChart(canvas, values, result, options) {
    const { ctx, width, height } = fitCanvas(canvas);
    const margin = { left: 58, right: 20, top: 24, bottom: 46 };
    const plotWidth = Math.max(10, width - margin.left - margin.right);
    const plotHeight = Math.max(10, height - margin.top - margin.bottom);
    const xs = result.kde.grid;
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const hist = histogram(values, options.histogramBins, minX, maxX);
    const yMax = Math.max(
      maxOf(hist, (item) => item.density),
      maxOf(result.kde.density, (item) => item),
      maxOf(result.componentGrid, (item) => item.mixture),
    ) * 1.12;
    const mapX = (x) => margin.left + ((x - minX) / (maxX - minX || 1)) * plotWidth;
    const mapY = (y) => margin.top + plotHeight - (y / (yMax || 1)) * plotHeight;

    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, width, height);

    ctx.strokeStyle = "#d9dee7";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(margin.left, margin.top);
    ctx.lineTo(margin.left, margin.top + plotHeight);
    ctx.lineTo(margin.left + plotWidth, margin.top + plotHeight);
    ctx.stroke();

    ctx.fillStyle = "#d6dbe3";
    for (const bar of hist) {
      const x = mapX(bar.x0);
      const w = Math.max(1, mapX(bar.x1) - x - 1);
      const y = mapY(bar.density);
      ctx.fillRect(x, y, w, margin.top + plotHeight - y);
    }

    for (let i = 0; i < result.model.means.length; i += 1) {
      ctx.strokeStyle = COLORS[i % COLORS.length];
      ctx.lineWidth = 1.6;
      drawPath(
        ctx,
        result.componentGrid.map((point) => ({ x: point.x, y: point.components[i] })),
        mapX,
        mapY,
      );
    }

    ctx.strokeStyle = "#111827";
    ctx.lineWidth = 2;
    drawPath(ctx, result.componentGrid.map((point) => ({ x: point.x, y: point.mixture })), mapX, mapY);

    ctx.strokeStyle = "#64748b";
    ctx.lineWidth = 1.5;
    ctx.setLineDash([5, 4]);
    drawPath(ctx, result.kde.grid.map((x, i) => ({ x, y: result.kde.density[i] })), mapX, mapY);
    ctx.setLineDash([]);

    for (const threshold of result.thresholds) {
      const x = mapX(threshold);
      ctx.strokeStyle = "#ef4444";
      ctx.lineWidth = 1;
      ctx.setLineDash([6, 4]);
      ctx.beginPath();
      ctx.moveTo(x, margin.top);
      ctx.lineTo(x, margin.top + plotHeight);
      ctx.stroke();
    }
    ctx.setLineDash([]);

    ctx.fillStyle = "#111827";
    for (const peak of result.peaks) {
      const x = mapX(peak.x);
      const y = mapY(peak.y);
      ctx.beginPath();
      ctx.moveTo(x - 5, y - 5);
      ctx.lineTo(x + 5, y + 5);
      ctx.moveTo(x + 5, y - 5);
      ctx.lineTo(x - 5, y + 5);
      ctx.strokeStyle = "#111827";
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }

    ctx.fillStyle = "#334155";
    ctx.font = "12px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    const tickCount = 6;
    for (let i = 0; i < tickCount; i += 1) {
      const value = minX + (i / (tickCount - 1)) * (maxX - minX);
      const x = mapX(value);
      ctx.strokeStyle = "#eef1f5";
      ctx.beginPath();
      ctx.moveTo(x, margin.top);
      ctx.lineTo(x, margin.top + plotHeight);
      ctx.stroke();
      ctx.fillText(value.toFixed(1), x, margin.top + plotHeight + 10);
    }
    ctx.save();
    ctx.translate(16, margin.top + plotHeight / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.textAlign = "center";
    ctx.fillText("Densite", 0, 0);
    ctx.restore();
    ctx.textAlign = "center";
    ctx.fillText("FME (kHz)", margin.left + plotWidth / 2, height - 22);
  }

  root.BatCharts = { drawGmmChart };
})(typeof window !== "undefined" ? window : globalThis);
