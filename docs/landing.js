const POSITION_ZH = { CASH: '空手', HALF: '半倉', FULL: '滿倉' };
const POSITION_BADGE_CLASS = { CASH: '', HALF: 'half', FULL: 'full' };
const STRATEGY_LABEL = { I: 'I', III: 'III' };

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

async function loadTargets() {
  const el = document.getElementById('target-cards');
  try {
    const resp = await fetch(`./targets.json?t=${Date.now()}`, { cache: 'no-store' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const cfg = await resp.json();
    const targets = cfg.targets || [];
    renderTargets(targets);
    loadLiveSummary(targets);
  } catch (err) {
    console.error('Failed to load targets.json:', err);
    if (el) el.innerHTML = '<p class="muted small" style="grid-column: 1 / -1;">標的物清單載入失敗。</p>';
  }
}

function renderTargets(targets) {
  const el = document.getElementById('target-cards');
  if (!el) return;
  if (!targets.length) {
    el.innerHTML = '<p class="muted small" style="grid-column: 1 / -1;">尚未設定任何標的物。</p>';
    return;
  }
  el.innerHTML = targets.map((t) => `
    <a class="strategy-card" style="display: block; text-decoration: none; color: inherit; border-top: 4px solid var(--signal-buy);" href="./${t.id}/index.html">
      <div class="strategy-head">
        <span class="strategy-key">${t.id}</span>
      </div>
      <div class="strategy-subtitle">${t.name}</div>
      <ul class="strategy-desc">
        <li>掛牌日：${t.listing_date}</li>
        <li>${t.split_date ? `分割：${t.split_date}（1:${t.split_ratio}）` : '無股票分割紀錄'}</li>
      </ul>
    </a>
  `).join('');
}

async function loadLiveSummary(targets) {
  const wrapper = document.getElementById('live-summary-wrapper');
  if (!wrapper) return;

  const files = [
    { strategy: 'I', file: 'live_trades.json' },
    { strategy: 'III', file: 'live_trades_iii.json' },
  ];

  const fetches = [];
  targets.forEach((t) => {
    files.forEach(({ strategy, file }) => {
      fetches.push(
        fetch(`./${t.id}/${file}?t=${Date.now()}`, { cache: 'no-store' })
          .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
          .then((data) => ({ target: t, strategy, data }))
          .catch((err) => {
            console.error(`Failed to load ${t.id}/${file}:`, err);
            return null;
          })
      );
    });
  });

  const results = (await Promise.all(fetches)).filter(Boolean);
  renderLiveSummary(results);
}

function renderLiveSummary(results) {
  const wrapper = document.getElementById('live-summary-wrapper');
  const subtitle = document.getElementById('live-summary-subtitle');
  if (!wrapper) return;

  if (!results.length) {
    wrapper.innerHTML = '<p class="muted small">實盤資料載入失敗。</p>';
    return;
  }

  const liveStart = results[0].data.live_start_date;
  const asOf = results.map((r) => r.data.as_of_date).sort().slice(-1)[0];
  if (subtitle) subtitle.textContent = `自實盤模擬啟動日 ${liveStart} 起，策略 I / III 於各標的的累積成效｜資料截至 ${asOf}`;

  // 依標的、策略排序，同一標的的兩個策略排在一起
  results.sort((a, b) => {
    if (a.target.id !== b.target.id) return a.target.id < b.target.id ? -1 : 1;
    return a.strategy < b.strategy ? -1 : 1;
  });

  const rows = results.map(({ target, strategy, data }) => {
    const s = data.summary || {};
    const totalDeposits = s.total_deposits || 0;
    const marketValue = s.market_value || 0;
    const totalAssets = s.total_assets || 0;
    const pnl = totalAssets - totalDeposits;
    const pnlPct = totalDeposits > 0 ? (pnl / totalDeposits) * 100 : 0;
    const pnlCls = pnl > 0 ? 'pos' : pnl < 0 ? 'neg' : 'zero';
    const position = data.current_round ? data.current_round.position_taken : 'CASH';
    const badgeCls = POSITION_BADGE_CLASS[position] || '';

    return `
      <tr>
        <td class="target-cell" data-label="標的物">${target.id}</td>
        <td data-label="策略">${STRATEGY_LABEL[strategy] || strategy}</td>
        <td data-label="目前部位"><span class="pos-badge ${badgeCls}">${POSITION_ZH[position] || position}</span></td>
        <td data-label="累積投入">${fmtCurrency(totalDeposits)}</td>
        <td data-label="目前市值">${fmtCurrency(marketValue)}</td>
        <td data-label="目前總資產">${fmtCurrency(totalAssets)}</td>
        <td data-label="損益" class="${pnlCls}"><strong>${fmtCurrency(pnl)}</strong>（${fmtPct(pnlPct)}）</td>
      </tr>
    `;
  }).join('');

  wrapper.innerHTML = `
    <table class="pivot-table live-summary-table">
      <thead>
        <tr>
          <th>標的物</th>
          <th>策略</th>
          <th>目前部位</th>
          <th>累積投入</th>
          <th>目前市值</th>
          <th>目前總資產</th>
          <th>損益</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', loadTargets);
} else {
  loadTargets();
}
