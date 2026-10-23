// Form behavior: rows, examples, loading state, rebalance helpers, export buttons.
// Plain JavaScript, no framework; the page works without it except these conveniences.
(function () {
  'use strict';
  const body = document.getElementById('holdings-body');
  const template = document.getElementById('row-template');

  function addRow(values) {
    const clone = template.content.cloneNode(true);
    if (values) {
      const inputs = clone.querySelectorAll('input');
      inputs[0].value = values.ticker || '';
      inputs[1].value = values.shares || '';
      inputs[2].value = values.purchase_price || '';
      inputs[3].value = values.purchase_date || '';
    }
    body.appendChild(clone);
  }

  if (body && template) {
    document.getElementById('add-row').addEventListener('click', function () {
      addRow();
      const rows = body.querySelectorAll('.holding-row');
      rows[rows.length - 1].querySelector('input').focus();
    });

    body.addEventListener('click', function (e) {
      const btn = e.target.closest('.remove-row');
      if (!btn) return;
      const rows = body.querySelectorAll('.holding-row');
      if (rows.length > 1) {
        btn.closest('tr').remove();
      } else {
        rows[0].querySelectorAll('input').forEach(function (i) { i.value = ''; });
      }
    });

    document.querySelectorAll('.example-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        const ex = (window.EXAMPLES || []).find(function (x) { return x.id === btn.dataset.example; });
        if (!ex) return;
        body.innerHTML = '';
        ex.holdings.forEach(addRow);
        document.getElementById('holdings-form').scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    });

    document.getElementById('holdings-form').addEventListener('submit', function () {
      const btn = document.getElementById('analyze-btn');
      btn.querySelector('.btn-label').hidden = true;
      btn.querySelector('.btn-spinner').hidden = false;
      btn.disabled = true;
    });
  }

  // ---- rebalance helpers ----
  const targets = Array.from(document.querySelectorAll('.target-input'));
  const sumEl = document.getElementById('target-sum');
  function updateSum() {
    if (!sumEl) return;
    const total = targets.reduce(function (acc, i) {
      const v = parseFloat(String(i.value).replace('%', ''));
      return acc + (isFinite(v) ? v : 0);
    }, 0);
    sumEl.textContent = total.toFixed(1) + '%';
    const ok = Math.abs(total - 100) <= 0.5;
    sumEl.className = 'sum-indicator ' + (ok ? 'ok' : 'off');
  }
  targets.forEach(function (i) { i.addEventListener('input', updateSum); });
  const equalBtn = document.getElementById('equal-weight');
  if (equalBtn) {
    equalBtn.addEventListener('click', function () {
      const each = Math.floor((100 / targets.length) * 10) / 10;
      targets.forEach(function (i, idx) {
        i.value = idx === 0 ? (100 - each * (targets.length - 1)).toFixed(1) : each.toFixed(1);
      });
      updateSum();
    });
  }
  const resetBtn = document.getElementById('reset-weights');
  if (resetBtn) {
    resetBtn.addEventListener('click', function () {
      targets.forEach(function (i) { i.value = i.dataset.current; });
      updateSum();
    });
  }
  updateSum();

  // ---- export buttons ----
  const printBtn = document.getElementById('print-btn');
  if (printBtn) printBtn.addEventListener('click', function () { window.print(); });

  const copyBtn = document.getElementById('copy-summary-btn');
  if (copyBtn && window.SUMMARY_TEXT) {
    copyBtn.addEventListener('click', function () {
      navigator.clipboard.writeText(window.SUMMARY_TEXT).then(function () {
        const c = document.getElementById('copy-confirm');
        c.hidden = false;
        setTimeout(function () { c.hidden = true; }, 2000);
      });
    });
  }

  const dlBtn = document.getElementById('download-json-btn');
  if (dlBtn && window.EXPORT_JSON) {
    dlBtn.addEventListener('click', function () {
      const blob = new Blob([JSON.stringify(window.EXPORT_JSON, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'portfolio-analysis.json';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    });
  }
})();
