const STRATEGY_COLORS = {
  I: '#2563eb',
  II: '#16a34a',
  III: '#ea580c',
  IV: '#a855f7',
  V: '#dc2626',
};

const SIGNAL_CLASS = {
  BUY_TRANCHE_1: 'buy',
  BUY_TRANCHE_2: 'buy',
  SELL_ALL: 'sell',
  ALERT_MA60: 'alert',
};

const ACTION_ZH = {
  BUY_TRANCHE_1: '第一批買進',
  BUY_TRANCHE_2: '第二批加碼',
  SELL_ALL: '獲利出場',
  ALERT_MA60: 'MA60 警戒',
};

let strategyData = null;
let returnChartInstance = null;
let equityChartInstance = null;
let equityYearIndex = 0;

function fmt(n) {
  return typeof n === 'number' ? n.toFixed(2) : '-';
}

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

function showError(err) {
  const banner = document.getElementById('error-banner');
  const body = document.getElementById('error-body');
  if (banner && body) {
    banner.hidden = false;
    body.textContent = String(err && (err.stack || err.message || err));
  }
  console.error(err);
}

async function loadStrategies5() {
  console.log('[comparison] loading strategies_5.json...');
  try {
    const resp = await fetch(`./strategies_5.json?t=${Date.now()}`, { cache: 'no-store' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status} on strategies_5.json`);
    strategyData = await resp.json();
    console.log('[comparison] loaded, calling renderAll');
    try {
      renderAll();
      console.log('[comparison] render complete');
    } catch (renderErr) {
      showError(renderErr);
    }
  } catch (err) {
    showError(err);
  }
}

function renderAll() {
  const data = strategyData;
  const updatedEl = document.getElementById('updated-line');
  if (updatedEl) updatedEl.textContent = `資料更新於：${formatUpdatedAt(data.updated_at)}（本地時間）`;

  renderStrategyCards(data);
  renderPivotTable(data);
  renderReturnChart(data);
  renderActivityTable(data);

  // Equity chart 預設顯示最後一年
  equityYearIndex = data.years.length - 1;
  renderEquityChart(data);
  setupEquityNav(data);

  setupDetailSelector(data);
  renderDetail(String(data.years[data.years.length - 1]), 'III');
}

function renderStrategyCards(data) {
  const el = document.getElementById('strategy-cards');
  if (!el) return;
  el.innerHTML = data.strategies.map((s) => {
    const color = STRATEGY_COLORS[s.key] || '#666';
    const desc = s.description.map((line) => `<li>${line}</li>`).join('');
    return `
      <div class="strategy-card" style="border-top: 4px solid ${color};">
        <div class="strategy-head">
          <span class="strategy-key" style="color: ${color};">${s.key}</span>
          <span class="strategy-name">${s.name}</span>
        </div>
        <div class="strategy-subtitle">${s.subtitle}</div>
        <ul class="strategy-desc">${desc}</ul>
      </div>
    `;
  }).join('');
}

function renderPivotTable(data) {
  const el = document.getElementById('pivot-wrapper');
  if (!el) return;
  const strategyKeys = data.strategies.map((s) => s.key);
  const years = data.years;

  const yearBestWorst = {};
  years.forEach((y) => {
    const row = data.pivot[String(y)];
    const entries = Object.entries(row);
    const best = entries.reduce((a, b) => (a[1] > b[1] ? a : b));
    const worst = entries.reduce((a, b) => (a[1] < b[1] ? a : b));
    yearBestWorst[y] = { best: best[0], worst: worst[0] };
  });

  // 每策略平均年報酬率
  const avgRow = {};
  strategyKeys.forEach((k) => {
    const vals = years.map((y) => data.pivot[String(y)][k]);
    avgRow[k] = vals.reduce((a, b) => a + b, 0) / vals.length;
  });
  const avgValues = Object.values(avgRow);
  const bestAvg = Math.max(...avgValues);
  const worstAvg = Math.min(...avgValues);

  const headRow = ['<th>年份</th>', ...strategyKeys.map((k) => {
    const color = STRATEGY_COLORS[k] || '#666';
    return `<th style="color: ${color};">${k}</th>`;
  })].join('');

  const bodyRows = years.map((y) => {
    const row = data.pivot[String(y)];
    const bw = yearBestWorst[y];
    const cells = strategyKeys.map((k) => {
      const v = row[k];
      const cls = v > 0 ? 'pos' : v < 0 ? 'neg' : 'zero';
      const mark = k === bw.best ? ' best' : k === bw.worst ? ' worst' : '';
      return `<td class="${cls}${mark}">${v >= 0 ? '+' : ''}${v.toFixed(2)}%</td>`;
    }).join('');
    return `<tr><th>${y}</th>${cells}</tr>`;
  }).join('');

  const avgCells = strategyKeys.map((k) => {
    const v = avgRow[k];
    const cls = v > 0 ? 'pos' : v < 0 ? 'neg' : 'zero';
    const mark = v === bestAvg ? ' best' : v === worstAvg ? ' worst' : '';
    return `<td class="${cls}${mark}">${v >= 0 ? '+' : ''}${v.toFixed(2)}%</td>`;
  }).join('');
  const avgRowHTML = `<tr class="avg-row"><th>平均</th>${avgCells}</tr>`;

  el.innerHTML = `
    <table class="pivot-table">
      <thead><tr>${headRow}</tr></thead>
      <tbody>${bodyRows}</tbody>
      <tfoot>${avgRowHTML}</tfoot>
    </table>
    <div class="pivot-legend">
      <span class="legend-mark best">■</span> 該欄最佳
      <span class="legend-mark worst">■</span> 該欄最差
      · 底部「平均」為六年年度報酬率的算術平均
    </div>
  `;
}

function renderActivityTable(data) {
  const el = document.getElementById('activity-wrapper');
  if (!el) return;
  const strategyKeys = data.strategies.map((s) => s.key);
  const years = data.years;

  // 每 (year, strategy) 的購入 / 出售次數
  const activity = {};
  years.forEach((y) => {
    activity[y] = {};
    const yearResults = data.results[String(y)] || {};
    strategyKeys.forEach((k) => {
      const r = yearResults[k] || { trades: [] };
      const trades = r.trades || [];
      const buys = trades.filter((t) => t.action === 'BUY_TRANCHE_1' || t.action === 'BUY_TRANCHE_2').length;
      const sells = trades.filter((t) => t.action === 'SELL_ALL').length;
      activity[y][k] = { buys, sells };
    });
  });

  // 總計
  const totals = {};
  strategyKeys.forEach((k) => {
    totals[k] = { buys: 0, sells: 0 };
    years.forEach((y) => {
      totals[k].buys += activity[y][k].buys;
      totals[k].sells += activity[y][k].sells;
    });
  });

  const headRow = ['<th>年份</th>', ...strategyKeys.map((k) => {
    const color = STRATEGY_COLORS[k] || '#666';
    return `<th style="color: ${color};">${k}</th>`;
  })].join('');

  const bodyRows = years.map((y) => {
    const cells = strategyKeys.map((k) => {
      const a = activity[y][k];
      return `<td class="activity-cell"><span class="buy-count">${a.buys}</span><span class="cell-sep">/</span><span class="sell-count">${a.sells}</span></td>`;
    }).join('');
    return `<tr><th>${y}</th>${cells}</tr>`;
  }).join('');

  const totalCells = strategyKeys.map((k) => {
    const t = totals[k];
    return `<td class="activity-cell"><span class="buy-count">${t.buys}</span><span class="cell-sep">/</span><span class="sell-count">${t.sells}</span></td>`;
  }).join('');
  const totalRowHTML = `<tr class="avg-row"><th>總計</th>${totalCells}</tr>`;

  el.innerHTML = `
    <table class="pivot-table">
      <thead><tr>${headRow}</tr></thead>
      <tbody>${bodyRows}</tbody>
      <tfoot>${totalRowHTML}</tfoot>
    </table>
    <div class="pivot-legend">
      <span class="legend-mark best" style="color: var(--signal-buy);">■</span> 購入次數（BUY_TRANCHE_1 + BUY_TRANCHE_2）
      <span class="legend-mark worst" style="color: var(--signal-sell);">■</span> 出售次數（SELL_ALL）
    </div>
  `;
}

function renderReturnChart(data) {
  const canvas = document.getElementById('return-chart');
  if (!canvas || typeof Chart === 'undefined') return;
  if (returnChartInstance) { returnChartInstance.destroy(); returnChartInstance = null; }
  const c = getChartColors();

  const labels = data.years.map(String);
  const datasets = data.strategies.map((s) => ({
    label: s.key,
    data: data.years.map((y) => data.pivot[String(y)][s.key]),
    backgroundColor: STRATEGY_COLORS[s.key],
    borderColor: STRATEGY_COLORS[s.key],
    borderWidth: 1,
  }));

  returnChartInstance = new Chart(canvas, {
    type: 'bar',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'top', labels: { color: c.text } },
        tooltip: {
          callbacks: {
            label: (ctx) => `策略 ${ctx.dataset.label}: ${ctx.parsed.y >= 0 ? '+' : ''}${ctx.parsed.y.toFixed(2)}%`,
          },
        },
      },
      scales: {
        x: { ticks: { color: c.text }, grid: { color: c.grid } },
        y: {
          ticks: { color: c.text, callback: (v) => `${v}%` },
          grid: { color: c.grid },
        },
      },
    },
  });
}

function renderEquityChart(data) {
  const canvas = document.getElementById('equity-chart');
  if (!canvas || typeof Chart === 'undefined') return;
  if (equityChartInstance) { equityChartInstance.destroy(); equityChartInstance = null; }

  const year = String(data.years[equityYearIndex]);
  const yearResults = data.results[year] || {};
  const first = data.strategies[0] && yearResults[data.strategies[0].key];
  const labels = first ? first.daily.map((d) => d.date) : [];

  const titleEl = document.getElementById('equity-title');
  const rangeEl = document.getElementById('equity-range');
  if (titleEl) titleEl.textContent = `${year} 資本淨值走勢`;
  if (rangeEl && labels.length) {
    rangeEl.textContent = `${labels[0]} ~ ${labels[labels.length - 1]}（${labels.length} 個交易日）`;
  }

  const prev = document.getElementById('equity-prev');
  const next = document.getElementById('equity-next');
  if (prev) prev.disabled = equityYearIndex === 0;
  if (next) next.disabled = equityYearIndex === data.years.length - 1;

  const c = getChartColors();
  const datasets = data.strategies.map((s) => {
    const r = yearResults[s.key];
    return {
      label: `策略 ${s.key}`,
      data: r ? r.daily.map((d) => d.total_assets) : [],
      borderColor: STRATEGY_COLORS[s.key],
      backgroundColor: STRATEGY_COLORS[s.key],
      borderWidth: 1.6,
      pointRadius: 0,
      tension: 0,
    };
  });

  equityChartInstance = new Chart(canvas, {
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
            color: c.text, maxTicksLimit: 8, maxRotation: 0,
            callback: function (value) {
              const label = this.getLabelForValue(value);
              return typeof label === 'string' && label.length >= 10
                ? label.slice(5).replace('-', '/') : label;
            },
          },
          grid: { color: c.grid },
        },
        y: {
          ticks: { color: c.text },
          grid: { color: c.grid },
        },
      },
    },
  });
}

function setupEquityNav(data) {
  const prev = document.getElementById('equity-prev');
  const next = document.getElementById('equity-next');
  if (prev) prev.addEventListener('click', () => {
    if (equityYearIndex > 0) { equityYearIndex--; renderEquityChart(data); }
  });
  if (next) next.addEventListener('click', () => {
    if (equityYearIndex < data.years.length - 1) { equityYearIndex++; renderEquityChart(data); }
  });
}

function setupDetailSelector(data) {
  const yearSel = document.getElementById('detail-year');
  const stratSel = document.getElementById('detail-strategy');
  if (!yearSel || !stratSel) return;

  yearSel.innerHTML = data.years.map((y) => `<option value="${y}">${y}</option>`).join('');
  stratSel.innerHTML = data.strategies.map((s) => `<option value="${s.key}">${s.key} · ${s.subtitle}</option>`).join('');

  yearSel.value = String(data.years[data.years.length - 1]);
  stratSel.value = 'III';

  const update = () => renderDetail(yearSel.value, stratSel.value);
  yearSel.addEventListener('change', update);
  stratSel.addEventListener('change', update);
}

function renderDetail(year, strategy) {
  const data = strategyData;
  if (!data) return;
  const yearResults = data.results[String(year)] || {};
  const r = yearResults[strategy];
  const strategyMeta = data.strategies.find((s) => s.key === strategy);

  const summaryEl = document.getElementById('detail-summary');
  const tradesSec = document.getElementById('detail-trades-section');
  const roundsSec = document.getElementById('detail-rounds-section');

  if (!r) {
    if (summaryEl) summaryEl.innerHTML = '<p class="muted">無資料</p>';
    if (tradesSec) tradesSec.hidden = true;
    if (roundsSec) roundsSec.hidden = true;
    return;
  }

  const retClass = r.return_pct > 0 ? 'pos' : r.return_pct < 0 ? 'neg' : 'zero';
  const gainClass = (r.end_total_assets - r.total_deposits) > 0 ? 'pos' : 'neg';
  const color = STRATEGY_COLORS[strategy] || '#666';

  if (summaryEl) {
    summaryEl.innerHTML = `
      <div class="detail-headline">
        <div>
          <span class="k">策略</span>
          <strong style="color: ${color};">${strategyMeta.key} · ${strategyMeta.subtitle}</strong>
        </div>
        <div class="detail-return ${retClass}">${r.return_pct >= 0 ? '+' : ''}${r.return_pct.toFixed(2)}%</div>
      </div>
      <div class="metric-block">
        <h5>本年成果</h5>
        <dl class="metric-list">
          <div><dt>本年入金</dt><dd>${fmtCurrency(r.total_deposits)}</dd></div>
          <div><dt>期末總資產</dt><dd>${fmtCurrency(r.end_total_assets)}</dd></div>
          <div><dt>本年獲利</dt><dd class="${gainClass}">${fmtCurrency(r.end_total_assets - r.total_deposits)}</dd></div>
          <div><dt>報酬率</dt><dd class="${retClass}">${r.return_pct >= 0 ? '+' : ''}${r.return_pct.toFixed(2)}%</dd></div>
        </dl>
      </div>
      <div class="metric-block">
        <h5>本年進出場次數</h5>
        <dl class="metric-list">
          <div><dt>購入次數</dt><dd><span class="buy-count">${r.num_buys ?? 0}</span> 次</dd></div>
          <div><dt>出售次數</dt><dd><span class="sell-count">${r.num_sells ?? 0}</span> 次</dd></div>
          <div><dt>MA60 警戒次數</dt><dd><span style="color: var(--signal-alert);">${r.num_alerts ?? 0}</span> 次 <span class="muted small">${strategy === 'I' ? '' : '（策略 II~V 無此訊號）'}</span></dd></div>
          <div><dt>完成輪次</dt><dd>${r.num_completed_rounds}</dd></div>
        </dl>
      </div>
      <div class="metric-block">
        <h5>期末部位</h5>
        <dl class="metric-list">
          <div><dt>期末收盤價 (adj)</dt><dd>${fmt(r.end_close)}</dd></div>
          <div><dt>資本池</dt><dd>${fmtCurrency(r.end_capital_pool)}</dd></div>
          <div><dt>持股數</dt><dd>${r.end_shares.toFixed(2)}</dd></div>
          <div><dt>成本均價 (adj)</dt><dd>${r.end_avg_cost ? fmt(r.end_avg_cost) : '-'}</dd></div>
          <div><dt>持股市值</dt><dd>${fmtCurrency(r.end_market_value)}</dd></div>
        </dl>
      </div>
    `;
  }

  if (r.trades && r.trades.length && tradesSec) {
    tradesSec.hidden = false;
    document.getElementById('detail-trades-list').innerHTML = r.trades.map((t) => `
      <li class="trade-item ${SIGNAL_CLASS[t.action] || 'none'}">
        <div class="trade-date">${t.date}</div>
        <div class="trade-action">${ACTION_ZH[t.action] || t.action}${t.invested > 0 ? '｜投入 ' + fmtCurrency(t.invested) : t.invested < 0 ? '｜收回 ' + fmtCurrency(-t.invested) : ''}</div>
        <div class="trade-price">@ ${fmt(t.price)}</div>
      </li>
    `).join('');
  } else if (tradesSec) {
    tradesSec.hidden = true;
  }

  if (r.rounds && r.rounds.length && roundsSec) {
    roundsSec.hidden = false;
    document.getElementById('detail-rounds-list').innerHTML = r.rounds.map((rd) => `
      <li class="round-item ${rd.pnl > 0 ? 'win' : 'loss'}">
        <div><strong>${rd.entry_date} → ${rd.exit_date}</strong>（持有 ${rd.days_held} 天）</div>
        <div>投入 ${fmtCurrency(rd.total_invested)}｜出場 ${fmtCurrency(rd.total_proceeds)}</div>
        <div>損益 <strong>${fmtCurrency(rd.pnl)}（${fmtPct(rd.pnl_pct)}）</strong>｜均價 ${fmt(rd.entry_avg_cost)} → 出場 ${fmt(rd.exit_price)}</div>
      </li>
    `).join('');
  } else if (roundsSec) {
    roundsSec.hidden = true;
  }
}

function boot() {
  loadStrategies5();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}
