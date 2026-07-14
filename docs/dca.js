const DCA_COLORS = {
  A: '#64748b',
  B: '#dc2626',
  C: '#2563eb',
  D: '#ea580c',
};

let dcaData = null;
let dcaChartInstance = null;

function fmt(n) { return typeof n === 'number' ? n.toFixed(2) : '-'; }
function fmtCurrency(n) {
  if (typeof n !== 'number') return '-';
  const abs = Math.abs(n).toLocaleString('en-US', { maximumFractionDigits: 0 });
  if (n > 0) return `+${abs}`;
  if (n < 0) return `-${abs}`;
  return `${abs}`;
}
function fmtPct(n) {
  if (typeof n !== 'number') return '-';
  const sign = n > 0 ? '+' : '';
  return `${sign}${n.toFixed(2)}%`;
}
function formatUpdatedAt(isoUtc) {
  if (!isoUtc) return '-';
  const d = new Date(isoUtc);
  const pad = (v) => String(v).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
function getChartColors() {
  const styles = getComputedStyle(document.documentElement);
  return {
    grid: styles.getPropertyValue('--border').trim() || '#e5e7eb',
    text: styles.getPropertyValue('--text-muted').trim() || '#6b7280',
  };
}

async function loadDCA() {
  try {
    const resp = await fetch(`./dca_comparison.json?t=${Date.now()}`, { cache: 'no-store' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    dcaData = await resp.json();
    renderAll();
  } catch (err) {
    console.error('Failed to load dca_comparison.json:', err);
  }
}

function renderAll() {
  const data = dcaData;
  const updatedEl = document.getElementById('updated-line');
  if (updatedEl) updatedEl.textContent = `資料更新於：${formatUpdatedAt(data.updated_at)}（本地時間）`;

  renderCards(data);
  renderSummaryTable(data);
  renderChart(data);
  renderTable(data);
  renderEventsLog(data);
}

function renderEventsLog(data) {
  const scenA = (data.scenarios || []).find((s) => s.key === 'A');
  if (!scenA) return;
  const dividends = scenA.dividends_log || [];
  const splits = scenA.splits_log || [];
  if (!dividends.length && !splits.length) return;

  const eventsCard = document.getElementById('dca-events-card');
  const body = document.getElementById('dca-events-body');
  if (!eventsCard || !body) return;
  eventsCard.hidden = false;

  const totalDiv = scenA.total_dividends_received || 0;
  let html = `
    <div class="metric-block">
      <h5>累計配息</h5>
      <div class="muted small" style="margin-bottom: 0.6rem;">
        除息 ${dividends.length} 次｜累計收到 <strong>${fmtCurrency(totalDiv)}</strong>（下月月初一起投入本金）
      </div>
      <div class="pivot-wrapper">
        <table class="pivot-table" style="font-size: 0.85rem;">
          <thead><tr><th>除息日</th><th>每股</th><th>持股</th><th>本次配息</th></tr></thead>
          <tbody>
            ${dividends.map((d) => `
              <tr>
                <th>${d.date}</th>
                <td>${d.cash_per_share}</td>
                <td>${d.shares_at_ex_date.toFixed(2)}</td>
                <td>${fmtCurrency(d.dividend_received)}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;
  if (splits.length) {
    html += `
      <div class="metric-block">
        <h5>股票分割紀錄</h5>
        <div class="pivot-wrapper">
          <table class="pivot-table" style="font-size: 0.85rem;">
            <thead><tr><th>分割日</th><th>比例</th><th>分割前持股</th><th>分割後持股</th><th>分割後 close</th></tr></thead>
            <tbody>
              ${splits.map((s) => `
                <tr>
                  <th>${s.date}</th>
                  <td><strong>${s.ratio}</strong></td>
                  <td>${s.shares_before.toFixed(2)}</td>
                  <td>${s.shares_after.toFixed(2)}</td>
                  <td>${s.close_after_split}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }
  body.innerHTML = html;
}

function renderCards(data) {
  const el = document.getElementById('dca-cards');
  if (!el) return;
  el.innerHTML = data.scenarios.map((s) => {
    const color = DCA_COLORS[s.key] || '#666';
    const bullets = s.description.map((line) => `<li>${line}</li>`).join('');
    const note = s.note ? `<p class="scenario-note">${s.note}</p>` : '';
    return `
      <div class="scenario-card" style="border-top: 4px solid ${color};">
        <div class="scenario-head">
          <span class="scenario-key" style="color: ${color};">${s.key}</span>
          <span class="scenario-name">${s.name}</span>
        </div>
        <div class="scenario-target">標的：<strong>${s.target_name}</strong></div>
        <ul class="scenario-desc">${bullets}</ul>
        ${note}
      </div>
    `;
  }).join('');
}

function renderSummaryTable(data) {
  const el = document.getElementById('dca-table');
  if (!el) return;
  const rows = data.scenarios.map((s) => {
    const color = DCA_COLORS[s.key] || '#666';
    const retClass = s.return_pct > 0 ? 'pos' : s.return_pct < 0 ? 'neg' : 'zero';
    const gain = s.end_total_assets - s.total_deposits;
    const gainClass = gain > 0 ? 'pos' : gain < 0 ? 'neg' : 'zero';
    return `
      <tr>
        <th style="color: ${color};">${s.key}</th>
        <td class="scenario-name-cell">${s.name}</td>
        <td>${s.months_invested ?? '-'}</td>
        <td>${fmtCurrency(s.total_deposits)}</td>
        <td>${fmtCurrency(s.end_total_assets)}</td>
        <td class="${gainClass}">${fmtCurrency(gain)}</td>
        <td class="${retClass}"><strong>${s.return_pct >= 0 ? '+' : ''}${s.return_pct.toFixed(2)}%</strong></td>
      </tr>
    `;
  }).join('');
  el.innerHTML = `
    <table class="pivot-table dca-summary-table">
      <thead>
        <tr>
          <th>方案</th>
          <th>名稱</th>
          <th>月數</th>
          <th>累積入金</th>
          <th>期末總資產</th>
          <th>獲利</th>
          <th>報酬率</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function renderTable(data) {
  const el = document.getElementById('dca-summary-wrapper');
  if (!el) return;
  const rows = data.scenarios.map((s) => {
    const color = DCA_COLORS[s.key] || '#666';
    const trades = (s.num_buys !== undefined || s.num_sells !== undefined)
      ? `<span class="buy-count">${s.num_buys ?? 0}</span> 買 / <span class="sell-count">${s.num_sells ?? 0}</span> 賣${s.num_completed_rounds !== undefined ? ` · ${s.num_completed_rounds} 輪` : ''}`
      : '每月 1 次全額投入';
    return `
      <tr>
        <th style="color: ${color};">${s.key}</th>
        <td>${fmt(s.end_close)}</td>
        <td>${(s.end_shares || 0).toFixed(2)}</td>
        <td>${s.avg_cost_per_share ? fmt(s.avg_cost_per_share) : (s.end_avg_cost ? fmt(s.end_avg_cost) : '-')}</td>
        <td>${fmtCurrency(s.end_market_value)}</td>
        <td>${s.end_capital_pool !== undefined ? fmtCurrency(s.end_capital_pool) : '-'}</td>
        <td class="activity-cell">${trades}</td>
      </tr>
    `;
  }).join('');
  el.innerHTML = `
    <table class="pivot-table">
      <thead>
        <tr>
          <th>方案</th>
          <th>期末收盤</th>
          <th>期末持股</th>
          <th>成本均價</th>
          <th>持股市值</th>
          <th>資本池</th>
          <th>交易活動</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function renderChart(data) {
  const canvas = document.getElementById('dca-chart');
  if (!canvas || typeof Chart === 'undefined') return;
  if (dcaChartInstance) { dcaChartInstance.destroy(); dcaChartInstance = null; }

  const first = data.scenarios[0] && data.scenarios[0].daily;
  if (!first) return;
  const labels = first.map((p) => p.date);
  const c = getChartColors();

  const datasets = data.scenarios.map((s) => ({
    label: `${s.key} · ${s.name}`,
    data: (s.daily || []).map((p) => p.total_assets),
    borderColor: DCA_COLORS[s.key],
    backgroundColor: DCA_COLORS[s.key],
    borderWidth: 1.6,
    pointRadius: 0,
    tension: 0,
  }));

  dcaChartInstance = new Chart(canvas, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { position: 'top', labels: { color: c.text, boxWidth: 12 } },
        tooltip: {
          mode: 'index', intersect: false,
          callbacks: {
            label: (ctx) => `${ctx.dataset.label}: ${fmtCurrency(ctx.parsed.y)}`,
          },
        },
      },
      scales: {
        x: {
          ticks: {
            color: c.text, maxTicksLimit: 12, maxRotation: 0,
            callback: function (value) {
              const label = this.getLabelForValue(value);
              return typeof label === 'string' && label.length >= 7 ? label.slice(0, 7) : label;
            },
          },
          grid: { color: c.grid },
        },
        y: {
          ticks: {
            color: c.text,
            callback: (v) => v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `${(v / 1e3).toFixed(0)}K` : v,
          },
          grid: { color: c.grid },
        },
      },
    },
  });
}

function boot() {
  loadDCA();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}
