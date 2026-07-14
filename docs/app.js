const SIGNAL_CLASS = {
  NONE: 'none',
  BUY_TRANCHE_1: 'buy',
  BUY_TRANCHE_2: 'buy',
  ALERT_MA60: 'alert',
  SELL_ALL: 'sell',
};

const POSITION_CLASS = {
  CASH: 'cash',
  HALF: 'half',
  FULL: 'full',
};

async function loadStatus(url = './latest.json', suffix = '', updateShared = true) {
  try {
    const resp = await fetch(`${url}?t=${Date.now()}`, { cache: 'no-store' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    render(data, suffix, updateShared);
  } catch (err) {
    const el = document.getElementById('signal-text' + suffix);
    if (el) el.textContent = '讀取失敗';
    console.error(`Failed to load ${url}:`, err);
  }
}

function render(data, suffix = '', updateShared = true) {
  const signalEl = document.getElementById('signal-text' + suffix);
  if (signalEl) {
    // 拆兩行：主動作（第一行大） + 括號內的條件敘述（第二行小灰）
    const raw = data.signal_zh || '-';
    const match = raw.match(/^(.+?)（(.+)）\s*$/);
    if (match) {
      signalEl.innerHTML =
        `<span class="signal-main">${match[1]}</span>` +
        `<span class="signal-sub">（${match[2]}）</span>`;
    } else {
      signalEl.innerHTML = `<span class="signal-main">${raw}</span>`;
    }
    signalEl.classList.remove('buy', 'sell', 'alert');
    const sigClass = SIGNAL_CLASS[data.signal];
    if (sigClass && sigClass !== 'none') signalEl.classList.add(sigClass);
  }

  const posEl = document.getElementById('position-text' + suffix);
  if (posEl) {
    posEl.textContent = data.position_zh;
    posEl.classList.remove('half', 'full');
    const posClass = POSITION_CLASS[data.position];
    if (posClass && posClass !== 'cash') posEl.classList.add(posClass);
  }

  if (updateShared) {
    const closeLabel = document.getElementById('close-label');
    if (closeLabel && data.date) {
      // "2026-07-13" → "07-13"
      closeLabel.textContent = `${data.date.slice(5)} 收盤`;
    }
    document.getElementById('close-value').textContent = fmt(data.close);
    document.getElementById('ma5-value').textContent = fmt(data.ma5);
    document.getElementById('ma20-value').textContent = fmt(data.ma20);
    document.getElementById('ma60-value').textContent = fmt(data.ma60);
    document.getElementById('date-line').textContent = `資料日期：${data.date}`;
    document.getElementById('updated-line').textContent = `最後更新：${formatUpdatedAt(data.updated_at)}`;
  }
}

function fmt(n) {
  return typeof n === 'number' ? n.toFixed(2) : '-';
}

function formatUpdatedAt(isoUtc) {
  if (!isoUtc) return '-';
  const d = new Date(isoUtc);
  const pad = (v) => String(v).padStart(2, '0');
  const local = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  return `${local}（本地時間）`;
}

let chartSegments = [];
let chartIndex = 0;
let chartInstance = null;

async function loadHistory() {
  try {
    const url = `./history.json?t=${Date.now()}`;
    const resp = await fetch(url, { cache: 'no-store' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    chartSegments = Array.isArray(data.segments) ? data.segments : [];
    if (chartSegments.length === 0) return;
    chartIndex = chartSegments.length - 1;
    renderCurrentSegment();
    setupChartNav();
  } catch (err) {
    console.error('Failed to load history.json:', err);
  }
}

function setupChartNav() {
  const prev = document.getElementById('chart-prev');
  const next = document.getElementById('chart-next');
  if (prev) prev.addEventListener('click', () => {
    if (chartIndex > 0) { chartIndex--; renderCurrentSegment(); }
  });
  if (next) next.addEventListener('click', () => {
    if (chartIndex < chartSegments.length - 1) { chartIndex++; renderCurrentSegment(); }
  });
}

function renderCurrentSegment() {
  const seg = chartSegments[chartIndex];
  if (!seg) return;
  const titleEl = document.getElementById('chart-title');
  const rangeEl = document.getElementById('chart-range');
  const prev = document.getElementById('chart-prev');
  const next = document.getElementById('chart-next');
  if (titleEl) titleEl.textContent = seg.label;
  if (rangeEl) rangeEl.textContent = `${seg.start_date} ~ ${seg.end_date}（${seg.count} 個交易日）`;
  if (prev) prev.disabled = chartIndex === 0;
  if (next) next.disabled = chartIndex === chartSegments.length - 1;
  renderChart('price-chart', seg.series);
}

function getChartColors() {
  const styles = getComputedStyle(document.documentElement);
  return {
    close: styles.getPropertyValue('--text').trim() || '#111827',
    ma5: '#f97316',
    ma20: '#2563eb',
    ma60: '#a855f7',
    grid: styles.getPropertyValue('--border').trim() || '#e5e7eb',
    text: styles.getPropertyValue('--text-muted').trim() || '#6b7280',
  };
}

function renderChart(canvasId, series) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || typeof Chart === 'undefined' || !series || !series.length) return;
  if (chartInstance) { chartInstance.destroy(); chartInstance = null; }
  const c = getChartColors();
  const labels = series.map((p) => p.date);
  const mkDataset = (label, key, color, width, yAxisID = 'y') => ({
    label,
    data: series.map((p) => p[key]),
    borderColor: color,
    backgroundColor: color,
    borderWidth: width,
    pointRadius: 0,
    tension: 0,
    spanGaps: true,
    yAxisID,
  });
  chartInstance = new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: [
        mkDataset('收盤價', 'close', c.close, 1.6, 'y'),
        mkDataset('MA5', 'ma5', c.ma5, 1, 'y'),
        mkDataset('MA20', 'ma20', c.ma20, 1, 'y'),
        mkDataset('MA60', 'ma60', c.ma60, 1, 'y'),
        mkDataset('漲跌幅', 'change_pct', 'rgba(107, 114, 128, 0.55)', 0.8, 'y1'),
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { position: 'top', labels: { color: c.text, boxWidth: 12 } },
        tooltip: { mode: 'index', intersect: false },
      },
      scales: {
        x: {
          ticks: {
            color: c.text,
            maxTicksLimit: 8,
            maxRotation: 0,
            callback: function (value) {
              const label = this.getLabelForValue(value);
              return typeof label === 'string' && label.length >= 10
                ? label.slice(5).replace('-', '/')
                : label;
            },
          },
          grid: { color: c.grid },
        },
        y: {
          type: 'linear',
          position: 'left',
          ticks: { color: c.text },
          grid: { color: c.grid },
          title: { display: true, text: '價格 (TWD)', color: c.text, font: { size: 11 } },
        },
        y1: {
          type: 'linear',
          position: 'right',
          ticks: {
            color: c.text,
            callback: (v) => `${v}%`,
          },
          grid: { drawOnChartArea: false },
          title: { display: true, text: '漲跌幅 (%)', color: c.text, font: { size: 11 } },
        },
      },
    },
  });
}

