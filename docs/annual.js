const SIGNAL_CLASS = {
  NONE: 'none',
  BUY_TRANCHE_1: 'buy',
  BUY_TRANCHE_2: 'buy',
  ALERT_MA60: 'alert',
  SELL_ALL: 'sell',
};

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

async function loadAnnualBacktest(url = './annual_backtest.json', suffix = '') {
  try {
    const resp = await fetch(`${url}?t=${Date.now()}`, { cache: 'no-store' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    renderAnnualBacktest(data, suffix);
  } catch (err) {
    console.error(`Failed to load ${url}:`, err);
  }
}

function renderAnnualBacktest(data, suffix = '') {
  const segments = data.segments || data.years || [];
  if (!segments.length) return;

  const gid = (id) => document.getElementById(id + suffix);

  const returns = segments.map((s) => s.return_pct);
  const avg = returns.reduce((a, b) => a + b, 0) / returns.length;
  const positive = segments.filter((s) => s.return_pct > 0);
  const negative = segments.filter((s) => s.return_pct < 0);
  const best = segments.reduce((a, b) => (a.return_pct > b.return_pct ? a : b));
  const worst = segments.reduce((a, b) => (a.return_pct < b.return_pct ? a : b));
  const summaryCard = gid('annual-summary-card');
  if (summaryCard) summaryCard.hidden = false;
  const summaryEl = gid('annual-summary');
  if (summaryEl) {
    summaryEl.innerHTML = `
      <div><span class="k">段數</span><span class="v">${segments.length}</span></div>
      <div><span class="k">平均報酬率</span><span class="v">${fmtPct(avg)}</span></div>
      <div><span class="k">正報酬 / 負報酬</span><span class="v">${positive.length} / ${negative.length}</span></div>
      <div><span class="k">勝率</span><span class="v">${((positive.length / segments.length) * 100).toFixed(1)}%</span></div>
      <div><span class="k">最佳一段</span><span class="v">${best.label} ${fmtPct(best.return_pct)}</span></div>
      <div><span class="k">最差一段</span><span class="v">${worst.label} ${fmtPct(worst.return_pct)}</span></div>
      <div><span class="k">回測起</span><span class="v">${data.start_date}</span></div>
      <div><span class="k">至</span><span class="v">${data.end_date}</span></div>
    `;
  }

  const listEl = gid('annual-list');
  if (!listEl) return;
  listEl.innerHTML = segments.map((s) => renderYearCard(s)).join('');
}

function renderYearCard(s) {
  const retClass = s.return_pct > 0 ? 'pos' : s.return_pct < 0 ? 'neg' : 'zero';
  const retSign = s.return_pct >= 0 ? '+' : '';
  const gainClass = s.year_gain > 0 ? 'pos' : s.year_gain < 0 ? 'neg' : '';
  const trades = (s.trades || [])
    .map(
      (t) => `
    <li class="${SIGNAL_CLASS[t.action] || 'none'}">
      <span class="td-date">${t.date}</span>
      <span>${t.action_zh} @ ${fmt(t.price)}${t.invested_amount > 0 ? '｜投入 ' + fmtCurrency(t.invested_amount) : ''}</span>
      <span class="td-price">資本池 → ${fmtCurrency(t.capital_after)}</span>
    </li>
  `,
    )
    .join('');
  const rounds = (s.rounds || [])
    .map(
      (r) => `
    <li class="${r.pnl > 0 ? 'win' : 'loss'}">
      <div><strong>${r.entry_date} → ${r.exit_date}</strong>（${r.days_held} 天，${r.position_taken}）</div>
      <div>投入 ${fmtCurrency(r.total_invested)}｜出場 ${fmtCurrency(r.total_proceeds)}｜損益 <strong>${fmtCurrency(r.pnl)}（${fmtPct(r.pnl_pct)}）</strong></div>
    </li>
  `,
    )
    .join('');

  return `
    <details class="annual-card">
      <summary>
        <span class="disclosure">▸</span>
        <div class="annual-label-block">
          <span class="annual-year">${s.label}</span>
          <span class="annual-sublabel">期末總資產 ${fmtCurrency(s.end_total_assets)}</span>
        </div>
        <span class="annual-return ${retClass}">${retSign}${s.return_pct.toFixed(2)}%</span>
      </summary>
      <div class="annual-detail">
        <div class="metric-block">
          <h5>段內回顧</h5>
          <dl class="metric-list">
            <div><dt>回測期間</dt><dd>${s.start_date} ~ ${s.end_date}</dd></div>
            <div><dt>本段入金</dt><dd>${fmtCurrency(s.total_deposits)} <span class="muted">（${s.months_deposited} 個月）</span></dd></div>
            <div><dt>段末總資產</dt><dd>${fmtCurrency(s.end_total_assets)}</dd></div>
            <div><dt>段獲利</dt><dd class="${gainClass}">${fmtCurrency(s.year_gain)}</dd></div>
            <div><dt>報酬率</dt><dd class="${retClass}">${retSign}${s.return_pct.toFixed(2)}%</dd></div>
          </dl>
        </div>
        <div class="metric-block">
          <h5>期末部位快照</h5>
          <dl class="metric-list">
            <div><dt>期末收盤價</dt><dd>${fmt(s.end_close)}</dd></div>
            <div><dt>資本池</dt><dd>${fmtCurrency(s.end_capital_pool)}</dd></div>
            <div><dt>持股數</dt><dd>${s.end_shares.toFixed(2)}</dd></div>
            <div><dt>成本均價</dt><dd>${s.end_avg_cost ? fmt(s.end_avg_cost) : '-'}</dd></div>
            <div><dt>持股市值</dt><dd>${fmtCurrency(s.end_market_value)}</dd></div>
          </dl>
        </div>
        <div class="metric-block">
          <h5>當段操作（${s.trades.length} 筆進出 · ${s.rounds.length} 輪完成）</h5>
          ${trades ? `<ul class="year-trades">${trades}</ul>` : '<p class="muted small">本段無訊號觸發（MA60 熱身期或無破線）。</p>'}
          ${rounds ? `<h6>完成輪次</h6><ul class="year-rounds">${rounds}</ul>` : ''}
        </div>
      </div>
    </details>
  `;
}

function boot() {
  loadAnnualBacktest('./annual_backtest.json', '');
  loadAnnualBacktest('./annual_backtest_iii.json', '-iii');
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}
