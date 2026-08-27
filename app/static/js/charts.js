(function () {
  if (typeof CHART_DATA === 'undefined' || !CHART_DATA) return;

  const palette = ['#4f8cff', '#3ecf8e', '#e8c547', '#ff9a4f', '#ff6b6b', '#a97fff', '#4fd1c5', '#f472b6'];
  const gridColor = '#2a2f3a';
  const textColor = '#9aa3b2';

  Chart.defaults.color = textColor;
  Chart.defaults.borderColor = gridColor;

  const allocEl = document.getElementById('allocationChart');
  if (allocEl && CHART_DATA.allocation && CHART_DATA.allocation.labels.length) {
    new Chart(allocEl, {
      type: 'doughnut',
      data: {
        labels: CHART_DATA.allocation.labels,
        datasets: [{ data: CHART_DATA.allocation.values, backgroundColor: palette }],
      },
      options: { plugins: { legend: { position: 'bottom', labels: { boxWidth: 12 } } } },
    });
  }

  const sectorEl = document.getElementById('sectorChart');
  if (sectorEl && CHART_DATA.sectors && CHART_DATA.sectors.labels.length) {
    new Chart(sectorEl, {
      type: 'bar',
      data: {
        labels: CHART_DATA.sectors.labels,
        datasets: [{ label: '% of portfolio', data: CHART_DATA.sectors.values, backgroundColor: palette }],
      },
      options: {
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, grid: { color: gridColor } }, x: { grid: { display: false } } },
      },
    });
  }

  const rebasedEl = document.getElementById('rebasedChart');
  const rebased = CHART_DATA.rebased;
  if (rebasedEl && rebased && rebased.dates && rebased.dates.length) {
    const datasets = Object.keys(rebased.series).map((ticker, i) => ({
      label: ticker,
      data: rebased.series[ticker],
      borderColor: palette[i % palette.length],
      backgroundColor: 'transparent',
      pointRadius: 0,
      borderWidth: 2,
      tension: 0.1,
    }));
    // Thin the x-axis labels so it isn't unreadable with 500 points
    const step = Math.max(1, Math.floor(rebased.dates.length / 8));
    new Chart(rebasedEl, {
      type: 'line',
      data: { labels: rebased.dates, datasets: datasets },
      options: {
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { position: 'bottom', labels: { boxWidth: 12 } } },
        scales: {
          y: { grid: { color: gridColor }, title: { display: true, text: 'Rebased to 100' } },
          x: { grid: { display: false }, ticks: { callback: function (val, idx) { return idx % step === 0 ? this.getLabelForValue(val) : ''; } } },
        },
      },
    });
  }

  const corrDiv = document.getElementById('correlationTable');
  if (corrDiv && CHART_DATA.correlation) {
    const tickers = Object.keys(CHART_DATA.correlation);
    let html = '<table><thead><tr><th></th>' + tickers.map(t => `<th>${t}</th>`).join('') + '</tr></thead><tbody>';
    tickers.forEach(rowT => {
      html += `<tr><th>${rowT}</th>`;
      tickers.forEach(colT => {
        const v = CHART_DATA.correlation[rowT][colT];
        const alpha = Math.min(1, Math.abs(v));
        const color = v >= 0 ? `rgba(255,107,107,${alpha * 0.6})` : `rgba(79,140,255,${alpha * 0.6})`;
        html += `<td style="background:${color}">${v.toFixed(2)}</td>`;
      });
      html += '</tr>';
    });
    html += '</tbody></table>';
    corrDiv.innerHTML = html;
  }
})();
