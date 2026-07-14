/* Fills in per-target page text (title / h1 / subtitle) from ../targets.json,
   using window.TARGET_ID set inline by each docs/{id}/*.html page. Elements
   opt in with data-template="...{id}...{name}..." (substituted from the
   matching entry in targets.json). Keeps every page byte-identical across
   targets except for that one inline TARGET_ID assignment. */
(function () {
  const targetId = window.TARGET_ID;
  if (!targetId) return;

  fetch('../targets.json', { cache: 'no-store' })
    .then((r) => r.json())
    .then((cfg) => applyMeta(cfg))
    .catch((err) => console.error('Failed to load targets.json:', err));

  function applyMeta(cfg) {
    const target = (cfg.targets || []).find((t) => t.id === targetId);
    if (!target) return;

    document.querySelectorAll('[data-template]').forEach((el) => {
      const tpl = el.getAttribute('data-template');
      el.textContent = tpl.replace(/\{id\}/g, target.id).replace(/\{name\}/g, target.name);
    });

    const splitNote = document.getElementById('dca-split-note');
    if (splitNote) {
      splitNote.textContent = target.split_date
        ? `${target.id} 為 ${target.split_date} 分割還原後價位；槓桿型 ETF 一般不配息。`
        : `${target.id} 無股票分割紀錄；槓桿型 ETF 一般不配息。`;
    }
  }
})();