async function loadLiveTrades(url = './live_trades.json', suffix = '') {
  try {
    const resp = await fetch(`${url}?t=${Date.now()}`, { cache: 'no-store' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    renderLiveTrades(data, suffix);
  } catch (err) {
    console.error(`Failed to load ${url}:`, err);
  }
}

function fmtCurrency(n) {
  if (typeof n !== 'number') return '-';
  const abs = Math.abs(n).toLocaleString('en-US', { maximumFractionDigits: 0 });
  if (n > 0) return `+${abs}`;
  if (n < 0) return `-${abs}`;
  return `${abs}`;
}

function fmtNumber(n) {
  if (typeof n !== 'number') return '-';
  return Math.abs(n).toLocaleString('en-US', { maximumFractionDigits: 0 });
}

function fmtPct(n) {
  if (typeof n !== 'number') return '-';
  const sign = n > 0 ? '+' : '';
  return `${sign}${n.toFixed(2)}%`;
}

function renderLiveTrades(data, suffix = '') {
  const startDate = data.live_start_date;
  const asOfDate = data.as_of_date;
  const gid = (id) => document.getElementById(id + suffix);
  const header = gid('live-header-line');
  if (header) header.textContent = `啟動日：${startDate}｜資料截至：${asOfDate}`;
  const inline = gid('live-start-date-inline');
  if (inline) inline.textContent = startDate;

  const trades = data.trades || [];
  const rounds = data.rounds || [];
  const current = data.current_round;
  const summary = data.summary || {};

  // 讓兩欄視覺對齊：所有 sections 都顯示，內容空時用 placeholder
  const emptyEl = gid('live-empty');
  const summarySec = gid('live-summary-section');
  const currentSec = gid('live-current-round');
  const tradesSec = gid('live-trades-section');
  const roundsSec = gid('live-rounds-section');
  if (emptyEl) emptyEl.hidden = true;
  if (summarySec) summarySec.hidden = false;
  if (currentSec) currentSec.hidden = false;
  if (tradesSec) tradesSec.hidden = false;
  if (roundsSec) roundsSec.hidden = false;

  // === Summary card（永遠顯示） ===
  const summaryEl = gid('live-summary');
  if (summaryEl) {
    summaryEl.innerHTML = `
      <div class="summary-item">
        <div class="summary-label">完成輪次</div>
        <div class="summary-value">${summary.num_completed_rounds || 0}</div>
      </div>
      <div class="summary-item">
        <div class="summary-label">已實現損益</div>
        <div class="summary-value">${fmtCurrency(summary.total_realized_pnl || 0)}</div>
      </div>
      <div class="summary-item">
        <div class="summary-label">累積入金</div>
        <div class="summary-value">${fmtNumber(summary.total_deposits || 0)}</div>
      </div>
      <div class="summary-item">
        <div class="summary-label">未實現損益</div>
        <div class="summary-value">${fmtCurrency(summary.current_open_pnl || 0)}</div>
      </div>
    `;
  }

  // === 目前部位狀態（永遠顯示） ===
  const cbEl = gid('live-current-round-body');
  if (cbEl) {
    if (current) {
      const pnlCls = current.current_pnl > 0 ? 'pos' : (current.current_pnl < 0 ? 'neg' : '');
      cbEl.innerHTML = `
        <div>進場日：<strong>${current.entry_date || '-'}</strong></div>
        <div>成本均價：<strong>${fmt(current.avg_cost)}</strong></div>
        <div>累積投入：<strong>${fmtNumber(current.total_invested)}</strong></div>
        <div>當前市值：<strong>${fmtNumber(current.market_value)}<span class="pnl-inline ${pnlCls}">（${fmtCurrency(current.current_pnl)} / ${fmtPct(current.current_pnl_pct)}）</span></strong></div>
        ${current.ma60_alerted ? '<div style="color: var(--signal-alert);">⚠︎ 本輪曾跌破季線 MA60</div>' : ''}
      `;
    } else {
      cbEl.innerHTML = `<div class="empty-placeholder">空手中｜等待觸發訊號</div>`;
    }
  }

  // === 交易時間軸（永遠顯示） ===
  const tradesList = gid('live-trades-list');
  if (tradesList) {
    if (trades.length) {
      const roundByExitDate = new Map();
      rounds.forEach((r) => {
        if (!roundByExitDate.has(r.exit_date)) roundByExitDate.set(r.exit_date, r);
      });
      tradesList.innerHTML = trades
        .map((t) => {
          let extra = '';
          if (t.action === 'SELL_ALL') {
            const r = roundByExitDate.get(t.date);
            if (r) {
              const pnlCls = r.pnl > 0 ? 'pos' : (r.pnl < 0 ? 'neg' : '');
              extra = ` · <span class="${pnlCls}">損益 ${fmtCurrency(r.pnl)}（${fmtPct(r.pnl_pct)}）</span>`;
            }
          }
          return `
            <li class="trade-item ${SIGNAL_CLASS[t.action] || 'none'}">
              <div class="trade-date">${t.date}</div>
              <div class="trade-action">${t.action_zh}${extra}</div>
              <div class="trade-price">@ ${fmt(t.price)}</div>
            </li>
          `;
        })
        .join('');
    } else {
      tradesList.innerHTML = `<li class="empty-placeholder">尚未觸發任何交易</li>`;
    }
  }

  // === 完成輪次（永遠顯示） ===
  const roundsList = gid('live-rounds-list');
  if (roundsList) {
    if (rounds.length) {
      roundsList.innerHTML = rounds
        .map(
          (r) => `
        <li class="round-item ${r.pnl > 0 ? 'win' : 'loss'}">
          <div><strong>${r.entry_date} → ${r.exit_date}</strong>（持有 ${r.days_held} 天）</div>
          <div>投入 ${fmtCurrency(r.total_invested)}｜出場 ${fmtCurrency(r.total_proceeds)}</div>
          <div>損益 <strong>${fmtCurrency(r.pnl)}（${fmtPct(r.pnl_pct)}）</strong></div>
        </li>
      `,
        )
        .join('');
    } else {
      roundsList.innerHTML = `<li class="empty-placeholder">尚無完成輪次</li>`;
    }
  }
}

function boot() {
  // 策略 I (共用 stats + date)
  loadStatus('./latest.json', '', true);
  // 策略 III (只更新 signal / position)
  loadStatus('./latest_iii.json', '-iii', false);

  loadHistory();

  loadLiveTrades('./live_trades.json', '');
  loadLiveTrades('./live_trades_iii.json', '-iii');
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}
