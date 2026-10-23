// Charts (Chart.js). Colors come from CSS custom properties so light/dark mode
// and print stay consistent. Palette: colorblind-validated blue/orange pair;
// SPY is also dashed so identity never relies on color alone.
(function () {
  'use strict';
  const D = window.CHART_DATA;
  if (!D || typeof Chart === 'undefined') return;

  const css = getComputedStyle(document.documentElement);
  const v = function (name) { return css.getPropertyValue(name).trim(); };
  const C = {
    s1: v('--series-1'), s2: v('--series-2'), ink: v('--ink-2'), muted: v('--muted'),
    grid: v('--line'), axis: v('--line-strong'), surface: v('--surface'),
  };

  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.color = C.ink;
  Chart.defaults.borderColor = C.grid;
  Chart.defaults.maintainAspectRatio = false;
  Chart.defaults.animation = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? false : { duration: 400 };

  const money = function (x) { return '$' + Math.round(x).toLocaleString(); };
  const pct = function (x, d) { return x.toFixed(d === undefined ? 1 : d) + '%'; };

  function xTicks(dates) {
    // show ~6 date labels as "Mon YYYY"
    const step = Math.max(1, Math.floor(dates.length / 6));
    return {
      autoSkip: false, maxRotation: 0,
      callback: function (val, idx) {
        if (idx % step !== 0) return '';
        const d = new Date(dates[idx] + 'T00:00:00');
        return d.toLocaleDateString(undefined, { month: 'short', year: 'numeric' });
      },
    };
  }

  function lineDatasets(block, fmtLabel) {
    const sets = [{
      label: 'Your portfolio', data: block.portfolio, borderColor: C.s1, backgroundColor: C.s1,
      borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: 0,
    }];
    if (block.benchmark && block.benchmark.length) {
      sets.push({
        label: 'S&P 500 (SPY)', data: block.benchmark, borderColor: C.s2, backgroundColor: C.s2,
        borderWidth: 2, borderDash: [6, 4], pointRadius: 0, pointHoverRadius: 4, tension: 0, spanGaps: true,
      });
    }
    return sets;
  }

  function lineChart(id, block, yFmt, extraY) {
    const el = document.getElementById(id);
    if (!el || !block || !block.dates || !block.dates.length) return;
    new Chart(el, {
      type: 'line',
      data: { labels: block.dates, datasets: lineDatasets(block) },
      options: {
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { position: 'top', align: 'start', labels: { usePointStyle: true, pointStyle: 'line', boxWidth: 24 } },
          tooltip: {
            callbacks: {
              title: function (items) { return items[0].label; },
              label: function (ctx) { return ctx.dataset.label + ': ' + yFmt(ctx.parsed.y); },
            },
          },
        },
        scales: {
          x: { grid: { display: false }, border: { color: C.axis }, ticks: xTicks(block.dates) },
          y: Object.assign({ grid: { color: C.grid }, border: { display: false }, ticks: { callback: yFmt } }, extraY || {}),
        },
      },
    });
  }

  lineChart('growthChart', D.growth, money);
  lineChart('drawdownChart', D.drawdown, function (x) { return pct(x, 0); }, { max: 0 });

  function barChart(id, block, tooltipExtra) {
    const el = document.getElementById(id);
    if (!el || !block || !block.labels || !block.labels.length) return;
    // more categories -> taller box so labels never collide
    el.parentElement.style.height = Math.max(160, 36 * block.labels.length + 40) + 'px';
    new Chart(el, {
      type: 'bar',
      data: {
        labels: block.labels,
        datasets: [{ label: '% of portfolio', data: block.values, backgroundColor: C.s1,
          borderRadius: 4, borderSkipped: 'start', maxBarThickness: 22 }],
      },
      options: {
        indexAxis: 'y',
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: function (ctx) {
            return pct(ctx.parsed.x) + (tooltipExtra ? tooltipExtra(ctx.dataIndex) : '');
          } } },
        },
        scales: {
          x: { beginAtZero: true, grid: { color: C.grid }, border: { display: false }, ticks: { callback: function (x) { return x + '%'; } } },
          y: { grid: { display: false }, border: { color: C.axis } },
        },
      },
    });
  }

  barChart('allocationChart', D.allocation, function (i) {
    return D.allocation.dollars ? ' (' + money(D.allocation.dollars[i]) + ')' : '';
  });
  barChart('sectorChart', D.sectors);
  barChart('assetClassChart', D.asset_classes);

  // ---- correlation heatmap as an accessible HTML table ----
  const corrDiv = document.getElementById('correlationTable');
  if (corrDiv && D.correlation) {
    const tickers = Object.keys(D.correlation);
    // diverging: blue (-1) -> neutral gray (0) -> red (+1)
    const NEG = [42, 120, 214], MID = [240, 239, 236], POS = [227, 73, 72];
    const mix = function (a, b, t) { return a.map(function (x, i) { return Math.round(x + (b[i] - x) * t); }); };
    const esc = function (s) { return String(s).replace(/[&<>"]/g, function (c) { return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]; }); };
    let html = '<table class="heatmap"><caption class="sr-only">Correlation of daily returns between each pair of holdings, from -1 to 1</caption><thead><tr><th scope="col"><span class="sr-only">Ticker</span></th>' +
      tickers.map(function (t) { return '<th scope="col">' + esc(t) + '</th>'; }).join('') + '</tr></thead><tbody>';
    tickers.forEach(function (rowT) {
      html += '<tr><th scope="row">' + esc(rowT) + '</th>';
      tickers.forEach(function (colT) {
        const val = D.correlation[rowT][colT];
        if (val === null || val === undefined || isNaN(val)) { html += '<td>–</td>'; return; }
        const rgb = val >= 0 ? mix(MID, POS, Math.min(1, val)) : mix(MID, NEG, Math.min(1, -val));
        const ink = Math.abs(val) > 0.55 ? '#ffffff' : '#0b0b0b';
        html += '<td style="background:rgb(' + rgb.join(',') + ');color:' + ink + '" title="' +
          esc(rowT) + ' vs ' + esc(colT) + ': ' + val.toFixed(2) + '">' + val.toFixed(2) + '</td>';
      });
      html += '</tr>';
    });
    corrDiv.innerHTML = html + '</tbody></table>';
  }
})();
