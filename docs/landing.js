async function loadTargets() {
  const el = document.getElementById('target-cards');
  try {
    const resp = await fetch(`./targets.json?t=${Date.now()}`, { cache: 'no-store' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const cfg = await resp.json();
    renderTargets(cfg.targets || []);
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

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', loadTargets);
} else {
  loadTargets();
}
